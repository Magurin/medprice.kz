"""
ingest.py — превращает «сырьё» харвестера в нормализованную БД.

Пайплайн (это и есть «кейс 1» внутри «кейса 2»):
    raw/clinics.jsonl + raw/offers.jsonl
        -> нормализация и матчинг каждой позиции (app/normalize.Matcher)
        -> канонические услуги (кураторские + авто из данных)
        -> SQLite (cities / clinics / services / price_offers)

Bulk-вставка через DBAPI executemany — быстро даже на сотнях тысяч строк.

Запуск:  python -m app.ingest
"""
import json
import os
from collections import defaultdict

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


def run():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    matcher = Matcher()

    # --- города + клиники (dedupe по host) ---
    cities: dict[str, int] = {}

    def city_id(name):
        name = (name or "Не указан").strip() or "Не указан"
        if name not in cities:
            cities[name] = len(cities) + 1
        return cities[name]

    host_to_id: dict[str, int] = {}
    clinic_rows = []
    cid = 0
    for c in _iter_jsonl(os.path.join(RAW, "clinics.jsonl")):
        if c["host"] in host_to_id:
            continue
        cid += 1
        host_to_id[c["host"]] = cid
        clinic_rows.append((cid, c["host"], c["name"], city_id(c.get("city")),
                            c.get("address"), c.get("source_url")))
    city_rows = [(i, n) for n, i in cities.items()]

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
        offer_rows.append((
            oid, clinic_id, sid, o["raw_name"], o.get("price"), o.get("currency", "KZT"),
            int(bool(o.get("is_from"))), int(bool(o.get("on_request"))),
            m["method"], m["score"],
        ))
        if o.get("price") is not None:
            priced_count[sid] += 1
            clinics_of[sid].add(clinic_id)

    service_rows = [
        (sid, code, name, cat, int(is_cur), meth, priced_count[sid], len(clinics_of[sid]))
        for code, (sid, name, cat, is_cur, meth) in svc.items()
    ]

    # --- bulk insert ---
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("PRAGMA synchronous=OFF")
        cur.execute("PRAGMA journal_mode=MEMORY")
        cur.executemany("INSERT INTO cities (id,name) VALUES (?,?)", city_rows)
        cur.executemany(
            "INSERT INTO clinics (id,host,name,city_id,address,source_url) VALUES (?,?,?,?,?,?)",
            clinic_rows)
        cur.executemany(
            "INSERT INTO services (id,code,name,category,is_curated,match_method,n_offers,n_clinics) "
            "VALUES (?,?,?,?,?,?,?,?)", service_rows)
        cur.executemany(
            "INSERT INTO price_offers "
            "(id,clinic_id,service_id,raw_name,price,currency,is_from,on_request,match_method,match_score) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", offer_rows)
        raw.commit()
    finally:
        raw.close()

    comparable = sum(1 for code, (sid, *_ ) in svc.items() if len(clinics_of[sid]) >= 2)
    print("=== INGEST DONE ===")
    print(f"  города:    {len(city_rows)}")
    print(f"  клиники:   {len(clinic_rows)}")
    print(f"  услуги:    {len(service_rows)}  (кураторских: {sum(r[4] for r in service_rows)})")
    print(f"  сравнимых услуг (>=2 клиник): {comparable}")
    print(f"  ценовых предложений: {len(offer_rows)}  (с ценой: {sum(priced_count.values())})")
    print(f"  методы матчинга: {dict(method_stats)}")


if __name__ == "__main__":
    run()
