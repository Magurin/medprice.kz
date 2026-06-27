"""
harvest.py — массовый сбор прайс-листов клиник РК с сети 103.kz.

Для каждого хоста из frontier.txt качает <host>/pricing/ и вынимает позиции
прайса по единому шаблону портала:
    .PersonalOffers__item
        .PersonalOffers__title   -> название услуги (как у клиники, «сырое»)
        .PersonalOffers__price   -> цена («1 790 тенге», «от 2 000 тенге», «уточняйте»)

Имя/город/адрес/телефон/часы работы клиники берём из встроенного JSON-LD
(<script type="application/ld+json"> -> LocalBusiness): там всегда лежат чистые
поля name / address.streetAddress / addressLocality / telephone /
openingHoursSpecification. Это снимает мусор вида «invitro-6», «gemotest-4»
(раньше имя добывалось из <title>, а для лабораторий шаблон не совпадал и
происходил откат к слагу хоста). Если JSON-LD нет — мягкий откат к <title>/<h1>
и DOM-элементам адреса/времени, но НИКОГДА к нумерованному слагу хоста.

Многопоточно (ThreadPoolExecutor), докачиваемо (пропускает хосты из _done.txt),
устойчиво к ошибкам отдельных клиник.

Выход (JSONL, по строке на запись):
    raw/clinics.jsonl  — {host, name, brand, street, city, address, phone,
                          working_hours, source_url, n_offers}
    raw/offers.jsonl   — {host, raw_name, category, price, currency, is_from, on_request}

Имя бренда («Гемотест», «INVITRO (ИНВИТРО)») у сетей одинаково на всех филиалах —
различение филиалов по улице делает потребитель (app/ingest.py): если бренд
встречается в ≥2 клиниках, к имени добавляется улица из street.

Запуск:
    python harvester/harvest.py --limit 300 --workers 24
    python harvester/harvest.py            # всё, что осталось во фронтире
"""
import argparse
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
UA = {"User-Agent": "Mozilla/5.0 (compatible; MedPriceBot/1.0; research)"}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# Города РК для распознавания + нормализация дублей
CITIES = [
    "Алматы", "Астана", "Нур-Султан", "Шымкент", "Караганда", "Актобе",
    "Тараз", "Павлодар", "Усть-Каменогорск", "Семей", "Атырау", "Костанай",
    "Кызылорда", "Уральск", "Петропавловск", "Актау", "Темиртау", "Туркестан",
    "Кокшетау", "Талдыкорган", "Экибастуз", "Рудный", "Жезказган", "Балхаш",
    "Кентау", "Сатпаев", "Риддер", "Жанаозен", "Степногорск",
]
CITY_CANON = {"Нур-Султан": "Астана", "Нур-султан": "Астана"}


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25, context=_ctx) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return None


_NUM = re.compile(r"\d[\d\s ]*")


def parse_price(text: str):
    """('1 790 тенге'|'от 2 000 тенге'|'уточняйте') -> (price|None, is_from, on_request)."""
    t = (text or "").replace(" ", " ").strip()
    low = t.lower()
    m = _NUM.search(t)
    if not m:
        return None, False, True
    price = int(re.sub(r"\D", "", m.group(0)))
    is_from = low.startswith("от") or " от " in low
    return price, is_from, False


def detect_city(soup: BeautifulSoup, title: str) -> str | None:
    # 1) элемент адреса: "Алматы, мкр. ..."
    el = soup.select_one("[class*=address], [class*=Address]")
    if el:
        head = el.get_text(" ", strip=True).split(",")[0].strip()
        head = re.sub(r"^г\.\s*", "", head)  # "г. Каскелен" -> "Каскелен"
        for c in CITIES:
            if head.lower().startswith(c.lower()):
                return CITY_CANON.get(c, c)
    # 2) из <title>: "... центр Алматы - ..."
    for c in CITIES:
        if re.search(r"\b" + re.escape(c) + r"\b", title, re.IGNORECASE):
            return CITY_CANON.get(c, c)
    return None


# --- имя клиники из <title>/<h1> (мягкий откат, когда нет JSON-LD) ---
_CENY_HEAD = re.compile(r"^\s*цены\s*[-–—|:]\s*", re.IGNORECASE)
_PRICE_TAIL = re.compile(
    r"\s*[-–—|]\s*(?:стоимость|прайс[\s-]?лист|прейскурант|цены|услуги|анализы)\b.*$",
    re.IGNORECASE,
)


