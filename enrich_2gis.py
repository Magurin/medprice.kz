# -*- coding: utf-8 -*-
"""
enrich_2gis.py — оценки и отзывы 2ГИС для клиник через Catalog API.

Для каждой клиники ищем организацию в 2ГИС (по названию+городу, при наличии —
сверяем с координатами), берём reviews.general_rating / general_review_count и
ссылку на карточку. Матч принимается только при достаточной схожести названия
ИЛИ близости координат — чтобы не прилепить чужой рейтинг.

Требуется ключ Catalog API (dev.2gis.ru):
  set TWOGIS_KEY=...
  set DATABASE_URL=postgresql://loader.<ref>:<pwd>@<host>:5432/postgres
  python enrich_2gis.py

Параметры окружения:
  TWOGIS_KEY      — ключ Catalog API (обязателен)
  ENRICH_LIMIT    — сколько клиник обработать за прогон (по умолчанию 300)
  NAME_THRESHOLD  — порог схожести имени 0..1 (по умолчанию 0.55)
  GEO_RADIUS      — радиус гео-поиска, м (по умолчанию 400)
"""
import datetime as dt
import difflib
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import psycopg

API = "https://catalog.api.2gis.com/3.0/items"
KEY = os.environ.get("TWOGIS_KEY")
LIMIT = int(os.environ.get("ENRICH_LIMIT", "300"))
NAME_THRESHOLD = float(os.environ.get("NAME_THRESHOLD", "0.55"))
GEO_RADIUS = int(os.environ.get("GEO_RADIUS", "400"))
PRIORITY = ["Алматы", "Астана", "Шымкент", "Караганда", "Актобе", "Атырау"]
FIELDS = "items.point,items.reviews,items.address_name,items.name_ex"

# город-суффикс и слаговый мусор в названиях клиник
CITY_WORDS = "|".join(PRIORITY + ["Almaty", "Astana", "Shymkent"])
NOISE_RE = re.compile(r"\b(медицинский центр|клиника|лаборатория|центр|"
                      rf"{CITY_WORDS})\b", re.IGNORECASE)


REFRESH_HOURS = int(os.environ.get("REFRESH_HOURS", "20"))  # дневной рефреш рейтинга

# город -> слаг 2gis.kz (для ссылок на отзывы без ключа)
SLUG = {
    "Алматы": "almaty", "Астана": "astana", "Шымкент": "shymkent", "Караганда": "karaganda",
    "Актобе": "aktobe", "Атырау": "atyrau", "Костанай": "kostanay", "Павлодар": "pavlodar",
    "Семей": "semey", "Актау": "aktau", "Кызылорда": "kyzylorda", "Уральск": "uralsk",
    "Петропавловск": "petropavlovsk", "Усть-Каменогорск": "ust-kamenogorsk", "Тараз": "taraz",
    "Туркестан": "turkestan", "Кокшетау": "kokshetau", "Талдыкорган": "taldykorgan",
    "Темиртау": "temirtau", "Экибастуз": "ekibastuz", "Рудный": "rudny",
}


def review_link(name, city, firm_id=None):
    """Ссылка на отзывы в 2ГИС. С firm_id — прямо на вкладку отзывов; иначе поиск."""
    slug = SLUG.get(city or "")
    if firm_id and slug:
        return f"https://2gis.kz/{slug}/firm/{firm_id}/tab/reviews"
    q = urllib.parse.quote(deslug(name))
    return f"https://2gis.kz/{slug}/search/{q}" if slug else f"https://2gis.kz/search/{q}"


def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://")


def deslug(name: str) -> str:
    """Слаги вида 'gorodskaja-poliklinika-5' -> читабельно; нормальные имена не трогаем."""
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        return " ".join(w.capitalize() for w in name.split("-") if w)
    return name


def norm(s: str) -> str:
    s = deslug(s or "").lower()
    s = NOISE_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def call(params: dict):
    params = {**params, "key": KEY, "fields": FIELDS, "page_size": 5}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MedPriceKZ/1.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except Exception as e:
        print(f"  ! API error: {e}")
        return []
    return (data.get("result") or {}).get("items") or []


