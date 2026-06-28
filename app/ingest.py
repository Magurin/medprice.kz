"""
ingest.py — нормализация собранного сырья из БД-слоя в витрину (price_offers).

ПОСЛЕ переезда сбора на VM источник сырья — НЕ файлы harvester/raw/*.jsonl (их на
VM нет), а таблицы БД, которые наполняет app.parser:
    raw_price_items (позиции «как пришли») + raw_clinics (метаданные клиник)
        -> матчинг каждой позиции (app.normalize.Matcher) к каноническим услугам
        -> clinics / services / price_offers

БЕЗОПАСНОСТЬ (на проде ~278k price_offers живого каталога):
  • НИКАКОГО глобального DELETE. Веб-цены пересобираем ТОЧЕЧНО — только для клиник,
    которые реально присутствуют в текущем сырье (scoped delete по clinic_id).
    Клиники, которые в этот прогон не парсились, и их цены — не трогаем.
  • Существующие клиники переиспользуем по host (id + 2ГИС-обогащение сохраняются,
    имя НЕ переписываем). Новые клиники создаём из raw_clinics.
  • Ручные/импортные цены (source_type != 'web') не трогаем — они не из парсера.
  • Пустое сырьё -> выходим, ничего не пишем.

Запуск:
  python -m app.ingest            # боевой прогон
  python -m app.ingest --dry-run  # показать дельты и откатить (ничего не записать)
"""
import argparse
import datetime as dt
from collections import defaultdict, Counter

from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import engine
from . import models
from .normalize import Matcher

_SERVICE_UPDATE = ["name", "category", "is_curated", "match_method", "n_offers", "n_clinics"]
# Поля, которыми заполняем НОВУЮ клинику (существующие не трогаем).
_NEW_CLINIC_COLS = ["id", "host", "name", "city_id", "address",
                    "source_url", "source_type", "phone", "working_hours"]


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _brand_key(name, city) -> tuple[str, str]:
    return ((name or "").strip().lower(), (city or "").strip().lower())


