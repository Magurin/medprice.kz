"""
normalize.py — движок нормализации и матчинга названий медуслуг.

Проблема кейса: одна и та же услуга у разных клиник называется по-разному
(«Общий анализ крови с лейкоформулой и СОЭ» / «Клинический анализ крови» /
«ОАК»). Чтобы сравнивать цены, raw-названия надо привести к каноническим.

Стратегия (масштабируется на сотни тысяч позиций, O(N)):
  1. normalize() схлопывает регистр/пунктуацию/ё/пробелы.
  2. Кураторский справочник (canonical.json) задаёт «якорные» услуги и их
     синонимы (alias) — разные формулировки сливаются в один канон.
  3. Лёгкое нечёткое сравнение ТОЛЬКО против кураторских синонимов ловит
     морфологические варианты, не перечисленные явно.
  4. Всё остальное (длинный хвост) группируется по нормализованному ключу:
     одинаковые названия у разных клиник автоматически становятся одной
     услугой -> уже можно сравнивать.
"""
import json
import os
import re
from difflib import SequenceMatcher

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_KEEP = re.compile(r"[^0-9a-zа-я]+")
_WS = re.compile(r"\s+")
# Генерические слова, которые не помогают различать услуги
_STOP = {"услуга", "услуги", "процедура", "манипуляция"}


def normalize(text: str) -> str:
    """Канонизирующий ключ: нижний регистр, ё→е, без пунктуации, схлопнутые пробелы."""
    s = (text or "").lower().replace("ё", "е")
    s = _KEEP.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    if not s:
        return s
    toks = [t for t in s.split() if t not in _STOP]
    return " ".join(toks) if toks else s


def _tokens(norm: str) -> set[str]:
    return set(norm.split())


def _similarity(a_norm: str, b_norm: str, a_tok: set[str], b_tok: set[str]) -> float:
    if not a_tok or not b_tok:
        return 0.0
    jacc = len(a_tok & b_tok) / len(a_tok | b_tok)
    ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
    return 0.6 * jacc + 0.4 * ratio


class Matcher:
    """Сопоставляет raw-название с каноническим кодом услуги."""

    FUZZY_THRESHOLD = 0.82

    def __init__(self, canonical_path: str | None = None):
        path = canonical_path or os.path.join(DATA_DIR, "canonical.json")
        with open(path, encoding="utf-8") as f:
            blob = json.load(f)
        self.services = blob["services"]
        # code -> service meta
        self.by_code = {s["code"]: s for s in self.services}
        # нормализованный alias -> code  (включая само каноническое имя)
        self.alias_index: dict[str, str] = {}
        # для нечёткого: список (code, alias_norm, tokens)
        self._fuzzy: list[tuple[str, str, set[str]]] = []
        # инвертированный индекс токен -> коды (чтобы не сравнивать со всем справочником)
        self._token_to_codes: dict[str, set[str]] = {}
        for s in self.services:
            forms = [s["name"], *s.get("aliases", [])]
            for form in forms:
                n = normalize(form)
                if not n:
                    continue
                self.alias_index.setdefault(n, s["code"])
                toks = _tokens(n)
                self._fuzzy.append((s["code"], n, toks))
                for t in toks:
                    self._token_to_codes.setdefault(t, set()).add(s["code"])
        # авто-канон: нормализованный ключ -> (code, display_name)
        self._auto: dict[str, tuple[str, str]] = {}

    def match(self, raw_name: str):
        """
        -> dict(code, name, category, method, score)
        method: 'curated' | 'curated_fuzzy' | 'auto'
        """
        norm = normalize(raw_name)
        if not norm:
            return None
        # 1) точное совпадение с кураторским синонимом
        code = self.alias_index.get(norm)
        if code:
            s = self.by_code[code]
            return {"code": code, "name": s["name"], "category": s["category"],
                    "method": "curated", "score": 1.0}
        # 2) кандидаты, делящие хотя бы 1 токен с raw-названием
        toks = _tokens(norm)
        cand_codes: set[str] = set()
        for t in toks:
            cand_codes |= self._token_to_codes.get(t, set())
        best = (0.0, None)
        if cand_codes:
            for c, alias_norm, alias_tok in self._fuzzy:
                if c not in cand_codes:
                    continue
                inter = toks & alias_tok
                # 2a) containment: синоним целиком присутствует в raw-названии
                if inter == alias_tok:
                    if len(alias_tok) >= 2:
                        jacc = len(inter) / len(toks | alias_tok)
                        sc = 0.93 + 0.07 * jacc
                    else:
                        # одно-токенный синоним (аббревиатура) — только если однозначен
                        tok = next(iter(alias_tok))
                        sc = 0.9 if (len(self._token_to_codes.get(tok, ())) == 1 and len(tok) >= 3) else 0.0
                else:
                    # 2b) обычное нечёткое сходство
                    sc = _similarity(norm, alias_norm, toks, alias_tok)
                if sc > best[0]:
                    best = (sc, c)
        if best[1] and best[0] >= self.FUZZY_THRESHOLD:
            s = self.by_code[best[1]]
            return {"code": best[1], "name": s["name"], "category": s["category"],
                    "method": "curated_fuzzy", "score": round(best[0], 3)}
        # 3) авто-канон по нормализованному ключу (длинный хвост)
        if norm in self._auto:
            code, name = self._auto[norm]
        else:
            code = "auto:" + norm
            name = raw_name.strip()
            self._auto[norm] = (code, name)
        return {"code": code, "name": name, "category": "Прочее", "method": "auto", "score": 1.0}


if __name__ == "__main__":
    # быстрый тест на реальных вариантах названий
    m = Matcher()
    samples = [
        "Общий анализ крови с лейкоформулой и СОЭ",
        "Клинический анализ крови (с лейкоцитарной формулой)",
        "Общий анализ крови без СОЭ",
        "ТТГ (тиреотропный гормон) ультрачувствительный",
        "ТТГ (TSH)",
        "Простатспецифический антиген (ПСА общий)",
        "ПСА общий",
        "МРТ артерий и вен головного мозга",
        "Физико-химическое исследование мочи с микроскопией",
        "Какая-то редкая услуга которой нет в справочнике",
    ]
    for s in samples:
        r = m.match(s)
        print(f"{s[:48]:50s} -> {r['code']:28s} [{r['method']}/{r['score']}]")