def best_match(clinic_name, city, lat, lng):
    """Возвращает dict(rating, reviews, id, lat, lng) или None.

    Координаты 2ГИС (point) точны для адресов РК (микрорайоны, литеры домов),
    где Nominatim почти всегда промахивается — поэтому геокодим заодно с рейтингом.
    """
    candidates = []
    q = " ".join(filter(None, [deslug(clinic_name), city]))
    candidates += call({"q": q})
    # гео-запрос — только если по имени ничего (бережём лимит демо-ключа: 1 запрос/клинику)
    if not candidates and lat is not None and lng is not None:
        candidates += call({"q": deslug(clinic_name), "point": f"{lng},{lat}",
                            "radius": GEO_RADIUS, "type": "branch,building"})

    best, best_score = None, 0.0
    for it in candidates:
        name = it.get("name") or ""
        ns = similar(clinic_name, name)
        score = ns
        # бонус за близость координат
        pt = it.get("point") or {}
        if lat is not None and pt.get("lat") is not None:
            d = haversine(lat, lng, pt["lat"], pt["lon"])
            if d < GEO_RADIUS:
                score = max(score, 0.6) + 0.3 * (1 - d / GEO_RADIUS)
        if score > best_score:
            best_score, best = score, it

    if not best or best_score < NAME_THRESHOLD:
        return None
    rv = best.get("reviews") or {}
    rating = rv.get("general_rating")
    pt = best.get("point") or {}
    # рейтинг может отсутствовать, но координаты/id у совпавшей организации есть
    return {
        "rating": float(rating) if rating is not None else None,
        "reviews": int(rv.get("general_review_count") or 0) if rating is not None else None,
        "id": best.get("id"),
        "lat": pt.get("lat"),
        "lng": pt.get("lon"),
    }


def main():
    now = dt.datetime.utcnow()
    with psycopg.connect(dsn(), sslmode="require", prepare_threshold=None) as conn:
        cur = conn.cursor()

        # ---- фаза 1: ссылки на отзывы 2ГИС для всех (без ключа) ----
        # не перетираем ссылки, уже привязанные к конкретной организации (twogis_id есть)
        cur.execute(
            "SELECT cl.id, cl.name, c.name FROM clinics cl LEFT JOIN cities c ON c.id=cl.city_id "
            "WHERE cl.twogis_id IS NULL")
        link_rows = cur.fetchall()
        cur.executemany("UPDATE clinics SET twogis_url=%s WHERE id=%s",
                        [(review_link(n, c), cid) for cid, n, c in link_rows])
        conn.commit()
        print(f"фаза 1: ссылки на отзывы 2ГИС у {len(link_rows)} клиник (без ключа)")

        if not KEY:
            print("фаза 2 пропущена: нет TWOGIS_KEY -> рейтинги не заполняются "
                  "(ссылки на отзывы уже работают). Бесплатный ключ: dev.2gis.com; "
                  "затем запускать раз в сутки (cron) для динамики.")
            return

        # ---- фаза 2: рейтинг + число отзывов (ключ); дневной рефреш ----
        cutoff = now - dt.timedelta(hours=REFRESH_HOURS)
        done = ok = geo = 0
        remaining = LIMIT
        for city in PRIORITY + [None]:
            if remaining <= 0:
                break
            if city:
                cur.execute(
                    "SELECT cl.id, cl.name, c.name, cl.lat, cl.lng FROM clinics cl "
                    "JOIN cities c ON c.id=cl.city_id WHERE c.name=%s "
                    "AND (cl.rating_updated_at IS NULL OR cl.rating_updated_at < %s) "
                    "ORDER BY cl.rating_updated_at NULLS FIRST LIMIT %s", (city, cutoff, remaining))
            else:
                cur.execute(
                    "SELECT cl.id, cl.name, NULL, cl.lat, cl.lng FROM clinics cl "
                    "WHERE (cl.rating_updated_at IS NULL OR cl.rating_updated_at < %s) "
                    "ORDER BY cl.rating_updated_at NULLS FIRST LIMIT %s", (cutoff, remaining))
            rows = cur.fetchall()
            if not rows:
                continue
            print(f"[{city or 'прочие'}] к обработке: {len(rows)}", flush=True)
            for cid, cname, ccity, lat, lng in rows:
                m = best_match(cname, ccity, lat, lng)
                done += 1
                remaining -= 1
                rating = m["rating"] if m else None
                reviews = m["reviews"] if m else None
                fid = m["id"] if m else None
                mlat = m["lat"] if m else None
                mlng = m["lng"] if m else None
                # координаты 2ГИС точнее — перезаписываем, если пришли; иначе храним прежние
                cur.execute(
                    "UPDATE clinics SET rating=%s, reviews_count=%s, twogis_id=%s, "
                    "twogis_url=%s, lat=COALESCE(%s, lat), lng=COALESCE(%s, lng), "
                    "rating_updated_at=%s WHERE id=%s",
                    (rating, reviews, fid, review_link(cname, ccity, fid),
                     mlat, mlng, now, cid))
                conn.commit()
                if rating is not None:
                    ok += 1
                if mlat is not None:
                    geo += 1
                if done % 25 == 0:
                    print(f"  {done} обработано, {ok} с рейтингом, {geo} с координатами", flush=True)
                time.sleep(1.2)  # бережём демо-ключ от блокировки
                if remaining <= 0:
                    break
        cur.execute("SELECT count(*) FROM clinics WHERE rating IS NOT NULL")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM clinics WHERE lat IS NOT NULL")
        total_geo = cur.fetchone()[0]
    print(f"=== ГОТОВО: обработано {done}, с рейтингом {ok} (+{geo} координат); "
          f"в БД с рейтингом {total}, с координатами {total_geo} ===")


if __name__ == "__main__":
    main()