def run(dry_run: bool = False):
    matcher = Matcher()
    now = dt.datetime.now(dt.timezone.utc)

    with engine.connect() as conn:
        # --- сырьё из БД-слоя ---
        raw_clinics = list(conn.execute(text("""
            SELECT host, name, brand, street, city, address, phone, working_hours, source_url
            FROM raw_clinics
        """)))
        # текущая цена на пару (host, raw_name) = самая свежая запись
        raw_offers = list(conn.execute(text("""
            SELECT DISTINCT ON (clinic_host, raw_name)
                   clinic_host AS host, raw_name, price, currency, is_from, on_request
            FROM raw_price_items
            WHERE source_kind = 'web' AND clinic_host IS NOT NULL
            ORDER BY clinic_host, raw_name, captured_at DESC, id DESC
        """)))
        # существующие сущности
        ex_cities = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM cities"))}
        ex_clinics = {r.host: r.id for r in conn.execute(text("SELECT id, host FROM clinics"))}
        ex_services = {r.code: r.id for r in conn.execute(text("SELECT id, code FROM services"))}

    if not raw_offers:
        print("=== INGEST SKIPPED ===")
        print("  raw_price_items пуст (нет web-сырья) — БД не тронута")
        return

    rc_by_host = {r.host: r for r in raw_clinics}
    brand_counts = Counter(_brand_key(r.brand or r.name, r.city) for r in raw_clinics)

    # --- города (создаём недостающие, существующие id сохраняем) ---
    cities = dict(ex_cities)
    new_city_rows = []
    city_seq = max(ex_cities.values(), default=0)

    def city_id(name):
        nonlocal city_seq
        name = (name or "Не указан").strip() or "Не указан"
        if name not in cities:
            city_seq += 1
            cities[name] = city_seq
            new_city_rows.append({"id": city_seq, "name": name})
        return cities[name]

    # --- клиники: существующие переиспользуем по host, новые создаём из raw_clinics ---
    hosts_in_run, seen = [], set()
    for o in raw_offers:
        if o.host and o.host not in seen:
            seen.add(o.host)
            hosts_in_run.append(o.host)

    clinic_seq = max(ex_clinics.values(), default=0)
    host_to_id = {}
    new_clinic_rows = []
    for host in hosts_in_run:
        if host in ex_clinics:
            host_to_id[host] = ex_clinics[host]      # переиспользуем (имя/обогащение не трогаем)
            continue
        clinic_seq += 1
        cid = clinic_seq
        host_to_id[host] = cid
        rc = rc_by_host.get(host)
        if rc:
            shared = brand_counts[_brand_key(rc.brand or rc.name, rc.city)] >= 2
            brand = (rc.brand or rc.name or host).strip()
            name = f"{brand}, {rc.street}" if (shared and rc.street) else brand
            new_clinic_rows.append({
                "id": cid, "host": host, "name": name or host,
                "city_id": city_id(rc.city), "address": rc.address,
                "source_url": rc.source_url, "source_type": "web",
                "phone": rc.phone, "working_hours": rc.working_hours,
            })
        else:   # позиции без метаданных клиники — минимальная заглушка (обогатится позже)
            new_clinic_rows.append({
                "id": cid, "host": host, "name": host, "city_id": city_id(None),
                "address": None, "source_url": f"https://{host}/", "source_type": "web",
                "phone": None, "working_hours": None,
            })

    # --- матчинг позиций -> услуги + ценовые предложения ---
    svc = {}
    offer_rows = []
    priced_count = defaultdict(int)
    clinics_of = defaultdict(set)
    method_stats = defaultdict(int)
    service_seq = max(ex_services.values(), default=0)

    for o in raw_offers:
        clinic_id = host_to_id.get(o.host)
        if clinic_id is None:
            continue
        m = matcher.match(o.raw_name)
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
        method_stats[m["method"]] += 1
        offer_rows.append({
            "clinic_id": clinic_id, "service_id": sid, "raw_name": o.raw_name,
            "price": o.price, "currency": o.currency or "KZT",
            "is_from": bool(o.is_from), "on_request": bool(o.on_request),
            "match_method": m["method"], "match_score": m["score"],
            "source_type": "web", "parsed_at": now,
        })
        if o.price is not None:
            priced_count[sid] += 1
            clinics_of[sid].add(clinic_id)

    if not offer_rows:
        print("=== INGEST SKIPPED ===")
        print(f"  ни одна из {len(raw_offers)} позиций не сматчилась с услугами — БД не тронута")
        return

    service_rows = [
        {"id": sid, "code": code, "name": name, "category": cat,
         "is_curated": bool(is_cur), "match_method": meth,
         "n_offers": priced_count[sid], "n_clinics": len(clinics_of[sid])}
        for code, (sid, name, cat, is_cur, meth) in svc.items()
    ]
    touched_ids = sorted(set(host_to_id.values()))

    def _upsert(conn, table, rows, conflict, update_cols):
        for batch in _chunks(rows, 500):
            stmt = pg_insert(table).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict],
                set_={col: getattr(stmt.excluded, col) for col in update_cols},
            )
            conn.execute(stmt)

    # --- запись в одной транзакции (dry-run -> откат после подсчёта дельт) ---
    conn = engine.connect()
    trans = conn.begin()
    try:
        web_before = conn.execute(text(
            "SELECT COUNT(*) FROM price_offers WHERE source_type='web' AND clinic_id = ANY(:ids)"
        ), {"ids": touched_ids}).scalar() or 0

        if new_city_rows:
            conn.execute(insert(models.City.__table__), new_city_rows)
        if new_clinic_rows:
            _upsert(conn, models.Clinic.__table__, new_clinic_rows, "host", _NEW_CLINIC_COLS[1:])
        _upsert(conn, models.Service.__table__, service_rows, "code", _SERVICE_UPDATE)
        for seq, tbl in (("cities_id_seq", "cities"),
                         ("clinics_id_seq", "clinics"),
                         ("services_id_seq", "services")):
            conn.execute(text(
                f"SELECT setval('{seq}', GREATEST((SELECT COALESCE(MAX(id),0) FROM {tbl}),1))"
            ))

        # ТОЧЕЧНАЯ пересборка веб-цен: только затронутые клиники, остальное не трогаем.
        conn.execute(text(
            "DELETE FROM price_offers WHERE source_type='web' AND clinic_id = ANY(:ids)"
        ), {"ids": touched_ids})
        conn.execute(text(
            "SELECT setval('price_offers_id_seq', GREATEST((SELECT COALESCE(MAX(id),0) FROM price_offers),1))"
        ))
        for batch in _chunks(offer_rows, 1000):
            conn.execute(insert(models.PriceOffer.__table__), batch)

        # счётчики услуг — по ВСЕЙ таблице (включая ручные цены)
        conn.execute(text("""
            UPDATE services s SET n_offers=COALESCE(a.no,0), n_clinics=COALESCE(a.nc,0)
            FROM (SELECT service_id, COUNT(*) no, COUNT(DISTINCT clinic_id) nc
                  FROM price_offers WHERE price IS NOT NULL GROUP BY service_id) a
            WHERE s.id=a.service_id
        """))
        # история цен: точка на пару клиника+услуга только при изменении цены
        conn.execute(text("""
            WITH cur AS (
                SELECT clinic_id, service_id, MIN(price) AS price
                FROM price_offers WHERE price IS NOT NULL
                GROUP BY clinic_id, service_id
            ),
            latest AS (
                SELECT DISTINCT ON (clinic_id, service_id) clinic_id, service_id, price
                FROM price_history ORDER BY clinic_id, service_id, recorded_at DESC, id DESC
            )
            INSERT INTO price_history (clinic_id, service_id, price, recorded_at, source_file)
            SELECT cur.clinic_id, cur.service_id, cur.price, :now, 'snapshot'
            FROM cur LEFT JOIN latest l
              ON l.clinic_id=cur.clinic_id AND l.service_id=cur.service_id
            WHERE l.price IS NULL OR l.price <> cur.price
        """), {"now": now})

        comparable = sum(1 for _, (sid, *_) in svc.items() if len(clinics_of[sid]) >= 2)
        print("=== INGEST" + (" DRY-RUN" if dry_run else " DONE") + " ===")
        print(f"  клиник в сырье:      {len(hosts_in_run)} (новых {len(new_clinic_rows)})")
        print(f"  городов:             +{len(new_city_rows)} новых")
        print(f"  услуг (затронуто):   {len(service_rows)} (кураторских {sum(r['is_curated'] for r in service_rows)})")
        print(f"  сравнимых (>=2 клиник): {comparable}")
        print(f"  веб-цены затронутых клиник: было {web_before} -> станет {len(offer_rows)} (с ценой {sum(priced_count.values())})")
        print(f"  методы матчинга: {dict(method_stats)}")

        if dry_run:
            trans.rollback()
            print("  DRY-RUN: транзакция откачена, БД НЕ изменена")
        else:
            trans.commit()
            print("  записано в витрину")
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MedPrice — нормализация сырья из БД в витрину")
    ap.add_argument("--dry-run", action="store_true", help="показать дельты и откатить, ничего не записывая")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