def _deslug(host: str) -> str:
    """'gorodskaja-poliklinika-5' -> 'Gorodskaja Poliklinika' (БЕЗ хвостового номера филиала)."""
    base = host.replace(".103.kz", "")
    base = re.sub(r"-\d+$", "", base)            # отрезаем '-6', '-12' и т.п.
    base = re.sub(r"-(kz|kazahstan|kz\d+)$", "", base, flags=re.IGNORECASE) or base
    words = [w for w in base.split("-") if w]
    return " ".join(w.capitalize() for w in words) or host.replace(".103.kz", "")


def clinic_name(title: str, h1: str, host: str) -> str:
    """Чистое имя из <title>/<h1>. Никогда не возвращает нумерованный слаг хоста."""
    for src in (title, h1):
        if not src:
            continue
        s = _CENY_HEAD.sub("", src)
        s = _PRICE_TAIL.sub("", s).strip(" -–—|·")
        if len(s) >= 2 and not re.fullmatch(r"[-–—\s·]*", s):
            return s
    return _deslug(host)


# --- JSON-LD (schema.org) ---
def _iter_ld(soup: BeautifulSoup):
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = s.string or s.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                g = x.get("@graph")
                if isinstance(g, list):
                    stack.extend(g)
                yield x


def _localbusiness(soup: BeautifulSoup) -> dict | None:
    """LocalBusiness/Medical* блок с именем и адресом — основной источник полей клиники."""
    for x in _iter_ld(soup):
        t = x.get("@type")
        types = t if isinstance(t, list) else [t]
        ok = any(
            str(tt).endswith("LocalBusiness") or str(tt).startswith("Medical")
            or tt in ("Hospital", "Pharmacy", "Dentist", "Physician")
            for tt in types
        )
        if ok and x.get("name") and x.get("address"):
            return x
    return None


_DOW = {
    "monday": "Пн", "tuesday": "Вт", "wednesday": "Ср", "thursday": "Чт",
    "friday": "Пт", "saturday": "Сб", "sunday": "Вс",
}
_DOW_ORDER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _fmt_hours(spec) -> str | None:
    """openingHoursSpecification -> 'Пн–Пт 07:00–12:00, Сб 08:00–11:00' (соседние дни схлопываем)."""
    if not spec:
        return None
    if isinstance(spec, dict):
        spec = [spec]
    byday: dict[str, tuple[str, str]] = {}
    for s in spec:
        if not isinstance(s, dict):
            continue
        dw = s.get("dayOfWeek")
        days = dw if isinstance(dw, list) else [dw]
        o = (s.get("opens") or "").strip()[:5]
        c = (s.get("closes") or "").strip()[:5]
        if not (o and c):
            continue
        for d in days:
            ab = _DOW.get(str(d).rstrip("/").split("/")[-1].lower())
            if ab:
                byday[ab] = (o, c)
    if not byday:
        return None
    groups: list[tuple[str, str, tuple[str, str]]] = []
    for d in _DOW_ORDER:
        if d not in byday:
            continue
        hrs = byday[d]
        if groups and groups[-1][2] == hrs and \
                _DOW_ORDER.index(d) == _DOW_ORDER.index(groups[-1][1]) + 1:
            groups[-1] = (groups[-1][0], d, hrs)
        else:
            groups.append((d, d, hrs))
    if len(groups) == 1 and groups[0][0] == "Пн" and groups[0][1] == "Вс":
        o, c = groups[0][2]
        return f"Ежедневно {o}–{c}"
    segs = []
    for a, b, (o, c) in groups:
        label = a if a == b else f"{a}–{b}"
        segs.append(f"{label} {o}–{c}")
    return ", ".join(segs)


def _first_phone(tel) -> str | None:
    if not tel:
        return None
    first = str(tel).split(",")[0]
    first = re.sub(r"\s+", " ", first).strip()
    return first or None


