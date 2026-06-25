"""
harvest.py — массовый сбор прайс-листов клиник РК с сети 103.kz.

Для каждого хоста из frontier.txt качает <host>/pricing/ и вынимает позиции
прайса по единому шаблону портала:
    .PersonalOffers__item
        .PersonalOffers__title   -> название услуги (как у клиники, «сырое»)
        .PersonalOffers__price   -> цена («1 790 тенге», «от 2 000 тенге», «уточняйте»)
Город/адрес/имя клиники берём из элемента адреса и <title>.

Многопоточно (ThreadPoolExecutor), докачиваемо (пропускает хосты из _done.txt),
устойчиво к ошибкам отдельных клиник.

Выход (JSONL, по строке на запись):
    raw/clinics.jsonl  — {host, name, city, address, source_url, n_offers}
    raw/offers.jsonl   — {host, raw_name, category, price, currency, is_from, on_request}

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
        for c in CITIES:
            if head.lower().startswith(c.lower()):
                return CITY_CANON.get(c, c)
    # 2) из <title>: "... центр Алматы - ..."
    for c in CITIES:
        if re.search(r"\b" + re.escape(c) + r"\b", title, re.IGNORECASE):
            return CITY_CANON.get(c, c)
    return None


def clinic_name(title: str, host: str) -> str:
    # "Цены - <NAME> - стоимость, прайс-лист ..."
    m = re.search(r"Цены\s*[-–—]\s*(.+?)\s*[-–—]\s*(?:стоимость|прайс)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if " - " in title:
        return title.split(" - ")[0].replace("Цены", "").strip(" -–—")
    return host.replace(".103.kz", "")


def parse_clinic(host: str, html: str):
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
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
    clinic = {
        "host": host,
        "name": clinic_name(title, host),
        "city": detect_city(soup, title),
        "address": (soup.select_one("[class*=address], [class*=Address]") or _Empty()).get_text(" ", strip=True) if soup.select_one("[class*=address], [class*=Address]") else None,
        "source_url": f"https://{host}/pricing/",
        "n_offers": len(offers),
    }
    return clinic, offers


class _Empty:
    def get_text(self, *a, **k):
        return None


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
