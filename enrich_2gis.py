# -*- coding: utf-8 -*-
"""
enrich_2gis.py — оценки/отзывы 2ГИС для клиник через Catalog API, МАТЧ ПО АДРЕСУ.

Главное отличие от прежней версии: у сетей много филиалов с одинаковым названием,
но разными адресами и рейтингами. Поэтому матчим НЕ по имени, а по паре
«название + адрес»: среди кандидатов 2ГИС выбираем тот, у кого совпадает улица и
НОМЕР ДОМА с нашим адресом. Если адреса нет/не совпал — берём по имени только при
высокой схожести (иначе не привязываем — лучше без рейтинга, чем чужой).

Ключи (ротация, обходим лимиты): TWOGIS_KEYS=key1,key2,...  (или один TWOGIS_KEY).
  DATABASE_URL=postgresql://loader:<pwd>@127.0.0.1:5432/medprice
  REMATCH_ALL=1   — пройти ВСЕ клиники заново (игнор дневного рефреша); иначе только
                    новые/устаревшие.
  ENRICH_LIMIT    — максимум клиник за прогон (по умолчанию 100000 при REMATCH_ALL).
"""
import datetime as dt
import difflib
import itertools
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
KEYS = [k.strip() for k in (os.environ.get("TWOGIS_KEYS") or os.environ.get("TWOGIS_KEY") or "").split(",") if k.strip()]
REMATCH_ALL = os.environ.get("REMATCH_ALL", "0") == "1"
LIMIT = int(os.environ.get("ENRICH_LIMIT", "100000" if REMATCH_ALL else "300"))
GEO_RADIUS = int(os.environ.get("GEO_RADIUS", "300"))
REFRESH_HOURS = int(os.environ.get("REFRESH_HOURS", "20"))
SLEEP = float(os.environ.get("ENRICH_SLEEP", "0.25"))   # с ротацией ключей пауза меньше
FIELDS = "items.point,items.reviews,items.address_name,items.name_ex"
PRIORITY = ["Алматы", "Астана", "Шымкент", "Караганда", "Актобе", "Атырау"]

CITY_WORDS = PRIORITY + ["Almaty", "Astana", "Shymkent", "Каскелен", "Талгар"]
_CITY_RE = re.compile(r"\b(" + "|".join(CITY_WORDS) + r")\b", re.I)
_NAME_NOISE = re.compile(r"\b(медицинский центр|клиника|поликлиника|лаборатория|центр|"
                         + "|".join(CITY_WORDS) + r")\b", re.I)
# префиксы улиц/домов (рус + каз), которые надо убрать перед сравнением адреса
_ADDR_NOISE = re.compile(r"\b(улица|ул|микрорайон|мкр|проспект|пр-т|пр|шоссе|переулок|"
                         r"пер|бульвар|б-р|дом|д|город|г|здание|блок|корпус|литер|"
                         r"көшесі|к-сі|даңғылы|даңғ|алаңы|шағын ауданы|ауданы|қ)\b\.?", re.I)
_HOUSE_RE = re.compile(r"\b(\d{1,4})\s*([а-яёa-z]?)(?:\s*/\s*(\d+))?\b", re.I)
# казахские буквы -> ближайшие русские, чтобы «Қарасай» = «Карасай» при сравнении улиц
_KZ_TRANSLIT = str.maketrans("қғңүұөһі", "кгнууохи")

_key_cycle = itertools.cycle(KEYS) if KEYS else None

SLUG = {
    "Алматы": "almaty", "Астана": "astana", "Шымкент": "shymkent", "Караганда": "karaganda",
    "Актобе": "aktobe", "Атырау": "atyrau", "Костанай": "kostanay", "Павлодар": "pavlodar",
    "Семей": "semey", "Актау": "aktau", "Кызылорда": "kyzylorda", "Уральск": "uralsk",
    "Петропавловск": "petropavlovsk", "Усть-Каменогорск": "ust-kamenogorsk", "Тараз": "taraz",
    "Туркестан": "turkestan", "Кокшетау": "kokshetau", "Талдыкорган": "taldykorgan",
    "Темиртау": "temirtau", "Экибастуз": "ekibastuz", "Рудный": "rudny", "Каскелен": "almaty",
}


