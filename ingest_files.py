# -*- coding: utf-8 -*-
"""
ingest_files.py — загрузка приложенного архива прайсов (8 клиник) в Postgres.

Пайплайн (кейс 1):
  Справочник услуг -> services(is_reference=true)
  8 файлов -> парсеры -> матчинг (код тарификатора -> имя -> нечёткий)
       -> price_offers(source_type='file'); непривязанное -> unmatched_queue
  журнал -> parse_log; пересчёт n_offers/n_clinics.

Идемпотентно: при пере-запуске удаляет прежние file-данные.
Запуск:
  set DATABASE_URL=postgresql://loader.<ref>:<pwd>@<host>:5432/postgres
  python ingest_files.py
"""
import datetime as dt
import json
import os
import re
import sys

import psycopg

from app.catalog import ReferenceMatcher
from app.fileparse import parse_file, TARIF_RE

ROOT = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(ROOT, "app", "data", "reference_services.json")
HToc = os.path.join(ROOT, "Хакатон")

# Лучший файл на клинику + город (если известен)
CLINICS = [
    (1, "Клиника 1", "Не указан",  "Клиника 1 прайс 2024.docx"),
    (2, "Клиника 2", "Не указан",  "Клиника 2 прайс 2026.pdf"),
    (3, "Клиника 3", "Не указан",  "Клиника 3 прайс 2026.PDF"),
    (4, "Клиника 4", "Не указан",  "Клиника 4 прайс 2026.pdf"),
    (5, "Клиника 5", "Не указан",  "Клиника 5 прайс 2025.pdf"),
    (6, "Клиника 6 (University Medical Center)", "Астана", "Клиника 6 прайс 2026.xlsx"),
    (7, "Клиника 7", "Не указан",  "Клиника 7_Прайс 2026.xls"),
    (8, "Клиника 8 (ННМЦ)", "Астана", "Клиника 8 2026.xlsx"),
]


def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL (Postgres, сессионный пулер :5432)")
    return url.replace("postgresql+psycopg://", "postgresql://")


def maxid(cur, table):
    cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
    return cur.fetchone()[0]


def main():
    matcher = ReferenceMatcher()
    ref_services = json.load(open(REF, encoding="utf-8"))["services"]
    now = dt.datetime.now()

    with psycopg.connect(dsn(), sslmode="require", prepare_threshold=None) as conn:
        cur = conn.cursor()

        # 0) чистим прежние file-данные
        cur.execute("DELETE FROM price_offers WHERE source_type = 'file'")
        cur.execute("DELETE FROM unmatched_queue")
        cur.execute("DELETE FROM clinics WHERE source_type = 'file'")
        cur.execute("DELETE FROM parse_log")
        conn.commit()

        # 1) справочник -> services(is_reference) [insert-if-missing]
        cur.execute("SELECT code, id FROM services WHERE is_reference = true")
        existing = dict(cur.fetchall())
        sid = maxid(cur, "services")
        new_rows = []
        refid_to_sid = {}
        for s in ref_services:
            code = f"ref:{s['ref_id']}"
            if code in existing:
                refid_to_sid[s["ref_id"]] = existing[code]
                continue
            sid += 1
            refid_to_sid[s["ref_id"]] = sid
            new_rows.append((sid, code, s["name"], s["category"], False, True,
                             s.get("tarificator"), s.get("specialty"), 0, 0))
        if new_rows:
            cur.executemany(
                "INSERT INTO services (id,code,name,category,is_curated,is_reference,"
                "tarificator_code,specialty,n_offers,n_clinics) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                new_rows)
        conn.commit()
        print(f"справочные услуги: +{len(new_rows)} (всего ref в БД: {len(existing) + len(new_rows)})")

        # 2) города (по имени) + клиники
        cur.execute("SELECT name, id FROM cities")
        cities = dict(cur.fetchall())
        cid_city = maxid(cur, "cities")
        for _, _, city, _ in CLINICS:
            if city not in cities:
                cid_city += 1
                cur.execute("INSERT INTO cities (id,name) VALUES (%s,%s)", (cid_city, city))
                cities[city] = cid_city
        conn.commit()

        clinic_id = maxid(cur, "clinics")
        clinic_map = {}
        for n, name, city, _ in CLINICS:
            clinic_id += 1
            clinic_map[n] = clinic_id
            cur.execute(
                "INSERT INTO clinics (id,host,name,city_id,source_type) VALUES (%s,%s,%s,%s,'file')",
                (clinic_id, f"file-clinic-{n}", name, cities[city]))
        conn.commit()

        # 3) парсинг + матчинг
        oid = maxid(cur, "price_offers")
        total_off = total_unm = 0
        for n, name, city, fname in CLINICS:
            path = os.path.join(HToc, fname)
            note = ""
            try:
                recs = parse_file(path)
            except Exception as e:
                recs = []
                note = f"parse error: {type(e).__name__}: {e}"
            offers, unm = [], []
            for r in recs:
                if not r.get("price"):
                    continue
                code = r.get("code")
                tarif = code if (code and TARIF_RE.search(str(code))) else None
                m = matcher.match(r["raw_name"], tarif)
                if m:
                    oid += 1
                    offers.append((oid, clinic_map[n], refid_to_sid[m["ref_id"]], r["raw_name"],
                                   r["price"], "KZT", m["method"], m["score"], "file",
                                   tarif, now, True))
                else:
                    unm.append((clinic_map[n], r["raw_name"], code, r["price"], fname))
            if offers:
                cur.executemany(
                    "INSERT INTO price_offers (id,clinic_id,service_id,raw_name,price,currency,"
                    "match_method,match_score,source_type,tarificator_code,parsed_at,is_active) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", offers)
            if unm:
                cur.executemany(
                    "INSERT INTO unmatched_queue (clinic_id,raw_name,code,price,source_file) "
                    "VALUES (%s,%s,%s,%s,%s)", unm)
            cur.execute(
                "INSERT INTO parse_log (source_file,clinic,rows_total,rows_matched,rows_unmatched,note) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (fname, name, len(recs), len(offers), len(unm), note or None))
            conn.commit()
            total_off += len(offers); total_unm += len(unm)
            print(f"  {name:42s} строк={len(recs):5d}  matched={len(offers):5d}  unmatched={len(unm):5d}  {note}")

        # 4) пересчёт счётчиков услуг
        cur.execute("""
            UPDATE services s SET n_offers = sub.cnt, n_clinics = sub.cl
            FROM (SELECT service_id, count(*) cnt, count(DISTINCT clinic_id) cl
                  FROM price_offers WHERE price IS NOT NULL GROUP BY service_id) sub
            WHERE s.id = sub.service_id
        """)
        conn.commit()

        cur.execute("SELECT count(*) FROM price_offers WHERE source_type='file'")
        pf = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM services WHERE is_reference=true AND n_clinics>=2")
        rc = cur.fetchone()[0]
        print(f"\n=== ГОТОВО: file-offers={pf}  unmatched={total_unm}  "
              f"сравнимых справочных услуг (>=2 клиник)={rc} ===")


if __name__ == "__main__":
    main()
