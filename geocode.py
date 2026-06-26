# -*- coding: utf-8 -*-
"""
geocode.py — геокодинг адресов клиник (адрес -> lat/lng) через Nominatim (OSM).

Бесплатно, без ключа. Соблюдаем fair-use: 1 запрос/сек, корректный User-Agent,
дедуп по адресу, приоритет крупных городов, общий лимит. Координаты затем
рисуются на любой карте (2ГИС MapGL и т.п.).

Запуск:
  set DATABASE_URL=postgresql://loader.<ref>:<pwd>@<host>:5432/postgres
  python geocode.py
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import psycopg

PRIORITY = ["Алматы", "Астана", "Шымкент", "Караганда", "Актобе", "Атырау"]
LIMIT = int(os.environ.get("GEOCODE_LIMIT", "700"))
UA = {"User-Agent": "MedPriceKZ/1.0 (hackathon project; faruhitakdaleevic@gmail.com)"}


def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL (Postgres :5432)")
    return url.replace("postgresql+psycopg://", "postgresql://")


def geocode(addr):
    q = addr if "казахстан" in addr.lower() else addr + ", Казахстан"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "limit": 1})
    try:
        req = urllib.request.Request(url, headers=UA)
        data = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None
    return None


def main():
    done = ok = 0
    with psycopg.connect(dsn(), sslmode="require", prepare_threshold=None) as conn:
        cur = conn.cursor()
        remaining = LIMIT
        for city in PRIORITY:
            if remaining <= 0:
                break
            cur.execute(
                "SELECT DISTINCT cl.address FROM clinics cl JOIN cities c ON c.id=cl.city_id "
                "WHERE c.name=%s AND cl.address IS NOT NULL AND cl.lat IS NULL LIMIT %s",
                (city, remaining))
            addrs = [r[0] for r in cur.fetchall()]
            print(f"[{city}] адресов к геокодингу: {len(addrs)}", flush=True)
            for a in addrs:
                coord = geocode(a)
                done += 1
                remaining -= 1
                if coord:
                    cur.execute("UPDATE clinics SET lat=%s, lng=%s WHERE address=%s",
                                (coord[0], coord[1], a))
                    conn.commit()
                    ok += 1
                if done % 50 == 0:
                    print(f"  {done} обработано, {ok} с координатами", flush=True)
                time.sleep(1.1)
                if remaining <= 0:
                    break
        cur.execute("SELECT count(*) FROM clinics WHERE lat IS NOT NULL")
        total = cur.fetchone()[0]
    print(f"=== ГЕОКОДИНГ: обработано {done}, успешно {ok}; всего с координатами в БД: {total} ===")


if __name__ == "__main__":
    main()