def deslug(name: str) -> str:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        return " ".join(w.capitalize() for w in name.split("-") if w)
    return name


def review_link(name, city, firm_id=None):
    slug = SLUG.get(city or "")
    if firm_id and slug:
        return f"https://2gis.kz/{slug}/firm/{firm_id}/tab/reviews"
    q = urllib.parse.quote(deslug(name or ""))
    return f"https://2gis.kz/{slug}/search/{q}" if slug else f"https://2gis.kz/search/{q}"


def dsn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://")


def _name_norm(s: str) -> str:
    s = deslug(s or "").lower()
    s = _NAME_NOISE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _name_norm(a), _name_norm(b)).ratio()


def _addr_parts(addr: str):
    """address -> (set улиц-слов, базовый_номер_дома|None). '...Сеченова, 29/7' -> ({сеченова}, '29')."""
    a = (addr or "").lower().replace("–", "-").replace("—", "-")
    a = a.translate(_KZ_TRANSLIT)                        # каз. буквы -> рус. (Қарасай->карасай)
    a = _CITY_RE.sub(" ", a)
    a = _ADDR_NOISE.sub(" ", a)
    houses = [m for m in _HOUSE_RE.finditer(a)]
    house = houses[-1].group(1) if houses else None     # номер дома — обычно последнее число
    words = set(re.findall(r"[а-яёa-z]{3,}", a))
    return words, house


def addr_score(our: str, gis: str) -> float:
    """Схожесть адресов 0..1. Главный сигнал — совпадение номера дома + улицы."""
    w1, h1 = _addr_parts(our)
    w2, h2 = _addr_parts(gis)
    street = (len(w1 & w2) / max(1, min(len(w1), len(w2)))) if (w1 and w2) else 0.0
    if h1 and h2:
        if h1 == h2:
            return 0.7 + 0.3 * street          # тот же дом (+ улица) — уверенно
        return 0.25 * street                   # дом разный — почти наверняка другой филиал
    return 0.4 * street                        # дома нет — слабый сигнал по улице


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000; p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def call(params: dict):
    key = next(_key_cycle)
    params = {**params, "key": key, "fields": FIELDS, "page_size": 10}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "MedPriceKZ/1.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    except Exception as e:
        # при лимите/ошибке пробуем следующий ключ один раз
        try:
            key2 = next(_key_cycle)
            url2 = API + "?" + urllib.parse.urlencode({**params, "key": key2})
            data = json.loads(urllib.request.urlopen(
                urllib.request.Request(url2, headers={"User-Agent": "MedPriceKZ/1.0"}), timeout=20).read().decode())
        except Exception as e2:
            print(f"  ! API error: {e2}")
            return []
    return (data.get("result") or {}).get("items") or []


