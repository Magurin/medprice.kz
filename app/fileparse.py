"""
fileparse.py — парсеры прайс-файлов клиник (Excel/Word/PDF) -> единый список строк.

Каждая строка: {section, code, raw_name, unit, price, tiers, currency}
  price  — основная цена (для граждан РК, если колонка распознана; иначе первая числовая)
  tiers  — все числовые ценовые колонки строки
  code   — код из файла (тарификатор, если есть)

Подход устойчив к разным раскладкам: колонки ищем по ключевым словам в шапке,
служебные/«шапочные» строки и заголовки разделов отсекаем.
"""
import re
import zipfile

# ---------- утилиты ----------
_DIGITS = re.compile(r"\d[\d  ]*[.,]?\d*")
TARIF_RE = re.compile(r"\b[A-EА-Е]\d{2}\.\d{3}\.\d{3}\b")  # формат тарификатора, напр. A02.004.000


def to_price(v):
    """Число/строку -> int тенге или None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v)) if v > 0 else None
    s = str(v).strip()
    m = _DIGITS.search(s)
    if not m:
        return None
    num = re.sub(r"[  ]", "", m.group(0)).replace(",", ".")
    try:
        f = float(num)
        return int(round(f)) if f > 0 else None
    except ValueError:
        return None


def is_section(name: str) -> bool:
    """Похоже на заголовок раздела: ВЕРХНИЙ РЕГИСТР / 'Раздел'/'Блок'/нумерованный заголовок без цены."""
    n = name.strip()
    if not n:
        return False
    if re.match(r"^(раздел|блок|глава|часть)\b", n, re.I):
        return True
    if re.match(r"^[\dIVX]+[.)]\s*[А-ЯЁA-Z]", n) and len(n) < 80 and not re.search(r"\d{3,}", n):
        return True
    letters = [c for c in n if c.isalpha()]
    if letters and len(n) < 70 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.8:
        return True
    return False


def find_code(*cells) -> str | None:
    for c in cells:
        if c is None:
            continue
        m = TARIF_RE.search(str(c))
        if m:
            return m.group(0)
    return None


# ---------- определение колонок по шапке ----------
NAME_KW = re.compile(r"наименование|название", re.I)
PRICE_KW = re.compile(r"цена|стоимост|тенге|тг", re.I)
RK_KW = re.compile(r"граждан|республики казахстан|резидент|кандас", re.I)
UNIT_KW = re.compile(r"ед\.?\s*изм|единица", re.I)
CODE_KW = re.compile(r"код", re.I)


def _detect_columns(rows, scan=40):
    """
    Индекс строки-шапки и индексы колонок. Шапка часто разбита на 2-3 строки
    (название в одной, «для граждан РК» в следующей) — объединяем окно строк.
    Ценовой считаем и колонку с пометкой «цена/тенге», и «для граждан РК».
    """
    n = len(rows)
    for ri in range(min(scan, n)):
        combined = {}
        for r in rows[ri:ri + 3]:
            for j, c in enumerate(r):
                if c is not None and str(c).strip():
                    combined[j] = (combined.get(j, "") + " " + str(c)).strip()
        name_col = next((j for j, t in combined.items() if NAME_KW.search(t)), None)
        if name_col is None:
            continue
        price_cols = [j for j, t in combined.items()
                      if j != name_col and (PRICE_KW.search(t) or RK_KW.search(t))]
        if not price_cols:
            continue
        rk_col = next((j for j in price_cols if RK_KW.search(combined[j])), None)
        unit_col = next((j for j, t in combined.items() if UNIT_KW.search(t)), None)
        code_col = next((j for j, t in combined.items() if CODE_KW.search(t) and j != name_col), None)
        return ri, name_col, price_cols, rk_col, unit_col, code_col
    return None


def _rows_to_records(rows):
    det = _detect_columns(rows)
    if not det:
        return []
    hdr, name_col, price_cols, rk_col, unit_col, code_col = det
    out = []
    section = None
    for row in rows[hdr + 1:]:
        cells = list(row)
        def cell(i):
            return cells[i] if (i is not None and i < len(cells)) else None
        name = cell(name_col)
        name = str(name).strip() if name is not None else ""
        if not name:
            continue
        if len(name) < 3 or re.fullmatch(r"[\d.,\s]+", name):
            continue  # строка-нумерация колонок («1 2 3») — не услуга
        tiers = [p for p in (to_price(cell(i)) for i in price_cols) if p]
        if not tiers:
            # строка без цен — возможно заголовок раздела
            if is_section(name):
                section = name
            continue
        primary = to_price(cell(rk_col)) if rk_col is not None else None
        if not primary:
            primary = tiers[0]
        code = None
        if code_col is not None:
            code = find_code(cell(code_col)) or (str(cell(code_col)).strip() if cell(code_col) else None)
        if not code:
            code = find_code(name)
        out.append({
            "section": section, "code": code, "raw_name": name,
            "unit": (str(cell(unit_col)).strip() if unit_col is not None and cell(unit_col) else None),
            "price": primary, "tiers": tiers, "currency": "KZT",
        })
    return out


# ---------- Excel ----------
def parse_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    recs = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        recs += _rows_to_records(rows)
    wb.close()
    return recs


def parse_xls(path):
    import xlrd
    wb = xlrd.open_workbook(path)
    recs = []
    for sh in wb.sheets():
        rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
        recs += _rows_to_records(rows)
    return recs


# ---------- Word (.docx) ----------
def parse_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    # таблицы
    rows = []
    for tbl in re.findall(r"<w:tbl[ >].*?</w:tbl>", xml, re.S):
        for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tbl, re.S):
            cells = []
            for tc in re.findall(r"<w:tc[ >].*?</w:tc>", tr, re.S):
                txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", tc, re.S))
                txt = re.sub(r"<[^>]+>", "", txt).replace("&amp;", "&").strip()
                cells.append(txt)
            if cells:
                rows.append(cells)
    if rows:
        recs = _rows_to_records(rows)
        if recs:
            return recs
    # запасной путь: параграфы тройками (код / название / цена)
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))
        t = re.sub(r"<[^>]+>", "", t).replace("&amp;", "&").strip()
        if t:
            paras.append(t)
    recs = []
    section = None
    i = 0
    while i < len(paras):
        line = paras[i]
        if is_section(line):
            section = line; i += 1; continue
        # код, затем название, затем цена
        if TARIF_RE.search(line) or re.match(r"^[UА-ЯA-Z]?\d", line):
            name = paras[i + 1] if i + 1 < len(paras) else ""
            price = to_price(paras[i + 2]) if i + 2 < len(paras) else None
            if name and price:
                recs.append({"section": section, "code": find_code(line) or line.strip(),
                             "raw_name": name, "unit": None, "price": price,
                             "tiers": [price], "currency": "KZT"})
                i += 3; continue
        i += 1
    return recs


def parse_file(path):
    p = path.lower()
    if p.endswith(".xlsx"):
        return parse_xlsx(path)
    if p.endswith(".xls"):
        return parse_xls(path)
    if p.endswith(".docx"):
        return parse_docx(path)
    if p.endswith(".pdf"):
        from .pdfparse import parse_pdf
        return parse_pdf(path)
    return []
