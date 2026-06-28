"""
generic.py — универсальный (бесшаблонный) адаптер сбора прайсов с ПРОИЗВОЛЬНЫХ
сайтов клиник. В отличие от harvester/harvest.py (заточен под вёрстку 103.kz),
здесь нет привязки к конкретным CSS-классам:

  1. discover_price_urls — находим страницы прайса по ссылкам-ключам
     (прайс/цены/стоимость/услуги/прейскурант/price/pricing) + типовые пути;
  2. extract_offers     — эвристикой вынимаем пары «услуга — цена» из таблиц и
     текста (токен «число + тг/₸/тенге/KZT»);
  3. clinic_meta        — метаданные клиники из JSON-LD LocalBusiness;
  4. Groq-fallback      — если эвристика сняла мало/ничего и задан GROQ_API_KEY,
     отправляем текст страницы в Groq (бесплатный OpenAI-совместимый LLM) и просим
     structured-вывод {услуга, цена, валюта}. Без ключа шаг просто пропускается.

Контракт parse_clinic(host) -> (clinic_meta|None, offers) совпадает с
harvester.harvest.parse_clinic, чтобы app.parser мог использовать оба одинаково.
offers: [{raw_name, category, price|None, currency, is_from, on_request}].
"""
import itertools
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; MedPriceBot/1.0; research)"}
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# Порог, ниже которого пробуем Groq-fallback (если ключ задан).
MIN_OFFERS_FOR_OK = int(os.environ.get("GENERIC_MIN_OFFERS", "5"))
# Сколько страниц-кандидатов максимум обходим на хост.
MAX_PRICE_PAGES = int(os.environ.get("GENERIC_MAX_PAGES", "6"))

# --- деньги: «1 500 ₸», «от 2 000 тенге», «5000 KZT» -----------------------------
_CUR = r"(?:₸|тг\.?|тнг|тенге|тг\b|kzt)"
_PRICE_RX = re.compile(r"(от\s+)?(\d[\d\s ]{2,})\s*" + _CUR, re.IGNORECASE)
# Чисто числовая цена (для ячеек таблицы в колонке «Цена», где валюта в шапке).
_NUM_CELL_RX = re.compile(r"^\s*(от\s+)?(\d[\d\s ]{2,})\s*" + _CUR + r"?\s*$", re.IGNORECASE)

_PRICE_WORDS = ("прайс", "цены", "цена", "стоимость", "тариф", "прейскурант",
                "услуги", "price", "pricing", "ceny", "uslugi", "tseny", "tarif")
_PRICE_PATH_GUESSES = ("/price/", "/pricing/", "/price-list/", "/ceny/", "/tseny/",
                       "/uslugi/", "/services/", "/price.html", "/prajs/")
# Стоп-слова: строки, которые не услуга (заголовки/мусор).
_NAME_STOP = re.compile(r"^\s*(итого|всего|категория|наименование|услуга|цена|стоимость)\s*$", re.I)


def fetch(url: str, timeout: int = 20, max_bytes: int = 4_000_000) -> str | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            data = r.read(max_bytes)
        return data.decode("utf-8", "ignore")
    except Exception:
        return None


def _money(text: str):
    """'от 2 000 тенге' -> (2000, is_from). Нет валюты/числа -> (None, False)."""
    m = _PRICE_RX.search(text or "")
    if not m:
        return None, False
    digits = re.sub(r"\D", "", m.group(2))
    if len(digits) < 3:                     # < 100 ₸ — почти наверняка не цена услуги
        return None, False
    val = int(digits)
    if val > 100_000_000:                   # абсурдно большое — мусор (телефон/индекс)
        return None, False
    return val, bool(m.group(1))


def _num_cell(text: str):
    """Ячейка-цена: '12 000' / 'от 12 000 ₸'. -> (price, is_from) | (None, False)."""
    m = _NUM_CELL_RX.match(text or "")
    if not m:
        return None, False
    digits = re.sub(r"\D", "", m.group(2))
    if len(digits) < 3:
        return None, False
    return int(digits), bool(m.group(1))