def parse_clinic(host: str, html: str):
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    h1_el = soup.select_one("h1")
    h1 = h1_el.get_text(" ", strip=True) if h1_el else ""

    items = soup.select(".PersonalOffers__item")
    offers = []
    for it in items:
        t = it.select_one(".PersonalOffers__title")
        p = it.select_one(".PersonalOffers__price")
        if not t or not p:
            continue
        raw_name = t.get_text(" ", strip=True)
        if not raw_name:
            continue
        cat_el = it.find_previous(class_="PersonalOffers__categoryTitle")
        category = cat_el.get_text(" ", strip=True) if cat_el else ""
        price, is_from, on_request = parse_price(p.get_text(" ", strip=True))
        offers.append({
            "host": host,
            "raw_name": raw_name,
            "category": category,
            "price": price,
            "currency": "KZT",
            "is_from": is_from,
            "on_request": on_request,
        })

    # --- поля клиники: сперва JSON-LD, затем мягкий откат к DOM/<title> ---
    lb = _localbusiness(soup)
    addr_el = soup.select_one("[class*=address], [class*=Address]")
    addr_dom = addr_el.get("title") or addr_el.get_text(" ", strip=True) if addr_el else None

    brand = street = city = phone = working_hours = None
    if lb:
        brand = (lb.get("name") or "").strip() or None
        ad = lb.get("address") or {}
        if isinstance(ad, dict):
            street = re.sub(r"\s+", " ", (ad.get("streetAddress") or "").strip()) or None
            city = (ad.get("addressLocality") or "").strip() or None
        phone = _first_phone(lb.get("telephone"))
        working_hours = _fmt_hours(lb.get("openingHoursSpecification"))

    if not brand:
        brand = clinic_name(title, h1, host)
    if not city:
        city = detect_city(soup, title)
    city = CITY_CANON.get(city, city) if city else None
    if not street and addr_dom:
        # из полного адреса DOM выкидываем ведущий город: "Алматы, ул. X, 1" -> "ул. X, 1"
        parts = [s.strip() for s in addr_dom.split(",")]
        if parts and city and parts[0].lower().lstrip("г. ").startswith(city.lower()):
            street = ", ".join(parts[1:]).strip() or None
        else:
            street = addr_dom

    # человекочитаемый адрес: "Город, улица" (как на 103.kz)
    address = ", ".join([p for p in (city, street) if p]) or addr_dom

    clinic = {
        "host": host,
        "name": brand,          # бренд; различение филиалов по street делает ingest
        "brand": brand,
        "street": street,
        "city": city,
        "address": address,
        "phone": phone,
        "working_hours": working_hours,
        "source_url": f"https://{host}/pricing/",
        "n_offers": len(offers),
    }
    return clinic, offers


_write_lock = threading.Lock()
_counter = {"clinics": 0, "offers": 0, "empty": 0, "errors": 0, "done": 0}


def worker(host: str, fc, fo, fd):
    html = fetch(f"https://{host}/pricing/")
    if html is None:
        with _write_lock:
            _counter["errors"] += 1
            _counter["done"] += 1
            fd.write(host + "\n"); fd.flush()
        return
    try:
        clinic, offers = parse_clinic(host, html)
    except Exception:
        with _write_lock:
            _counter["errors"] += 1
            _counter["done"] += 1
            fd.write(host + "\n"); fd.flush()
        return
    with _write_lock:
        if offers:
            fc.write(json.dumps(clinic, ensure_ascii=False) + "\n"); fc.flush()
            for o in offers:
                fo.write(json.dumps(o, ensure_ascii=False) + "\n")
            fo.flush()
            _counter["clinics"] += 1
            _counter["offers"] += len(offers)
        else:
            _counter["empty"] += 1
        _counter["done"] += 1
        fd.write(host + "\n"); fd.flush()


def load_done() -> set[str]:
    p = os.path.join(RAW, "_done.txt")
    if not os.path.exists(p):
        return set()
    return set(x.strip() for x in open(p, encoding="utf-8") if x.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="макс. число клиник за запуск (0 = все оставшиеся)")
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    frontier_path = os.path.join(ROOT, "frontier.txt")
    if not os.path.exists(frontier_path):
        print("frontier.txt не найден — сначала запусти discover.py", file=sys.stderr)
        sys.exit(1)
    hosts = [h.strip() for h in open(frontier_path, encoding="utf-8") if h.strip()]
    done = load_done()
    todo = [h for h in hosts if h not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"frontier={len(hosts)} done={len(done)} todo_now={len(todo)} workers={args.workers}", flush=True)

    t0 = time.time()
    with open(os.path.join(RAW, "clinics.jsonl"), "a", encoding="utf-8") as fc, \
         open(os.path.join(RAW, "offers.jsonl"), "a", encoding="utf-8") as fo, \
         open(os.path.join(RAW, "_done.txt"), "a", encoding="utf-8") as fd:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(worker, h, fc, fo, fd) for h in todo]
            last = 0
            for _ in as_completed(futs):
                d = _counter["done"]
                if d - last >= 50:
                    last = d
                    el = time.time() - t0
                    print(f"  {d}/{len(todo)} | clinics+={_counter['clinics']} offers={_counter['offers']} "
                          f"empty={_counter['empty']} err={_counter['errors']} | {el:.0f}s "
                          f"({d/el:.1f}/s)", flush=True)
    el = time.time() - t0
    print(f"DONE batch: processed={_counter['done']} clinics_with_prices={_counter['clinics']} "
          f"offers={_counter['offers']} empty={_counter['empty']} errors={_counter['errors']} in {el:.0f}s", flush=True)


if __name__ == "__main__":
    main()
