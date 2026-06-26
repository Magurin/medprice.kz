# -*- coding: utf-8 -*-
"""
build_reference.py — из приложенного «Справочник услуг.xlsx» строит
канонический справочник app/data/reference_services.json.

Поля строки справочника: ID(спец.), Специальность, Code, Name_ru, TarificatrCode.
Выход: список услуг + производная категория (enum по ТЗ §2.2).
"""
import json
import os
import re

import openpyxl

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "Справочник услуг.xlsx")
OUT = os.path.join(ROOT, "app", "data", "reference_services.json")

DIAG = re.compile(r"\b(УЗИ|МРТ|КТ|рентген|томограф|ФГДС|ФГС|колоноскоп|эндоскоп|ЭКГ|ЭхоКГ|ЭЭГ|"
                  r"допплер|доплер|маммограф|денситометр|флюорограф|рдг|сцинтиграф|холтер|спирограф|КТГ|узд)", re.I)
LAB = re.compile(r"\b(анализ|кровь|крови|моч[аи]|кал\b|посев|ИФА|ПЦР|мазок|биохими|гормон|"
                 r"онкомаркер|серолог|цитолог|гистолог|коагул|липид|глюкоз|тест)", re.I)
PRIEM = re.compile(r"^\s*(при[её]м|консультац|осмотр врача)", re.I)


def categorize(name: str, specialty: str) -> str:
    n = name or ""
    if PRIEM.search(n):
        return "приём врача"
    if (specialty or "").strip().lower() == "лаборатория" or LAB.search(n):
        return "лаборатория"
    if DIAG.search(n) or DIAG.search(specialty or ""):
        return "диагностика"
    return "процедура"


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    services = []
    ref_id = 0
    header_seen = False
    for row in ws.iter_rows(values_only=True):
        if not header_seen:
            header_seen = True
            continue  # пропустить шапку
        spec_id, specialty, code, name, tarif = (list(row) + [None] * 5)[:5]
        if not name or not str(name).strip():
            continue
        name = str(name).strip()
        ref_id += 1
        services.append({
            "ref_id": ref_id,
            "orig_code": None if code is None else str(code).strip(),
            "name": name,
            "specialty": (str(specialty).strip() if specialty else None),
            "tarificator": (str(tarif).strip() if tarif else None),
            "category": categorize(name, str(specialty or "")),
        })
    wb.close()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"services": services}, f, ensure_ascii=False, indent=1)

    # статистика
    from collections import Counter
    cats = Counter(s["category"] for s in services)
    specs = Counter(s["specialty"] for s in services)
    with_tarif = sum(1 for s in services if s["tarificator"])
    tindex = Counter(s["tarificator"] for s in services if s["tarificator"])
    dup_codes = sum(1 for c, n in tindex.items() if n > 1)
    print(f"услуг в справочнике: {len(services)}")
    print(f"с кодом тарификатора: {with_tarif}  | уникальных кодов: {len(tindex)}  | кодов с >1 услугой: {dup_codes}")
    print("категории:", dict(cats))
    print("специальностей:", len(specs))
    print("примеры:")
    for s in services[:3] + services[-2:]:
        print("  ", s["ref_id"], "|", s["category"], "|", s["tarificator"], "|", s["name"][:45], "|", s["specialty"])
    print("-> сохранено:", OUT)


if __name__ == "__main__":
    main()
