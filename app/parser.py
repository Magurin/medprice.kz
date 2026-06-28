"""
parser.py — модуль сбора данных (ТЗ §3.1). Единый оркестратор для двух путей запуска:
  • вручную из интерфейса  -> бэкенд триггерит GitHub Actions (workflow_dispatch)
  • по расписанию (cron)    -> тот же workflow по schedule
И там, и там на раннере выполняется ОДНА функция run_parse() — без дубля логики.

Что делает один прогон:
  1. Заводит запись parse_runs (status=running).
  2. Обходит источники нужного формата:
       web  — хосты 103.kz (harvester.harvest: HTML)
       file — файлы прайсов (app.fileparse: PDF / DOCX / XLSX / XLS)
  3. Складывает позиции «как пришли» в raw_price_items (СЫРОЙ слой, отдельно от
     нормализованных price_offers).
  4. Дедупликация: content_hash = sha256(source|raw_name|price), колонка UNIQUE,
     вставка ON CONFLICT DO NOTHING -> повторный запуск не плодит дубли.
  5. Любая ошибка по источнику пишется в parse_errors (источник + стадия + причина),
     прогон продолжается дальше.
  6. Финализирует parse_runs (счётчики, status=done/failed).

Запуск (раннер/cron):
  python -m app.parser --kind web  --limit 50
  python -m app.parser --kind web  --hosts almaty-clinic.103.kz,kdl.103.kz
  python -m app.parser --kind file --paths "Хакатон/*.xlsx,Хакатон/*.pdf"
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import SessionLocal
from .ops_models import OpsBase, ParseRun, ParseError, ParseRunLog, RawPriceItem, RawClinic
from .database import engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------- утилиты ----------
def _hash(source: str, raw_name: str, price) -> str:
    key = f"{source}|{(raw_name or '').strip().lower()}|{price if price is not None else ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _log(db, run_id, message, level="info", source=None, stage=None):
    """Строка в подробный лог прогона (видна в админке). Дублируется в stdout раннера."""
    db.add(ParseRunLog(run_id=run_id, level=level, source=source, stage=stage,
                       message=str(message)[:4000]))
    db.commit()
    prefix = f"[{level}]" + (f" {source}" if source else "")
    print(f"{prefix} {message}", flush=True)


def _log_error(db, run_id, source, stage, exc):
    db.add(ParseError(run_id=run_id, source=source, stage=stage, error=str(exc)[:2000]))
    db.commit()
    # та же ошибка попадает и в подробный лог — чтобы хронология прогона была полной
    _log(db, run_id, str(exc)[:2000], level="error", source=source, stage=stage)


def _store_clinic(db, run_id, clinic) -> None:
    """UPSERT метаданных клиники в raw_clinics по host (один ряд на host = текущий снимок)."""
    if not clinic or not clinic.get("host"):
        return
    payload = {**clinic, "run_id": run_id}
    upd = {k: payload[k] for k in
           ("run_id", "name", "brand", "street", "city", "address",
            "phone", "working_hours", "source_url", "branches") if k in payload}
    stmt = (
        pg_insert(RawClinic.__table__)
        .values(payload)
        .on_conflict_do_update(index_elements=["host"], set_=upd)
    )
    db.execute(stmt)
    db.commit()


def _store_rows(db, run_id, rows) -> tuple[int, int]:
    """Bulk-вставка raw-строк с дедупом по content_hash. -> (new, dup)."""
    if not rows:
        return 0, 0
    new = 0
    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        batch = rows[i:i + CHUNK]
        stmt = (
            pg_insert(RawPriceItem.__table__)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(RawPriceItem.id)
        )
        res = db.execute(stmt)
        new += len(res.fetchall())
        db.commit()
    return new, len(rows) - new


# ---------- источники: web (103.kz) ----------
def _import_harvester():
    """harvester/ — не пакет; добавляем в путь и импортируем harvest как модуль."""
    hdir = os.path.join(ROOT, "harvester")
    if hdir not in sys.path:
        sys.path.insert(0, hdir)
    import harvest  # type: ignore
    return harvest


def _frontier_hosts():
    """Все хосты из авто-списка 103.kz (harvester/frontier.txt)."""
    frontier = os.path.join(ROOT, "harvester", "frontier.txt")
    if not os.path.exists(frontier):
        return []
    return [h.strip() for h in open(frontier, encoding="utf-8") if h.strip()]


def _enabled_web_hosts(db, limit):
    """Хосты из включённых источников parse_sources: frontier -> весь список, host -> сам хост.
    Если в БД ничего/таблицы нет — откат к frontier.txt (обратная совместимость)."""
    from .ops_models import ParseSource
    hosts = []
    try:
        for s in db.query(ParseSource).filter(ParseSource.enabled.is_(True)).all():
            if s.kind == "frontier":
                hosts.extend(_frontier_hosts())
            elif s.value:
                hosts.append(s.value.strip())
    except Exception:
        hosts = []
    # дедуп с сохранением порядка
    seen, out = set(), []
    for h in hosts:
        if h and h not in seen:
            seen.add(h); out.append(h)
    if not out:
        out = _frontier_hosts()
    return out[:limit] if limit else out


def _web_hosts(db, sources, limit):
    if sources:                       # явные хосты из UI/CLI --hosts
        return sources
    return _enabled_web_hosts(db, limit)


def _web_rows(host, offers):
    """offers (из любого адаптера) -> raw-строки для raw_price_items (с дедуп-хэшем)."""
    rows = []
    for o in offers:
        rows.append({
            "source_kind": "web", "source": host, "clinic_host": host,
            "raw_name": o["raw_name"], "category": o.get("category"),
            "price": o.get("price"), "price_text": None, "currency": o.get("currency", "KZT"),
            "is_from": bool(o.get("is_from")), "on_request": bool(o.get("on_request")),
            "content_hash": _hash(host, o["raw_name"], o.get("price")),
        })
    return rows


def _clinic_meta(host, clinic, default_url):
    """clinic-словарь любого адаптера -> единый формат для raw_clinics (или None)."""
    if not clinic:
        return None
    branches = clinic.get("branches")
    return {
        "host": host,
        "name": clinic.get("name") or clinic.get("brand"),
        "brand": clinic.get("brand") or clinic.get("name"),
        "street": clinic.get("street"),
        "city": clinic.get("city"),
        "address": clinic.get("address"),
        "phone": clinic.get("phone"),
        "working_hours": clinic.get("working_hours"),
        "source_url": clinic.get("source_url") or default_url,
        "branches": json.dumps(branches, ensure_ascii=False) if branches else None,
    }


def _parse_103kz_source(harvest, host):
    """Шаблонный адаптер 103.kz: прайс всегда на /pricing/, вёрстка единая."""
    html = harvest.fetch(f"https://{host}/pricing/")
    if html is None:
        e = RuntimeError("страница недоступна (timeout/HTTP error)")
        e.stage = "fetch"
        raise e
    try:
        clinic, offers = harvest.parse_clinic(host, html)
    except Exception as exc:
        exc.stage = "parse"
        raise
    meta = _clinic_meta(host, clinic, f"https://{host}/pricing/") if offers else None
    return meta, _web_rows(host, offers)


def _parse_generic_source(source):
    """Унифицированный адаптер для ЛЮБОГО источника: discover -> render(Jina) -> Groq.
    source может быть доменом или прямым URL прайса; clinic_host нормализуем до домена."""
    from . import generic
    clinic, offers = generic.parse_clinic(source)   # сам ищет/рендерит/извлекает
    domain = (clinic or {}).get("host") or re.sub(r"^https?://", "", str(source)).split("/")[0]
    meta = _clinic_meta(domain, clinic, f"https://{domain}/") if offers else None
    return meta, _web_rows(domain, offers)


def _parse_web_source(harvest, host):
    """Роутер web-источника по домену:
      *.103.kz  -> шаблонный харвестер (единая вёрстка, 9000+ хостов задёшево);
      остальное -> унифицированный generic (render через Jina + извлечение Groq).
    Возвращает (clinic_meta | None, список raw-строк). Метаданные клиники больше НЕ
    выбрасываем — run_parse сохранит их в raw_clinics (нужно ingest для новых клиник)."""
    h = (host or "").strip().lower()
    if h == "103.kz" or h.endswith(".103.kz"):
        return _parse_103kz_source(harvest, host)
    return _parse_generic_source(host)


# ---------- источники: file (PDF/DOCX/XLSX/XLS) ----------
def _parse_file_source(path):
    """path -> (None, список raw-строк). У файлового источника нет метаданных клиники."""
    from .fileparse import parse_file
    try:
        recs = parse_file(path)
    except Exception as exc:
        exc.stage = "parse"
        raise
    base = os.path.basename(path)
    rows = []
    for r in recs:
        rows.append({
            "source_kind": "file", "source": base, "clinic_host": None,
            "raw_name": r["raw_name"], "category": r.get("section"),
            "price": r.get("price"), "price_text": None, "currency": r.get("currency", "KZT"),
            "is_from": False, "on_request": r.get("price") is None,
            "content_hash": _hash(base, r["raw_name"], r.get("price")),
        })
    return None, rows


def _expand_paths(specs):
    out = []
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        matched = glob.glob(os.path.join(ROOT, spec)) or glob.glob(spec)
        out.extend(matched or [spec])
    return out


# ---------- оркестратор ----------
def run_parse(kind: str, sources=None, limit: int = 50, trigger: str = "manual") -> int:
    """Один прогон парсинга. Возвращает run_id."""
    OpsBase.metadata.create_all(engine)  # на случай первого запуска
    db = SessionLocal()
    run = ParseRun(source_kind=kind, trigger=trigger, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    _log(db, run_id, f"старт прогона: kind={kind}, trigger={trigger}, limit={limit}", stage="run")

    try:
        if kind == "web":
            harvest = _import_harvester()
            items = _web_hosts(db, sources, limit)
            handler = lambda s: _parse_web_source(harvest, s)
            if not sources:  # прогон по источникам из БД — отметим их как использованные
                try:
                    from .ops_models import ParseSource
                    now = dt.datetime.now(dt.timezone.utc)
                    for s in db.query(ParseSource).filter(ParseSource.enabled.is_(True)).all():
                        s.last_run_at = now
                    db.commit()
                except Exception:
                    db.rollback()
        elif kind == "file":
            items = _expand_paths(sources or [])
            handler = _parse_file_source
        else:
            run.status = "failed"; run.note = f"неизвестный kind: {kind}"
            run.finished_at = dt.datetime.now(dt.timezone.utc)
            _log(db, run_id, f"неизвестный kind: {kind}", level="error", stage="run")
            db.commit(); db.close()
            raise SystemExit(f"неизвестный kind: {kind}")

        run.sources_total = len(items)
        db.commit()
        _log(db, run_id, f"источников к обработке: {len(items)}", stage="run")
        ok = failed = rows_raw = rows_new = rows_dup = 0

        for src in items:
            try:
                clinic, rows = handler(src)
            except Exception as exc:
                failed += 1
                _log_error(db, run_id, str(src), getattr(exc, "stage", "parse"), exc)
                continue
            try:
                if clinic:
                    _store_clinic(db, run_id, clinic)   # метаданные клиники в raw_clinics
                new, dup = _store_rows(db, run_id, rows)
            except Exception as exc:
                failed += 1
                db.rollback()
                _log_error(db, run_id, str(src), "store", exc)
                continue
            ok += 1
            rows_raw += len(rows); rows_new += new; rows_dup += dup
            run.sources_ok = ok; run.sources_failed = failed
            run.rows_raw = rows_raw; run.rows_new = rows_new; run.rows_dup = rows_dup
            db.commit()
            _log(db, run_id, f"ок: строк {len(rows)} (новых {new}, дублей {dup})",
                 source=str(src), stage="store")

        run.sources_ok = ok
        run.sources_failed = failed
        run.rows_raw = rows_raw
        run.rows_new = rows_new
        run.rows_dup = rows_dup
        run.status = "done"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.note = f"источников: ok={ok}, ошибок={failed}; строк: {rows_raw} (новых {rows_new}, дублей {rows_dup})"
        db.commit()
        _log(db, run_id, "прогон завершён: " + run.note, stage="run")
    except SystemExit:
        raise
    except Exception as exc:
        # любая непредвиденная ошибка прогона — фиксируем как failed, а не «висящий running»
        db.rollback()
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.note = f"прогон прерван ошибкой: {exc}"
        db.commit()
        _log(db, run_id, str(exc), level="error", stage="run")
        db.close()
        raise
    db.close()
    return run_id


def main():
    ap = argparse.ArgumentParser(description="MedPrice — модуль сбора данных (ТЗ §3.1)")
    ap.add_argument("--kind", choices=["web", "file"], required=True)
    ap.add_argument("--limit", type=int, default=50, help="макс. источников за прогон (web, из frontier)")
    ap.add_argument("--hosts", default="", help="web: список хостов через запятую (вместо frontier)")
    ap.add_argument("--paths", default="", help="file: пути/глобы через запятую")
    ap.add_argument("--trigger", default="cron")
    args = ap.parse_args()

    sources = None
    if args.kind == "web" and args.hosts:
        sources = [h.strip() for h in args.hosts.split(",") if h.strip()]
    if args.kind == "file":
        sources = [p for p in args.paths.split(",") if p.strip()]

    run_id = run_parse(args.kind, sources=sources, limit=args.limit, trigger=args.trigger)
    print(f"run_id={run_id}", flush=True)


if __name__ == "__main__":
    main()
