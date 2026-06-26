"""
pdfparse.py — best-effort разбор PDF-прайсов.

Стратегия: берём слова с координатами (PyMuPDF), кластеризуем в визуальные
строки по Y (имя и цена в исходнике на одной строке, даже если текст
линеаризуется отдельно). В строке: правые числовые токены -> цена,
остальной текст -> название. Грязные сканы (битые цифры) — насколько выйдет;
непарсибельное просто не попадёт (уйдёт мимо, как и договаривались — best-effort).
"""
import re

import fitz

from .fileparse import is_section, find_code, TARIF_RE

_PRICE_TOK = re.compile(r"^[\d  .,]+$")
_HAS_DIGIT = re.compile(r"\d")


def _clean_digits(s: str) -> str:
    # мягкая чистка частых артефактов скана в числах: кир. О/о -> 0
    return s.replace("О", "0").replace("о", "0")


def _is_num(tok):
    tc = _clean_digits(tok)
    return bool(_PRICE_TOK.match(tc) and _HAS_DIGIT.search(tc))


def _to_int(parts):
    joined = re.sub(r"[  .,]", "", "".join(_clean_digits(p) for p in parts))
    return int(joined) if joined.isdigit() else None


def _price_columns(words):
    """
    Из слов строки (с координатами) выделяет хвостовые числовые КОЛОНКИ.
    Соседние числовые токены с малым X-разрывом = разряды одного числа;
    большой разрыв = отдельная ценовая колонка (тир).
    Возвращает (name_words, [цены_по_колонкам]).
    """
    # индекс, с которого начинается хвостовой числовой блок
    i = len(words)
    while i > 0 and _is_num(words[i - 1][4]):
        i -= 1
    num_words = words[i:]
    name_words = words[:i]
    if not num_words:
        return name_words, []
    # ширина символа для оценки «большого» разрыва
    cols, cur = [], [num_words[0]]
    for prev, w in zip(num_words, num_words[1:]):
        gap = w[0] - prev[2]               # x0 текущего минус x1 предыдущего
        approx_char = max((prev[2] - prev[0]) / max(len(prev[4]), 1), 4)
        if gap > approx_char * 2.5:        # большой разрыв -> новая колонка
            cols.append(cur); cur = [w]
        else:
            cur.append(w)
    cols.append(cur)
    prices = []
    for c in cols:
        v = _to_int([w[4] for w in c])
        if v and 50 <= v <= 5_000_000:
            prices.append(v)
    return name_words, prices


def _rows_from_page(page, ytol=4.0):
    words = page.get_text("words")  # (x0,y0,x1,y1, word, block, line, wordno)
    if not words:
        return []
    words.sort(key=lambda w: (round(w[1] / ytol), w[0]))
    rows, cur, cur_y = [], [], None
    for w in words:
        y = w[1]
        if cur_y is None or abs(y - cur_y) <= ytol:
            cur.append(w); cur_y = y if cur_y is None else cur_y
        else:
            rows.append(cur); cur = [w]; cur_y = y
    if cur:
        rows.append(cur)
    return rows


def parse_pdf(path):
    doc = fitz.open(path)
    recs = []
    section = None
    for page in doc:
        for row in _rows_from_page(page):
            text = " ".join(w[4] for w in row).strip()
            if not text:
                continue
            name_words, prices = _price_columns(row)
            name_tokens = [w[4] for w in name_words]
            # отбросить ведущий номер п/п
            if name_tokens and re.fullmatch(r"\d+[.)]?", name_tokens[0]):
                name_tokens = name_tokens[1:]
            name = " ".join(name_tokens).strip(" .\t")
            if not prices:
                if is_section(text):
                    section = text
                continue
            if not name or len(name) < 4 or not re.search(r"[А-Яа-яA-Za-z]{3,}", name):
                continue
            price = prices[0]  # левая ценовая колонка = граждане РК
            recs.append({
                "section": section, "code": find_code(name), "raw_name": name,
                "unit": None, "price": price, "tiers": prices, "currency": "KZT",
            })
    doc.close()
    return recs
