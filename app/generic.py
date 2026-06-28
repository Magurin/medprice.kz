"""
generic.py — УНИФИЦИРОВАННЫЙ адаптер сбора прайсов с любого сайта клиники.

Никакой привязки к вёрстке конкретного сайта (в отличие от шаблонного 103.kz):
  1. discover_price_urls — находим страницы прайса по ссылкам-ключам + типовым путям;
  2. контент страницы:
       • если в статическом HTML уже есть ценовые токены — берём его текст (дёшево);
       • иначе (SPA: цены подгружает JS) — рендерим через Jina Reader (r.jina.ai,
         бесплатно исполняет JS и отдаёт чистый текст) — без браузера на сервере;
  3. llm_extract — Groq (бесплатный OpenAI-совместимый LLM) со structured-выводом
     {услуга, цена, валюта}, длинные страницы — чанками;
  4. clinic_meta — метаданные клиники из JSON-LD LocalBusiness (best-effort).

Так модератор может добавить ЛЮБОЙ источник через UI — код один на все сайты.
Контракт parse_clinic(host) -> (clinic_meta|None, offers) совпадает с harvest.
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
from urllib.parse import urljoin, urlparse, quote

from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; MedPriceBot/1.0; research)"}
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

MAX_PRICE_PAGES = int(os.environ.get("GENERIC_MAX_PAGES", "3"))   # страниц-кандидатов на хост
LLM_CHUNK = int(os.environ.get("GENERIC_LLM_CHUNK", "12000"))    # символов на запрос к Groq
LLM_MAX_CHUNKS = int(os.environ.get("GENERIC_LLM_MAX_CHUNKS", "8"))  # потолок чанков на страницу
JINA_BASE = os.environ.get("JINA_BASE", "https://r.jina.ai/")
# Порог «в статике уже есть цены» — тогда Jina не нужна.
STATIC_PRICE_SIGNAL = int(os.environ.get("GENERIC_STATIC_SIGNAL", "5"))

_CUR = r"(?:₸|тг\.?|тнг|тенге|kzt)"
_PRICE_RX = re.compile(r"(\d[\d\s ]{2,})\s*" + _CUR, re.IGNORECASE)

_PRICE_WORDS = ("прайс", "цены", "цена", "стоимость", "тариф", "прейскурант",
                "услуги", "price", "pricing", "ceny", "uslugi", "tseny", "tarif",
                "pricelist", "price-list")
_PRICE_PATH_GUESSES = ("/price/", "/pricing/", "/price-list/", "/pricelist/", "/ceny/",
                       "/tseny/", "/uslugi/", "/services/", "/price.html", "/prajs/")

_CONTACT_WORDS = ("контакт", "contacts", "о нас", "о клинике", "about", "адрес",
                  "address", "филиал", "где наход", "офис", "kontakty")
_CONTACT_PATH_GUESSES = ("/contacts/", "/kontakty/", "/about/", "/o-nas/", "/about-us/",
                         "/filialy/", "/adresa/", "/clinics/")


def fetch(url: str, timeout: int = 20, max_bytes: int = 4_000_000) -> str | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return r.read(max_bytes).decode("utf-8", "ignore")
    except Exception:
        return None


def jina_render(url: str, timeout: int = 35) -> str | None:
    """Рендер страницы через Jina Reader (исполняет JS) -> чистый текст. None при ошибке."""
    headers = dict(UA)
    key = os.environ.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"     # выше бесплатные лимиты
    try:
        req = urllib.request.Request(JINA_BASE + url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return r.read(6_000_000).decode("utf-8", "ignore")
    except Exception:
        return None


def _price_signal(text: str) -> int:
    return len(_PRICE_RX.findall(text or ""))


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return soup.get_text(" ", strip=True)


# ---------- поиск страниц прайса ----------
def _discover(base_url: str, home_html: str, words, guesses, limit: int) -> list[str]:
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
            return
        seen.add(u)
        found.append(u)

    soup = BeautifulSoup(home_html or "", "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True).lower()
        if any(w in text or w in href.lower() for w in words):
            add(urljoin(base_url, href))
    for g in guesses:
        add(urljoin(base_url, g))
    return found[:limit]


def discover_price_urls(base_url: str, home_html: str) -> list[str]:
    urls = _discover(base_url, home_html, _PRICE_WORDS, _PRICE_PATH_GUESSES, MAX_PRICE_PAGES)
    base = base_url.rstrip("/")
    return (urls + [base])[:MAX_PRICE_PAGES] if base not in urls else urls


def discover_contact_urls(base_url: str, home_html: str) -> list[str]:
    return _discover(base_url, home_html, _CONTACT_WORDS, _CONTACT_PATH_GUESSES, 2)


# ---------- Groq (бесплатный LLM, structured output, мульти-ключ) ----------
_key_lock = threading.Lock()
_key_counter = itertools.count()


def _groq_keys() -> list[str]:
    raw = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def _keys_in_rotation(keys: list[str]) -> list[str]:
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


_SYS_MSG = (
    "Ты извлекаешь прайс-лист медицинских услуг из текста страницы клиники. "
    "Верни СТРОГО JSON-объект {\"items\":[{\"name\":\"...\",\"price\":1500,\"currency\":\"KZT\"}]}. "
    "name — ТОЧНОЕ название услуги без приписок о сроках/разделах/днях/категориях. "
    "price — целое число в тенге без пробелов; если цена «уточняйте»/«от …»/нет — price=null "
    "(а для «от N» возьми число N). Не выдумывай услуги, бери только реально присутствующие. "
    "Никакого текста кроме JSON."
)


def _groq_one(text: str) -> list[dict]:
    keys = _groq_keys()
    if not keys:
        return []
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": _SYS_MSG},
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
            if e.code in (429, 401, 403):
                continue
            return []
        except Exception:
            return []
    if resp is None:
        return []
    try:
        items = json.loads(resp["choices"][0]["message"]["content"]).get("items", [])
    except Exception:
        return []
    out = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        price = it.get("price")
        try:
            price = int(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        out.append({"raw_name": name, "category": "", "price": price,
                    "currency": (it.get("currency") or "KZT").upper(),
                    "is_from": False, "on_request": price is None})
    return out


def _chunks_by_lines(text: str, size: int) -> list[str]:
    lines = (text or "").splitlines()
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > size and cur:
            chunks.append(cur)
            cur = ""
        cur += ln + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks[:LLM_MAX_CHUNKS] or ([text[:size]] if text else [])


def llm_extract(text: str) -> list[dict]:
    """Извлечь услуги/цены из текста через Groq, длинный текст — чанками + дедуп."""
    if not text or not _groq_keys():
        return []
    offers = []
    for chunk in _chunks_by_lines(text, LLM_CHUNK):
        offers.extend(_groq_one(chunk))
    return _dedup(offers)


# Совместимость: старое имя groq_extract (без чанков) для тестов.
def groq_extract(text: str) -> list[dict]:
    return llm_extract(text)


_PROFILE_SYS = (
    "Ты извлекаешь карточку медицинской клиники/лаборатории из текста страницы. "
    "Верни СТРОГО JSON: {\"name\":\"\",\"city\":\"\",\"address\":\"\",\"phone\":\"\","
    "\"working_hours\":\"\",\"branches\":[{\"city\":\"\",\"address\":\"\",\"phone\":\"\"}]}. "
    "name — название клиники; address/phone/working_hours — основного офиса; "
    "branches — список ВСЕХ филиалов с адресами, если на странице есть (иначе []). "
    "Телефоны в формате как на сайте. Пустые поля = \"\". Никакого текста кроме JSON."
)


def llm_clinic_profile(text: str) -> dict:
    """Карточка клиники из текста (адрес/телефон/часы + филиалы) через Groq. {} при ошибке."""
    keys = _groq_keys()
    if not keys or not text:
        return {}
    payload = {
        "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "system", "content": _PROFILE_SYS},
                     {"role": "user", "content": text[:15000]}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    resp = None
    for key in _keys_in_rotation(keys):
        try:
            resp = _groq_call(key, payload)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 401, 403):
                continue
            return {}
        except Exception:
            return {}
    if resp is None:
        return {}
    try:
        d = json.loads(resp["choices"][0]["message"]["content"])
    except Exception:
        return {}
    branches = d.get("branches") or []
    branches = [b for b in branches if isinstance(b, dict) and (b.get("address") or "").strip()]
    return {
        "name": (d.get("name") or "").strip() or None,
        "city": (d.get("city") or "").strip() or None,
        "address": (d.get("address") or "").strip() or None,
        "phone": (d.get("phone") or "").strip() or None,
        "working_hours": (d.get("working_hours") or "").strip() or None,
        "branches": branches or None,
    }


def _dedup(offers: list[dict]) -> list[dict]:
    seen, out = set(), []
    for o in offers:
        key = (re.sub(r"\s+", " ", o["raw_name"].strip().lower()), o["price"])
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


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
    name = street = city = phone = None
    for d in _iter_ld(soup):
        t = d.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if not any(any(w in str(x) for w in ("Business", "Organization", "Hospital", "Clinic"))
                   for x in types):
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
    if not name:
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            name = og["content"].strip()
        elif soup.title:
            name = soup.title.get_text(strip=True)[:120] or None
    address = ", ".join([p for p in (city, street) if p]) or None
    return {"host": host, "name": name or host, "brand": name or host,
            "street": street, "city": city, "address": address,
            "phone": phone, "working_hours": None, "source_url": source_url}


# ---------- оркестрация одного хоста ----------
def _page_content(url: str, plain_html: str | None) -> str:
    """Текст страницы для LLM: статика как есть, иначе рендер через Jina."""
    plain = _visible_text(plain_html) if plain_html else ""
    if _price_signal(plain) >= STATIC_PRICE_SIGNAL:
        return plain                        # цены уже в статике — Jina не нужна
    rendered = jina_render(url)             # SPA: рендерим JS
    return rendered or plain


def _split_source(source: str) -> tuple[str, str | None]:
    """Источник может быть доменом ('clinic.kz') или прямым URL прайса
    ('clinic.kz/price', 'https://clinic.kz/pricelist/astana'). -> (host, direct_url|None).
    Прямой URL модератор задаёт в админке, когда страницу прайса не найти автоматически
    (напр. city-сегментные SPA вроде KDL: kdlolymp.kz/pricelist/astana)."""
    s = (source or "").strip()
    s = re.sub(r"^https?://", "", s).strip("/")
    if "/" in s:
        host = s.split("/", 1)[0]
        return host, "https://" + s
    return s, None


def parse_clinic(source: str):
    """source (домен или прямой URL прайса) -> (clinic_meta|None, offers).
    Унифицированный путь: [прямой URL] + discover -> контент (статика/Jina) -> Groq."""
    host, direct = _split_source(source)
    base = f"https://{host}/"
    home = fetch(base) or fetch(f"http://{host}/")

    candidates: list[str] = []
    if direct:
        candidates.append(direct)           # прямой URL прайса — первым приоритетом
    if home:
        candidates += [u for u in discover_price_urls(base, home) if u not in candidates]
    elif not direct:
        candidates.append(f"https://{host}/")  # ни home, ни прямого — пробуем корень через Jina
    candidates = candidates[:MAX_PRICE_PAGES]

    best_offers: list[dict] = []
    best_url = direct or base
    for u in candidates:
        plain = home if home and u.rstrip("/") == base.rstrip("/") else fetch(u)
        content = _page_content(u, plain)
        offers = llm_extract(content)
        if len(offers) > len(best_offers):
            best_offers, best_url = offers, u
        if len(best_offers) > 40:           # уже похоже на полноценный прайс — хватит
            break

    if not best_offers:
        if home is None and not direct:
            e = RuntimeError("сайт недоступен (timeout/HTTP error)")
            e.stage = "fetch"
            raise e
        return None, []

    meta = clinic_meta(host, home or "", best_url)
    meta["source_url"] = best_url
    _enrich_card(meta, host, base, home)     # добить адрес/телефон/часы/филиалы через LLM
    return meta, best_offers


def _enrich_card(meta: dict, host: str, base: str, home: str | None) -> None:
    """Если JSON-LD не дал адрес/телефон — рендерим страницу контактов и достаём карточку
    клиники (адрес/телефон/часы + филиалы) нейросетью. Заполняем ТОЛЬКО пустые поля."""
    if (meta.get("address") and meta.get("phone")) or not _groq_keys():
        return
    contact_urls = discover_contact_urls(base, home or "")
    contact_urls.append(base.rstrip("/"))    # на крайний случай — главная (часто адрес в футере)
    text = ""
    for u in contact_urls[:2]:
        plain = home if home and u.rstrip("/") == base.rstrip("/") else fetch(u)
        content = _page_content(u, plain)
        if content and len(content) > 200:
            text = content
            break
    if not text:
        return
    prof = llm_clinic_profile(text)
    if not prof:
        return
    for f in ("name", "city", "address", "phone", "working_hours"):
        if not meta.get(f) and prof.get(f):
            meta[f] = prof[f]
    if prof.get("branches"):
        meta["branches"] = prof["branches"]
