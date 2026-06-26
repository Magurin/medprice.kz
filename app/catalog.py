"""
catalog.py — матчинг названий услуг клиник на приложенный Справочник (1281 услуга).

Приоритет:
  1) по коду тарификатора (точно). Если код в справочнике у нескольких услуг —
     выбираем по близости названия.
  2) точное совпадение нормализованного названия.
  3) нечёткое по названию (containment + сходство, как в normalize.Matcher).
  Иначе -> не сопоставлено (unmatched).
"""
import json
import os
from difflib import SequenceMatcher

from .normalize import normalize

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "reference_services.json")


# Слишком общие токены — сами по себе не доказывают совпадение услуги
GENERIC = {
    "прием", "приём", "первичный", "повторный", "консультативный", "консультация",
    "врача", "осмотр", "услуга", "услуги", "на", "для", "с", "и", "в", "по",
    "1", "2", "посещение", "исследование", "анализ",
}


def _tok(s):
    return set(s.split())


def _sim(a, b, at, bt):
    if not at or not bt:
        return 0.0
    j = len(at & bt) / len(at | bt)
    return 0.6 * j + 0.4 * SequenceMatcher(None, a, b).ratio()


class ReferenceMatcher:
    FUZZY = 0.82

    def __init__(self, path=DATA):
        with open(path, encoding="utf-8") as f:
            self.services = json.load(f)["services"]
        self.by_id = {s["ref_id"]: s for s in self.services}
        self.by_tarif = {}
        self.name_exact = {}
        self.tok_index = {}
        self._norm = {}  # ref_id -> (norm, tokens)
        for s in self.services:
            n = normalize(s["name"])
            self._norm[s["ref_id"]] = (n, _tok(n))
            self.name_exact.setdefault(n, s["ref_id"])
            for t in _tok(n):
                self.tok_index.setdefault(t, set()).add(s["ref_id"])
            if s.get("tarificator"):
                self.by_tarif.setdefault(s["tarificator"], []).append(s["ref_id"])

        # слой синонимов (ТЗ §3.2): app/data/synonyms.json
        self.phrase_subs = {}
        self.syn_index = {}
        sp = os.path.join(os.path.dirname(path), "synonyms.json")
        if os.path.exists(sp):
            blob = json.load(open(sp, encoding="utf-8"))
            self.phrase_subs = {normalize(k): normalize(v)
                                for k, v in blob.get("phrase_subs", {}).items()}
            for syn, target in blob.get("synonyms", []):
                rid = self.name_exact.get(normalize(target))
                if rid:  # цель есть в справочнике — иначе игнорируем
                    self.syn_index[normalize(syn)] = rid

    def _sub(self, norm: str) -> str:
        if not self.phrase_subs:
            return norm
        return " ".join(self.phrase_subs.get(t, t) for t in norm.split())

    def _best_name(self, norm, toks, candidate_ids):
        best = (0.0, None)
        for rid in candidate_ids:
            cn, ct = self._norm[rid]
            inter = toks & ct
            if inter == ct and len(ct) >= 2:
                sc = 0.93 + 0.07 * (len(inter) / len(toks | ct))
            else:
                sc = _sim(norm, cn, toks, ct)
            if sc > best[0]:
                best = (sc, rid)
        return best

    def match(self, raw_name: str, tarificator: str | None = None):
        norm = self._sub(normalize(raw_name))
        if not norm:
            return None
        toks = _tok(norm)

        # 1) по коду тарификатора
        if tarificator and tarificator in self.by_tarif:
            cands = self.by_tarif[tarificator]
            if len(cands) == 1:
                rid = cands[0]
                return self._result(rid, "tarif", 1.0)
            sc, rid = self._best_name(norm, toks, cands)
            if rid:
                return self._result(rid, "tarif+name", round(max(sc, 0.9), 3))

        # 1.5) слой синонимов
        if norm in self.syn_index:
            return self._result(self.syn_index[norm], "synonym", 1.0)

        # 2) точное имя
        if norm in self.name_exact:
            return self._result(self.name_exact[norm], "name_exact", 1.0)

        # 3) нечёткое имя
        cand_ids = set()
        for t in toks:
            cand_ids |= self.tok_index.get(t, set())
        if cand_ids:
            sc, rid = self._best_name(norm, toks, cand_ids)
            if rid and sc >= self.FUZZY:
                # принять только если есть общий ЗНАЧИМЫЙ (не общий) токен
                shared = (toks & self._norm[rid][1]) - GENERIC
                if shared:
                    return self._result(rid, "name_fuzzy", round(sc, 3))
        return None

    def _result(self, rid, method, score):
        s = self.by_id[rid]
        return {
            "ref_id": rid, "name": s["name"], "category": s["category"],
            "specialty": s["specialty"], "tarificator": s["tarificator"],
            "method": method, "score": score,
        }


if __name__ == "__main__":
    m = ReferenceMatcher()
    tests = [
        ("Прием акушер-гинеколога", "A02.004.000"),
        ("Общий анализ крови", None),
        ("ОАК (клинический анализ крови)", None),
        ("ФГДС с седацией", None),
        ("Какая-то левая услуга", None),
        ("3D УЗИ плода", "C03.033.004"),
    ]
    for nm, code in tests:
        r = m.match(nm, code)
        print(f"{nm[:42]:44s} -> {(r['name'][:34]+' ['+r['method']+'/'+str(r['score'])+']') if r else 'UNMATCHED'}")