# ---------- поиск страниц прайса ----------
def discover_price_urls(base_url: str, home_html: str) -> list[str]:
    """Кандидаты страниц прайса: ссылки с ключевыми словами + типовые пути + сам home."""
    host = urlparse(base_url).netloc
    found: list[str] = []
    seen: set[str] = set()

    def add(u: str):
        if not u:
            return
        u = u.split("#")[0].rstrip("/") or u
        if u in seen:
            return
        if urlparse(u).netloc and urlparse(u).netloc != host:
            return                          # только тот же хост
        seen.add(u)
        found.append(u)

    soup = BeautifulSoup(home_html or "", "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        hl = href.lower()
        if any(w in text or w in hl for w in _PRICE_WORDS):
            add(urljoin(base_url, href))
    for g in _PRICE_PATH_GUESSES:           # типовые пути на случай, если ссылок нет
        add(urljoin(base_url, g))
    add(base_url.rstrip("/"))               # на крайний случай — сама главная
    return found[:MAX_PRICE_PAGES]


# ---------- эвристическое извлечение услуга/цена ----------
def _extract_from_tables(soup: BeautifulSoup) -> list[dict]:
    offers = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for tr in rows:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            # цена — последняя ячейка, похожая на число-с-ценой; имя — первая текстовая
            price = is_from = None
            price_idx = None
            for i in range(len(cells) - 1, -1, -1):
                p, isf = _num_cell(cells[i])
                if p is not None:
                    price, is_from, price_idx = p, isf, i
                    break
            if price is None:
                continue
            name = next((c for j, c in enumerate(cells)
                         if j != price_idx and c and not _NAME_STOP.match(c)
                         and not _num_cell(c)[0]), None)
            if not name:
                continue
            offers.append({"raw_name": name, "category": "", "price": price,
                           "currency": "KZT", "is_from": bool(is_from), "on_request": False})
    return offers


def _extract_from_text(soup: BeautifulSoup) -> list[dict]:
    """Блоки, где в одном элементе есть и название, и токен цены (число+валюта)."""
    offers = []
    for el in soup.find_all(["li", "p", "div", "tr", "dd", "span"]):
        if el.find(["li", "p", "div", "tr", "table"]):
            continue                        # берём только «листовые» блоки
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 300:
            continue
        price, is_from = _money(text)
        if price is None:
            continue
        name = _PRICE_RX.sub("", text).strip(" .—-:; ")
        if not name or _NAME_STOP.match(name) or len(name) < 3:
            continue
        offers.append({"raw_name": name, "category": "", "price": price,
                       "currency": "KZT", "is_from": bool(is_from), "on_request": False})
    return offers


def _dedup(offers: list[dict]) -> list[dict]:
    seen, out = set(), []
    for o in offers:
        key = (re.sub(r"\s+", " ", o["raw_name"].strip().lower()), o["price"])
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def extract_offers(html: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    offers = _extract_from_tables(soup) + _extract_from_text(soup)
    return _dedup(offers)


# ---------- метаданные клиники (JSON-LD LocalBusiness) ----------
def _iter_ld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                if "@graph" in cur:
                    stack.extend(cur["@graph"] if isinstance(cur["@graph"], list) else [cur["@graph"]])
                yield cur


def clinic_meta(host: str, html: str, source_url: str) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    name = street = city = address = phone = hours = None
    for d in _iter_ld(soup):
        t = d.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if not any("Business" in str(x) or "Organization" in str(x)
                   or "Hospital" in str(x) or "Clinic" in str(x) for x in types):
            continue
        name = name or (d.get("name") or "").strip() or None
        ad = d.get("address")
        if isinstance(ad, dict):
            street = street or (ad.get("streetAddress") or "").strip() or None
            city = city or (ad.get("addressLocality") or "").strip() or None
        tel = d.get("telephone")
        if isinstance(tel, list):
            tel = tel[0] if tel else None
        phone = phone or (str(tel).strip() if tel else None)
    if not name:                            # откат: <title> / og:site_name / h1
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            name = og["content"].strip()
        elif soup.title:
            name = soup.title.get_text(strip=True)[:120] or None
        elif soup.find("h1"):
            name = soup.find("h1").get_text(" ", strip=True)[:120] or None
    address = ", ".join([p for p in (city, street) if p]) or None
    return {
        "host": host, "name": name or host, "brand": name or host,
        "street": street, "city": city, "address": address,
        "phone": phone, "working_hours": hours,
        "source_url": source_url,
    }


# ---------- Groq fallback (бесплатный LLM, structured output) ----------
# Несколько ключей (GROQ_API_KEYS через запятую) — ротация по кругу + переход на
# следующий ключ при 429, чтобы обходить rate-limit бесплатного тарифа.
_key_lock = threading.Lock()
_key_counter = itertools.count()


def _groq_keys() -> list[str]:
    raw = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _keys_in_rotation(keys: list[str]) -> list[str]:
    """Порядок ключей со сдвигом старта по кругу — равномерно размазываем нагрузку."""
    if len(keys) <= 1:
        return keys
    with _key_lock:
        start = next(_key_counter) % len(keys)
    return keys[start:] + keys[:start]


def _groq_call(key: str, payload: dict):
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", **UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60, context=_ctx) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def groq_extract(text: str) -> list[dict]:
    """Извлечь услуги/цены через Groq, если задан ключ. Иначе/при ошибке -> []."""
    keys = _groq_keys()
    if not keys:
        return []
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    text = (text or "")[:15000]             # держим вход в разумных пределах (лимиты)
    sys_msg = ("Ты извлекаешь прайс-лист медицинских услуг со страницы клиники. "
               "Верни СТРОГО JSON-объект вида "
               '{"items":[{"name":"...","price":1500,"currency":"KZT"}]}. '
               "price — целое число в тенге без пробелов; если цена «уточняйте»/нет — "
               "price=null. Никакого текста кроме JSON.")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sys_msg},
                     {"role": "user", "content": text}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    resp = None
    for key in _keys_in_rotation(keys):
        try:
            resp = _groq_call(key, payload)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 401, 403):   # лимит/невалидный ключ — пробуем следующий
                continue
            return []
        except Exception:
            return []
    if resp is None:                        # все ключи упёрлись в лимит
        return []
    try:
        content = resp["choices"][0]["message"]["content"]
        items = json.loads(content).get("items", [])
    except Exception:
        return []
    offers = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        price = it.get("price")
        try:
            price = int(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        offers.append({"raw_name": name, "category": "", "price": price,
                       "currency": (it.get("currency") or "KZT").upper(),
                       "is_from": False, "on_request": price is None})
    return _dedup(offers)


# ---------- оркестрация одного хоста ----------
def parse_clinic(host: str):
    """host -> (clinic_meta|None, offers). Делает собственный fetch/discover.
    clinic_meta=None и offers=[] -> вызывающий считает источник неуспешным."""
    base = f"https://{host}/"
    home = fetch(base)
    if home is None:
        home = fetch(f"http://{host}/")
        base = f"http://{host}/"
    if home is None:
        e = RuntimeError("сайт недоступен (timeout/HTTP error)")
        e.stage = "fetch"
        raise e

    urls = discover_price_urls(base, home)
    offers: list[dict] = []
    best_html = home
    best_url = base
    for u in urls:
        html = fetch(u) if u != base else home
        if not html:
            continue
        got = extract_offers(html)
        if got:
            offers.extend(got)
            if len(got) > len(extract_offers(best_html)):
                best_html, best_url = html, u
    offers = _dedup(offers)

    # Fallback на Groq, если эвристика сняла мало (и ключ задан).
    if len(offers) < MIN_OFFERS_FOR_OK:
        soup = BeautifulSoup(best_html, "lxml")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        llm = groq_extract(soup.get_text(" ", strip=True))
        if len(llm) > len(offers):
            offers = llm

    meta = clinic_meta(host, home, best_url) if offers else None
    return meta, offers
