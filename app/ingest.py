"""
ingest.py — превращает «сырьё» харвестера в нормализованную БД (Postgres/Supabase).

Пайплайн:
    raw/clinics.jsonl + raw/offers.jsonl
        -> дедуп клиник по host, различение филиалов сетей по улице
        -> нормализация и матчинг каждой позиции (app/normalize.Matcher)
        -> канонические услуги (кураторские + авто из данных)
        -> clinics / cities / services / price_offers

Различение филиалов: имя из харвестера — это БРЕНД («Гемотест», «INVITRO (ИНВИТРО)»),
одинаковый на всех филиалах сети. Если бренд (в пределах города) встречается в ≥2
клиниках — к имени добавляется улица из street: «Гемотест, ул. Ауэзова, 11».
Так в выдаче не бывает безликих «Invitro 6», а одинаковые названия различимы.

Запись — ТОЛЬКО DML (роль `loader` не владелец таблиц и не имеет DDL/CREATE,
только RLS-политику FOR ALL USING(true); поэтому никаких drop_all/create_all/TRUNCATE):
  • cities/clinics/services — UPSERT по естественному ключу (name/host/code).
    Существующие id сохраняются → FK из subscriptions/price_history не рвутся,
    обогащение клиник (2ГИС-рейтинг, гео) тоже сохраняется (его колонки апдейт не трогает).
  • price_offers — DELETE + повторная вставка (на них нет входящих FK).
(Раньше тут был SQLite-курсор `?`/PRAGMA + drop_all — падал на Postgres, а в CI
ошибка глоталась `|| echo`.)

Запуск:  python -m app.ingest   (DATABASE_URL -> session pooler :5432)
"""
import datetime as dt
import json
import os
from collections import defaultdict, Counter

from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import engine
from . import models
from .normalize import Matcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "harvester", "raw")


def _iter_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # незавершённая последняя строка (харвест ещё пишет) — пропускаем
                continue


def _brand_key(c: dict) -> tuple[str, str]:
    """Ключ группировки филиалов: (бренд, город) в нижнем регистре."""
    brand = (c.get("brand") or c.get("name") or "").strip().lower()
    city = (c.get("city") or "").strip().lower()
    return brand, city


def _display_name(c: dict, shared: bool) -> str:
    """Имя клиники для выдачи. У сетей (shared=имя встречается ≥2 раз) добавляем улицу."""
    brand = (c.get("brand") or c.get("name") or "").strip()
    street = (c.get("street") or "").strip()
    if shared and street:
        return f"{brand}, {street}"
    return brand or c.get("host", "")


# Поля обогащения (2ГИС-рейтинги enrich_2gis.py + гео geocode.py) пишутся отдельно.
# При UPSERT их колонки в SET не входят -> у существующих клиник сохраняются сами собой,
# у новых клиник остаются NULL до первого прогона enrich/geocode.
_CLINIC_UPDATE = ["name", "city_id", "address", "source_url", "source_type",
                  "phone", "working_hours"]
