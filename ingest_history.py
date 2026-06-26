# -*- coding: utf-8 -*-
"""
ingest_history.py — история цен из архивных прайсов «Хакатон/».

В отличие от ingest_files.py (берёт по одному «лучшему» файлу на клинику), здесь
парсим ВСЕ файлы и проставляем год из имени файла -> точки в price_history.
Реальная история: Клиника 1 (2024+2026) и Клиника 2 (2025+2026) дают по 2 точки,
остальные — по одной. Привязка к тем же file-клиникам (host = file-clinic-N).

Идемпотентно: пере-запуск очищает price_history.
Запуск:
  set DATABASE_URL=postgresql://loader.<ref>:<pwd>@<host>:5432/postgres
  python ingest_history.py
"""
import datetime as dt
import os
import re
import sys

import psycopg

from app.catalog import ReferenceMatcher
from app.fileparse import parse_file, TARIF_RE

ROOT = os.path.dirname(os.path.abspath(__file__))
HToc = os.path.join(ROOT, "Хакатон")

CLINIC_RE = re.compile(r"Клиника\s*(\d+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(20\d{2})")


def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL (Postgres, сессионный пулер :5432)")
    return url.replace("postgresql+psycopg://", "postgresql://")


def discover():
    """[(clinic_no, year, filename), ...] из имён файлов архива."""
    out = []
    for fn in sorted(os.listdir(HToc)):
        if fn.startswith("~$"):
            continue
        cm, ym = CLINIC_RE.search(fn), YEAR_RE.search(fn)
        if cm and ym:
            out.append((int(cm.group(1)), int(ym.group(1)), fn))
    return out


def main():
    matcher = ReferenceMatcher()
    files = discover()
    print("Найдено файлов с (клиника, год):")
    for n, y, fn in files:
        print(f"  Клиника {n}  {y}  <- {fn}")

    with psycopg.connect(dsn(), sslmode="require", prepare_threshold=None) as conn:
        cur = conn.cursor()

        # file-клиники должны быть уже загружены (ingest_files.py)
        cur.execute("SELECT host, id FROM clinics WHERE source_type='file'")
        host_to_id = dict(cur.fetchall())
        if not host_to_id:
            sys.exit("ERROR: нет file-клиник в БД. Сначала запусти ingest_files.py")

        # справочник: ref_id -> service_id
        cur.execute("SELECT code, id FROM services WHERE is_reference=true")
        code_to_sid = dict(cur.fetchall())  # code = 'ref:<ref_id>'

        cur.execute("DELETE FROM price_history")
        conn.commit()

        total = 0
        for n, year, fn in files:
            host = f"file-clinic-{n}"
            clinic_id = host_to_id.get(host)
            if not clinic_id:
                print(f"  ! пропуск {fn}: нет клиники {host}")
                continue
            recorded = dt.datetime(year, 1, 1)
            try:
                recs = parse_file(os.path.join(HToc, fn))
            except Exception as e:
                print(f"  ! {fn}: parse error {type(e).__name__}: {e}")
                continue

            rows, seen = [], set()
            for r in recs:
                if not r.get("price"):
                    continue
                code = r.get("code")
                tarif = code if (code and TARIF_RE.search(str(code))) else None
                m = matcher.match(r["raw_name"], tarif)
                if not m:
                    continue
                sid = code_to_sid.get(f"ref:{m['ref_id']}")
                if not sid or sid in seen:   # одна (первая) цена на услугу в этом файле
                    continue
                seen.add(sid)
                rows.append((clinic_id, sid, int(r["price"]), recorded, fn, r["raw_name"]))

            if rows:
                cur.executemany(
                    "INSERT INTO price_history (clinic_id,service_id,price,recorded_at,source_file,raw_name) "
                    "VALUES (%s,%s,%s,%s,%s,%s)", rows)
                conn.commit()
            total += len(rows)
            print(f"  Клиника {n} {year}: точек истории +{len(rows)}")

        # сколько услуг имеют >=2 точек (есть тренд)
        cur.execute("""
            SELECT count(*) FROM (
              SELECT service_id, clinic_id FROM price_history
              GROUP BY service_id, clinic_id HAVING count(*) >= 2) t
        """)
        trends = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM price_history")
        ph = cur.fetchone()[0]
    print(f"\n=== ГОТОВО: price_history={ph}  (пар клиника+услуга с трендом >=2 точек: {trends}) ===")


if __name__ == "__main__":
    main()