def best_match(clinic_name, city, address, lat, lng):
    """Выбор организации 2ГИС по ИМЕНИ+АДРЕСУ. None, если уверенного совпадения нет."""
    q = " ".join(filter(None, [deslug(clinic_name), city]))
    candidates = call({"q": q})
    if not candidates and address:
        candidates = call({"q": " ".join(filter(None, [deslug(clinic_name), address]))})

    have_house = _addr_parts(address)[1] is not None
    best, best_score, best_addr = None, 0.0, 0.0
    for it in candidates:
        nm = it.get("name") or ""
        ns = name_sim(clinic_name, nm)
        as_ = addr_score(address, it.get("address_name") or "") if address else 0.0
        # гео-подтверждение
        geo = 0.0
        pt = it.get("point") or {}
        if lat is not None and pt.get("lat") is not None:
            d = haversine(lat, lng, pt["lat"], pt["lon"])
            if d < GEO_RADIUS:
                geo = 1 - d / GEO_RADIUS
        # итоговый скор: если есть адрес — он главный; иначе имя+гео
        if have_house:
            score = 0.65 * as_ + 0.25 * ns + 0.10 * geo
        else:
            score = 0.55 * ns + 0.45 * geo
        if score > best_score:
            best_score, best, best_addr = score, it, as_

    if not best:
        return None
    # порог принятия: с адресом требуем совпадение дома (as_>=0.7) ИЛИ сильное гео+имя;
    # без адреса — высокую схожесть имени.
    if have_house:
        ok = best_addr >= 0.7
    else:
        ok = name_sim(clinic_name, best.get("name") or "") >= 0.72 or best_score >= 0.7
    if not ok:
        return None
    rv = best.get("reviews") or {}
    rating = rv.get("general_rating")
    pt = best.get("point") or {}
    return {
        "rating": float(rating) if rating is not None else None,
        "reviews": int(rv.get("general_review_count") or 0) if rating is not None else None,
        "id": best.get("id"),
        "matched_name": best.get("name"),
        "matched_addr": best.get("address_name"),
        "lat": pt.get("lat"), "lng": pt.get("lon"),
    }


def main():
    if not KEYS:
        sys.exit("ERROR: задай TWOGIS_KEYS (ключи Catalog API через запятую)")
    now = dt.datetime.utcnow()
    print(f"ключей: {len(KEYS)}, режим: {'ВСЕ ЗАНОВО' if REMATCH_ALL else 'обычный рефреш'}, лимит: {LIMIT}")
    with psycopg.connect(dsn(), prepare_threshold=None) as conn:
        cur = conn.cursor()
        if REMATCH_ALL:
            cur.execute(
                "SELECT cl.id, cl.name, c.name, cl.address, cl.lat, cl.lng "
                "FROM clinics cl LEFT JOIN cities c ON c.id=cl.city_id "
                "ORDER BY cl.id LIMIT %s", (LIMIT,))
        else:
            cutoff = now - dt.timedelta(hours=REFRESH_HOURS)
            cur.execute(
                "SELECT cl.id, cl.name, c.name, cl.address, cl.lat, cl.lng "
                "FROM clinics cl LEFT JOIN cities c ON c.id=cl.city_id "
                "WHERE cl.rating_updated_at IS NULL OR cl.rating_updated_at < %s "
                "ORDER BY cl.rating_updated_at NULLS FIRST LIMIT %s", (cutoff, LIMIT))
        rows = cur.fetchall()
        print(f"к обработке: {len(rows)}")
        done = matched = rated = 0
        for cid, cname, ccity, addr, lat, lng in rows:
            m = best_match(cname, ccity, addr, lat, lng)
            done += 1
            if m:
                matched += 1
                if m["rating"] is not None:
                    rated += 1
                cur.execute(
                    "UPDATE clinics SET rating=%s, reviews_count=%s, twogis_id=%s, twogis_url=%s, "
                    "lat=COALESCE(%s, lat), lng=COALESCE(%s, lng), rating_updated_at=%s WHERE id=%s",
                    (m["rating"], m["reviews"], m["id"], review_link(cname, ccity, m["id"]),
                     m["lat"], m["lng"], now, cid))
            else:
                # не нашли уверенно — сбрасываем привязку к фирме, оставляем ссылку-поиск
                cur.execute(
                    "UPDATE clinics SET rating=NULL, reviews_count=NULL, twogis_id=NULL, "
                    "twogis_url=%s, rating_updated_at=%s WHERE id=%s",
                    (review_link(cname, ccity, None), now, cid))
            conn.commit()
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}: привязано {matched}, с рейтингом {rated}", flush=True)
            time.sleep(SLEEP)
    print(f"=== ГОТОВО: обработано {done}, привязано {matched}, с рейтингом {rated} ===")


if __name__ == "__main__":
    main()