_SERVICE_UPDATE = ["name", "category", "is_curated", "match_method", "n_offers", "n_clinics"]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def run():
    matcher = Matcher()
    now = dt.datetime.now(dt.timezone.utc)  # отметка актуальности цен (ТЗ §3.3)

    # --- существующие id (чтобы UPSERT сохранял их и не рвал FK) ---
    with engine.connect() as conn:
        ex_cities = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM cities"))}
        ex_clinics = {r.host: r.id for r in conn.execute(text("SELECT id, host FROM clinics"))}
        ex_services = {r.code: r.id for r in conn.execute(text("SELECT id, code FROM services"))}
    city_seq = max(ex_cities.values(), default=0)
    clinic_seq = max(ex_clinics.values(), default=0)
    service_seq = max(ex_services.values(), default=0)

    # --- города ---
    cities: dict[str, int] = dict(ex_cities)
    new_city_rows = []

    def city_id(name):
        nonlocal city_seq
        name = (name or "Не указан").strip() or "Не указан"
        if name not in cities:
            city_seq += 1
            cities[name] = city_seq
            new_city_rows.append({"id": city_seq, "name": name})
        return cities[name]

    # --- клиники: дедуп по host + различение филиалов по улице ---
    clinic_recs = []
    seen_host: set[str] = set()
    for c in _iter_jsonl(os.path.join(RAW, "clinics.jsonl")):
        if c["host"] in seen_host:
            continue
        seen_host.add(c["host"])
        clinic_recs.append(c)

    brand_counts = Counter(_brand_key(c) for c in clinic_recs)

    host_to_id: dict[str, int] = {}
    clinic_rows = []
    new_clinics = 0
    for c in clinic_recs:
        host = c["host"]
        if host in ex_clinics:
            cid = ex_clinics[host]
        else:
            clinic_seq += 1
            cid = clinic_seq
            new_clinics += 1
        host_to_id[host] = cid
        shared = brand_counts[_brand_key(c)] >= 2
        clinic_rows.append({
            "id": cid,
            "host": host,
            "name": _display_name(c, shared) or host,
            "city_id": city_id(c.get("city")),
            "address": c.get("address"),
            "source_url": c.get("source_url"),
            "source_type": "web",
            "phone": c.get("phone"),
            "working_hours": c.get("working_hours"),
        })

    # --- услуги + ценовые предложения (матчинг) ---
    svc: dict[str, tuple] = {}          # code -> (id, name, category, is_curated, method)
    offer_rows = []
    priced_count = defaultdict(int)     # service_id -> кол-во цен
    clinics_of = defaultdict(set)       # service_id -> {clinic_id}
    oid = 0
    method_stats = defaultdict(int)

    for o in _iter_jsonl(os.path.join(RAW, "offers.jsonl")):
        clinic_id = host_to_id.get(o["host"])
        if clinic_id is None:
            continue
        m = matcher.match(o["raw_name"])
        if not m:
            continue
        code = m["code"]
        if code not in svc:
            sid = ex_services.get(code)
            if sid is None:
                service_seq += 1
                sid = service_seq
            is_cur = m["method"] in ("curated", "curated_fuzzy")
            svc[code] = (sid, m["name"], m["category"], is_cur, m["method"])
        sid = svc[code][0]
        oid += 1
        method_stats[m["method"]] += 1
        offer_rows.append({
            "id": oid,
            "clinic_id": clinic_id,
            "service_id": sid,
            "raw_name": o["raw_name"],
            "price": o.get("price"),
            "currency": o.get("currency", "KZT"),
            "is_from": bool(o.get("is_from")),
            "on_request": bool(o.get("on_request")),
            "match_method": m["method"],
            "match_score": m["score"],
            "source_type": "web",
            "parsed_at": now,
        })
        if o.get("price") is not None:
            priced_count[sid] += 1
            clinics_of[sid].add(clinic_id)

    service_rows = [
        {
            "id": sid, "code": code, "name": name, "category": cat,
            "is_curated": bool(is_cur), "match_method": meth,
            "n_offers": priced_count[sid], "n_clinics": len(clinics_of[sid]),
        }
        for code, (sid, name, cat, is_cur, meth) in svc.items()
    ]

    # --- предохранитель: пустой вход НЕ должен обнулить прод ---
    # (в CI raw/*.jsonl gitignored и отсутствуют; без этого DELETE FROM price_offers
    #  снёс бы все цены без повторной вставки). Пишем, только если есть и клиники, и цены.
    if not clinic_rows or not offer_rows:
        print("=== INGEST SKIPPED ===")
        print(f"  пустой вход: clinics={len(clinic_rows)} offers={len(offer_rows)} "
              f"(нет harvester/raw/*.jsonl?) — БД не тронута")
        return

    # --- запись: только DML (см. модульный docstring) ---
    def _upsert(conn, table, rows, conflict, update_cols):
        for batch in _chunks(rows, 500):
            stmt = pg_insert(table).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict],
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            )
            conn.execute(stmt)

    with engine.begin() as conn:
        if new_city_rows:
            conn.execute(insert(models.City.__table__), new_city_rows)
        _upsert(conn, models.Clinic.__table__, clinic_rows, "host", _CLINIC_UPDATE)
        _upsert(conn, models.Service.__table__, service_rows, "code", _SERVICE_UPDATE)
        # price_offers — без входящих FK: полностью пересобираем
        conn.execute(text("DELETE FROM price_offers"))
        for batch in _chunks(offer_rows, 1000):
            conn.execute(insert(models.PriceOffer.__table__), batch)

    comparable = sum(1 for code, (sid, *_) in svc.items() if len(clinics_of[sid]) >= 2)
    chains = sum(1 for k, n in brand_counts.items() if n >= 2)
    print("=== INGEST DONE ===")
    print(f"  города:    +{len(new_city_rows)} новых (всего {len(cities)})")
    print(f"  клиники:   {len(clinic_rows)}  (+{new_clinics} новых; сетевых брендов с ≥2 филиалами: {chains})")
    print(f"  услуги:    {len(service_rows)}  (кураторских: {sum(r['is_curated'] for r in service_rows)})")
    print(f"  сравнимых услуг (>=2 клиник): {comparable}")
    print(f"  ценовых предложений: {len(offer_rows)}  (с ценой: {sum(priced_count.values())})")
    print(f"  методы матчинга: {dict(method_stats)}")


if __name__ == "__main__":
    run()
