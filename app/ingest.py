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

Вставка — через SQLAlchemy Core (executemany), движок-агностично: работает и на
Postgres-пулере Supabase, и локально. (Раньше тут был сырой SQLite-курсор с `?`
и PRAGMA — на Postgres он падал, а в CI ошибка глоталась `|| echo`.)

Запуск:  python -m app.ingest   (DATABASE_URL -> session pooler :5432)
"""
import json
import os
from collections import defaultdict, Counter

from sqlalchemy import insert, text

from .database import Base, engine
from . import models  # noqa: F401  (регистрирует таблицы в Base.metadata)
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


# Поля обогащения (2ГИС-рейтинги enrich_2gis.py + гео geocode.py) живут НЕ в харвесте.
# При полной пересборке (drop_all) их надо сохранить по host, иначе карта/рейтинги
# на сайте обнулятся до следующего прогона enrich/geocode (а geocode не в дневном CI).
_ENRICH_COLS = [
    "lat", "lng", "rating", "reviews_count",
    "twogis_url", "twogis_id", "rating_updated_at",
]


def _snapshot_enrichment() -> dict[str, dict]:
    """host -> {обогащённые поля}. Пусто, если таблицы ещё нет (первый прогон)."""
    cols = ", ".join(["host", *_ENRICH_COLS])
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {cols} FROM clinics")).mappings().all()
    except Exception:
        return {}
    return {r["host"]: {c: r[c] for c in _ENRICH_COLS} for r in rows if r.get("host")}


def run():
    enrichment = _snapshot_enrichment()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    matcher = Matcher()

    # --- города ---
    cities: dict[str, int] = {}

    def city_id(name):
        name = (name or "Не указан").strip() or "Не указан"
        if name not in cities:
            cities[name] = len(cities) + 1
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
    cid = 0
    for c in clinic_recs:
        cid += 1
        host_to_id[c["host"]] = cid
        shared = brand_counts[_brand_key(c)] >= 2
        row = {
            "id": cid,
            "host": c["host"],
            "name": _display_name(c, shared) or c["host"],
            "city_id": city_id(c.get("city")),
            "address": c.get("address"),
            "source_url": c.get("source_url"),
            "source_type": "web",
            "phone": c.get("phone"),
            "working_hours": c.get("working_hours"),
            **{col: None for col in _ENRICH_COLS},  # единый набор ключей для executemany
        }
        row.update(enrichment.get(c["host"], {}))  # вернуть сохранённые рейтинг/гео по host
        clinic_rows.append(row)
    city_rows = [{"id": i, "name": n} for n, i in cities.items()]

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
            is_cur = m["method"] in ("curated", "curated_fuzzy")
            svc[code] = (len(svc) + 1, m["name"], m["category"], is_cur, m["method"])
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

    # --- bulk insert (SQLAlchemy Core: работает на Postgres) ---
    with engine.begin() as conn:
        if city_rows:
            conn.execute(insert(models.City.__table__), city_rows)
        if clinic_rows:
            conn.execute(insert(models.Clinic.__table__), clinic_rows)
        if service_rows:
            conn.execute(insert(models.Service.__table__), service_rows)
        # ценовых предложений много — режем на батчи
        CHUNK = 1000
        for i in range(0, len(offer_rows), CHUNK):
            conn.execute(insert(models.PriceOffer.__table__), offer_rows[i:i + CHUNK])

    comparable = sum(1 for code, (sid, *_) in svc.items() if len(clinics_of[sid]) >= 2)
    chains = sum(1 for k, n in brand_counts.items() if n >= 2)
    print("=== INGEST DONE ===")
    print(f"  города:    {len(city_rows)}")
    print(f"  клиники:   {len(clinic_rows)}  (сетевых брендов с ≥2 филиалами: {chains})")
    print(f"  услуги:    {len(service_rows)}  (кураторских: {sum(r['is_curated'] for r in service_rows)})")
    print(f"  сравнимых услуг (>=2 клиник): {comparable}")
    print(f"  ценовых предложений: {len(offer_rows)}  (с ценой: {sum(priced_count.values())})")
    print(f"  методы матчинга: {dict(method_stats)}")


if __name__ == "__main__":
    run()
