"""
MedPrice KZ — API агрегатора и сравнения цен на медуслуги в Казахстане.

Источники данных:
  • web  — харвест сети 103.kz
  • file — приложенный архив прайсов 8 клиник (нормализован на «Справочник услуг»)

Запуск:  uvicorn app.main:app --reload   ·   Docs: /docs
"""
import datetime as dt
import statistics
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    City, Clinic, ParseLog, PriceHistory, PriceOffer, Service, Subscription, UnmatchedItem,
)
from .normalize import Matcher, normalize
from .auth import verify_staff
from . import notify

app = FastAPI(
    title="MedPrice KZ",
    description="Агрегатор и сравнение цен на медуслуги Казахстана. Данные: веб-харвест 103.kz "
                "+ архив прайсов клиник, нормализованные на единый справочник услуг.",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_matcher = Matcher()  # live-матчинг для /api/ingest/match


# ---------- схемы ----------
class OfferOut(BaseModel):
    clinic: str
    city: Optional[str]
    address: Optional[str]
    raw_name: str
    price: int
    is_from: bool
    source_url: Optional[str]
    source_type: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    twogis_url: Optional[str] = None
    parsed_at: Optional[str] = None   # когда данные распарсены (актуальность)
    source_file: Optional[str] = None  # имя архивного файла (для source_type='file')


class CompareStats(BaseModel):
    count: int
    min: int
    max: int
    avg: int
    median: int
    savings: int
    savings_pct: float


class CompareOut(BaseModel):
    code: str
    name: str
    category: Optional[str]
    is_curated: bool
    is_reference: bool = False
    tarificator: Optional[str] = None
    city: Optional[str]
    last_updated: Optional[str] = None
    stats: CompareStats
    offers: list[OfferOut]


def _price_stats(prices: list[int]) -> CompareStats:
    mn, mx = min(prices), max(prices)
    return CompareStats(
        count=len(prices), min=mn, max=mx,
        avg=round(statistics.mean(prices)), median=round(statistics.median(prices)),
        savings=mx - mn, savings_pct=round((mx - mn) / mx * 100, 1) if mx else 0.0,
    )


def _apply_source(q, source):
    if source == "web":
        return q.filter((PriceOffer.source_type == "web") | (PriceOffer.source_type.is_(None)))
    if source == "file":
        return q.filter(PriceOffer.source_type == "file")
    return q


# ---------- базовые ----------
@app.get("/")
def root():
    return {"service": "MedPrice KZ", "docs": "/docs", "health": "ok"}


def _count_if(cond):
    """Условный COUNT внутри одного запроса (заменяет отдельный round-trip к БД)."""
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    # 4 запроса вместо 10: счётчики по каждой таблице сведены в один проход.
    cities = db.query(func.count(City.id)).scalar()
    clinics, clinics_file = db.query(
        func.count(Clinic.id), _count_if(Clinic.source_type == "file")
    ).one()
    services, reference_services, comparable_services, curated_services = db.query(
        func.count(Service.id),
        _count_if(Service.is_reference),
        _count_if(Service.n_clinics >= 2),
        _count_if(Service.is_curated),
    ).one()
    offers, priced_offers, offers_file = db.query(
        func.count(PriceOffer.id),
        _count_if(PriceOffer.price.isnot(None)),
        _count_if(PriceOffer.source_type == "file"),
    ).one()
    return {
        "cities": cities,
        "clinics": clinics,
        "clinics_file": clinics_file,
        "services": services,
        "reference_services": reference_services,
        "comparable_services": comparable_services,
        "offers": offers,
        "priced_offers": priced_offers,
        "offers_file": offers_file,
        "curated_services": curated_services,
    }


@app.get("/api/cities")
def cities(db: Session = Depends(get_db)):
    rows = (
        db.query(City.name, func.count(Clinic.id))
        .outerjoin(Clinic, Clinic.city_id == City.id)
        .group_by(City.id).order_by(func.count(Clinic.id).desc()).all()
    )
    return [{"city": n, "clinics": c} for n, c in rows]


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)):
    rows = (
        db.query(Service.category, func.count(Service.id))
        .filter(Service.n_clinics >= 2).group_by(Service.category)
        .order_by(func.count(Service.id).desc()).all()
    )
    return [{"category": c, "services": n} for c, n in rows]


@app.get("/api/services")
def services(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_clinics: int = Query(2, ge=1),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Service).filter(Service.n_clinics >= min_clinics)
    if q:
        query = query.filter(Service.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(Service.category == category)
    rows = query.order_by(Service.n_clinics.desc(), Service.n_offers.desc()).limit(limit).all()
    return [
        {"code": s.code, "name": s.name, "category": s.category, "is_curated": s.is_curated,
         "is_reference": s.is_reference, "clinics": s.n_clinics, "offers": s.n_offers}
        for s in rows
    ]


def _clinic_min_prices(db, service_id, city=None, source="all"):
    """Возвращает {clinic_id: (min_price, offer, clinic, city)} — одна (минимальная) цена на клинику."""
    q = (
        db.query(PriceOffer, Clinic, City)
        .join(Clinic, Clinic.id == PriceOffer.clinic_id)
        .outerjoin(City, City.id == Clinic.city_id)
        .filter(PriceOffer.service_id == service_id, PriceOffer.price.isnot(None))
        .order_by(PriceOffer.price.asc())
    )
    if city:
        q = q.filter(City.name == city)
    q = _apply_source(q, source)
    best = {}
    for po, cl, ct in q.all():
        if cl.id not in best:  # первая = минимальная (отсортировано по цене)
            best[cl.id] = (po, cl, ct)
    return best


def _search_price_agg(db, service_ids, city=None, source="all", max_price=None):
    """Агрегат диапазона цен по списку услуг ОДНИМ запросом (цена = минимум на клинику).

    Заменяет N+1 вызовов _clinic_min_prices в /api/search: сперва считаем минимум
    на (услуга, клиника), затем сводим в min/max/avg/clinics на услугу.
    Возвращает {service_id: (clinics, min, max, avg)}.
    """
    if not service_ids:
        return {}
    inner = (
        db.query(
            PriceOffer.service_id.label("sid"),
            PriceOffer.clinic_id.label("cid"),
            func.min(PriceOffer.price).label("p"),
        )
        .join(Clinic, Clinic.id == PriceOffer.clinic_id)
        .filter(PriceOffer.service_id.in_(service_ids), PriceOffer.price.isnot(None))
    )
    if city:
        inner = inner.outerjoin(City, City.id == Clinic.city_id).filter(City.name == city)
    inner = _apply_source(inner, source)
    inner = inner.group_by(PriceOffer.service_id, PriceOffer.clinic_id).subquery()

    outer = db.query(
        inner.c.sid,
        func.count().label("clinics"),
        func.min(inner.c.p),
        func.max(inner.c.p),
        func.avg(inner.c.p),
    )
    if max_price:
        outer = outer.filter(inner.c.p <= max_price)
    rows = outer.group_by(inner.c.sid).all()
    return {sid: (clinics, mn, mx, round(float(avg))) for sid, clinics, mn, mx, avg in rows}


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=2),
    city: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[int] = None,
    source: str = Query("all", pattern="^(all|web|file)$"),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
):
    """Быстрый поиск: услуги + диапазон цен (одна цена на клинику)."""
    sq = db.query(Service).filter(Service.name.ilike(f"%{q}%"), Service.n_clinics >= 2)
    if category:
        sq = sq.filter(Service.category == category)
    rows = sq.order_by(Service.n_clinics.desc()).limit(limit * 2).all()
    # Один агрегатный запрос на все услуги-кандидаты вместо N+1 round-trips к БД.
    agg = _search_price_agg(db, [s.id for s in rows], city, source, max_price)
    out = []
    for s in rows:
        a = agg.get(s.id)
        if not a:
            continue
        clinics, mn, mx, avg = a
        out.append({
            "code": s.code, "name": s.name, "category": s.category,
            "is_curated": s.is_curated, "is_reference": s.is_reference,
            "clinics": clinics, "min_price": mn,
            "max_price": mx, "avg_price": avg,
        })
        if len(out) >= limit:
            break
    return {"query": q, "city": city, "results": out}


@app.get("/api/services/{code}/compare", response_model=CompareOut)
def compare(
    code: str,
    city: Optional[str] = None,
    source: str = Query("all", pattern="^(all|web|file)$"),
    db: Session = Depends(get_db),
):
    """Сравнение по клиникам: одна (минимальная) цена на клинику + статистика и экономия."""
    s = db.query(Service).filter(Service.code == code).first()
    if not s:
        raise HTTPException(404, "Услуга не найдена")
    best = _clinic_min_prices(db, s.id, city, source)
    if not best:
        raise HTTPException(404, "Нет цен по этой услуге (с учётом фильтра)")
    triples = sorted(best.values(), key=lambda x: x[0].price)
    # имя архивного файла на клинику (для пометки источника у file-офферов) — из журнала парсинга
    file_clinics = {cl.name for _, cl, _ in triples if cl.source_type == "file"}
    file_map = {}
    if file_clinics:
        file_map = {r.clinic: r.source_file for r in
                    db.query(ParseLog).filter(ParseLog.clinic.in_(file_clinics)).all()}
    offers, updated = [], []
    for po, cl, ct in triples:
        offers.append(OfferOut(
            clinic=cl.name, city=ct.name if ct else None, address=cl.address,
            raw_name=po.raw_name, price=po.price, is_from=bool(po.is_from),
            source_url=cl.source_url, source_type=po.source_type,
            rating=cl.rating, reviews_count=cl.reviews_count, twogis_url=cl.twogis_url,
            parsed_at=po.parsed_at.isoformat() if po.parsed_at else None,
            source_file=file_map.get(cl.name) if po.source_type == "file" else None,
        ))
        if po.parsed_at:
            updated.append(po.parsed_at)
    prices = [o.price for o in offers]
    return CompareOut(
        code=s.code, name=s.name, category=s.category, is_curated=s.is_curated,
        is_reference=s.is_reference, tarificator=s.tarificator_code, city=city,
        last_updated=max(updated).isoformat() if updated else None,
        stats=_price_stats(prices), offers=offers,
    )


@app.get("/api/clinics")
def clinics(
    city: Optional[str] = None,
    q: Optional[str] = None,
    source: str = Query("all", pattern="^(all|web|file)$"),
    with_coords: bool = Query(False),  # только клиники с координатами (для карты)
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Clinic, City).outerjoin(City, City.id == Clinic.city_id)
    if city:
        query = query.filter(City.name == city)
    if q:
        query = query.filter(Clinic.name.ilike(f"%{q}%"))
    if source != "all":
        query = query.filter(Clinic.source_type == source)
    if with_coords:
        query = query.filter(Clinic.lat.isnot(None), Clinic.lng.isnot(None))
    rows = query.limit(limit).all()
    return [
        {"id": cl.id, "name": cl.name, "city": ct.name if ct else None, "address": cl.address,
         "host": cl.host, "source_url": cl.source_url, "source_type": cl.source_type,
         "lat": cl.lat, "lng": cl.lng, "rating": cl.rating,
         "reviews_count": cl.reviews_count, "twogis_url": cl.twogis_url}
        for cl, ct in rows
    ]


@app.get("/api/clinics/{clinic_id}")
def clinic_card(clinic_id: int, limit: int = Query(300, le=2000), db: Session = Depends(get_db)):
    """Карточка клиники: контакты + все её услуги с ценами (одна на услугу)."""
    cl = db.query(Clinic).filter(Clinic.id == clinic_id).first()
    if not cl:
        raise HTTPException(404, "Клиника не найдена")
    ct = db.query(City).filter(City.id == cl.city_id).first()
    rows = (
        db.query(PriceOffer, Service)
        .join(Service, Service.id == PriceOffer.service_id)
        .filter(PriceOffer.clinic_id == clinic_id, PriceOffer.price.isnot(None))
        .order_by(PriceOffer.price.asc()).all()
    )
    seen, items = set(), []
    for po, s in rows:
        if s.id in seen:
            continue
        seen.add(s.id)
        items.append({"code": s.code, "service": s.name, "category": s.category,
                      "price": po.price, "raw_name": po.raw_name})
    items.sort(key=lambda x: (x["category"] or "", x["service"]))
    return {
        "id": cl.id, "name": cl.name, "city": ct.name if ct else None, "address": cl.address,
        "phone": cl.phone, "working_hours": cl.working_hours, "source_url": cl.source_url,
        "source_type": cl.source_type, "lat": cl.lat, "lng": cl.lng,
        "rating": cl.rating, "reviews_count": cl.reviews_count, "twogis_url": cl.twogis_url,
        "services_count": len(items), "services": items[:limit],
    }


@app.get("/api/unmatched")
def unmatched(
    q: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Очередь ручной разметки: строки прайсов, не привязанные к справочнику (ТЗ §3.2)."""
    base = db.query(UnmatchedItem, Clinic).outerjoin(Clinic, Clinic.id == UnmatchedItem.clinic_id)
    if q:
        base = base.filter(UnmatchedItem.raw_name.ilike(f"%{q}%"))
    total = base.count()
    rows = base.order_by(UnmatchedItem.id).offset(offset).limit(limit).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [
            {"id": u.id, "raw_name": u.raw_name, "code": u.code, "price": u.price,
             "clinic": cl.name if cl else None, "source_file": u.source_file}
            for u, cl in rows
        ],
    }


# ---------- админ-зона (только staff) ----------
import json as _json
import os as _os
import urllib.request as _urlreq
import urllib.error as _urlerr

from .ops_models import ParseRun, ParseError, RawPriceItem, LearnedMatch, ParseSource


@app.get("/api/admin/me")
def admin_me(staff: dict = Depends(verify_staff)):
    """Проверка доступа: вернёт {user_id, role}, если токен валиден и юзер в staff."""
    return staff


def _run_out(r: ParseRun) -> dict:
    return {
        "id": r.id, "source_kind": r.source_kind, "trigger": r.trigger, "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "sources_total": r.sources_total, "sources_ok": r.sources_ok,
        "sources_failed": r.sources_failed, "rows_raw": r.rows_raw,
        "rows_new": r.rows_new, "rows_dup": r.rows_dup, "note": r.note,
    }


@app.get("/api/admin/parse/runs")
def parse_runs(limit: int = Query(30, le=100), staff: dict = Depends(verify_staff),
               db: Session = Depends(get_db)):
    """Журнал прогонов парсера (ТЗ §3.1)."""
    rows = db.query(ParseRun).order_by(ParseRun.id.desc()).limit(limit).all()
    return [_run_out(r) for r in rows]


@app.get("/api/admin/parse/runs/{run_id}")
def parse_run_detail(run_id: int, staff: dict = Depends(verify_staff),
                     db: Session = Depends(get_db)):
    """Детали прогона: счётчики + ошибки по источникам с причинами."""
    r = db.query(ParseRun).get(run_id)
    if not r:
        raise HTTPException(404, "Прогон не найден")
    errs = (db.query(ParseError).filter(ParseError.run_id == run_id)
            .order_by(ParseError.id).limit(500).all())
    return {
        **_run_out(r),
        "errors": [
            {"source": e.source, "stage": e.stage, "error": e.error,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in errs
        ],
    }


class ParseRunBody(BaseModel):
    kind: str = "web"          # web | file
    limit: Optional[int] = 50  # сколько источников за прогон (web)
    hosts: Optional[str] = None
    paths: Optional[str] = None


def _dispatch_workflow(body: ParseRunBody) -> None:
    """Триггерит GitHub Actions workflow_dispatch. Нужны env GH_TOKEN, GH_REPO (owner/repo)."""
    token = _os.environ.get("GH_TOKEN", "")
    repo = _os.environ.get("GH_REPO", "")
    workflow = _os.environ.get("GH_PARSER_WORKFLOW", "parser.yml")
    ref = _os.environ.get("GH_REF", "main")
    if not token or not repo:
        raise HTTPException(
            501,
            "Ручной запуск из UI не настроен: задайте GH_TOKEN и GH_REPO в окружении бэкенда "
            "(парсинг идёт на GitHub-раннере). Cron и CLI работают и без этого.",
        )
    payload = {"ref": ref, "inputs": {
        "kind": body.kind,
        "limit": str(body.limit or 50),
        "hosts": body.hosts or "",
        "paths": body.paths or "",
    }}
    data = _json.dumps(payload).encode()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "User-Agent": "medprice-admin", "X-GitHub-Api-Version": "2022-11-28"}
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"

    def _post(u: str):
        _urlreq.urlopen(_urlreq.Request(u, data=data, headers=headers, method="POST"), timeout=15)

    try:
        try:
            _post(url)
        except _urlerr.HTTPError as e:
            # GitHub редиректит /repos/{owner}/{name} -> /repositories/{id} (после переименования
            # репо). urllib НЕ повторяет POST на 307/308 — делаем редирект вручную один раз.
            loc = e.headers.get("Location") if e.code in (301, 307, 308) else None
            if loc:
                _post(loc)
            else:
                raise
    except Exception as exc:
        raise HTTPException(502, f"GitHub отклонил запуск: {exc}")


@app.post("/api/admin/parse/run")
def parse_run_trigger(body: ParseRunBody, staff: dict = Depends(verify_staff),
                      db: Session = Depends(get_db)):
    """Ручной запуск парсинга из интерфейса (ТЗ §3.1). Делегирует воркеру на раннере."""
    _dispatch_workflow(body)
    run = ParseRun(source_kind=body.kind, trigger="manual", status="queued",
                   note=f"поставлено из админки ({staff.get('role')})")
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"status": "queued", "run": _run_out(run)}


# ---------- источники парсинга (ТЗ §3.1: управление целевыми сайтами) ----------
def _source_out(s: ParseSource) -> dict:
    return {
        "id": s.id, "kind": s.kind, "value": s.value, "label": s.label,
        "enabled": s.enabled, "note": s.note,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_count": s.last_count,
        "frontier_size": 9248 if s.kind == "frontier" else None,
    }


@app.get("/api/admin/sources")
def sources_list(staff: dict = Depends(verify_staff), db: Session = Depends(get_db)):
    """Список источников парсинга."""
    rows = db.query(ParseSource).order_by(ParseSource.kind.desc(), ParseSource.id).all()
    return [_source_out(s) for s in rows]


class SourceCreate(BaseModel):
    value: str                       # хост, напр. kdl.103.kz
    label: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/admin/sources")
def sources_add(body: SourceCreate, staff: dict = Depends(verify_staff),
                db: Session = Depends(get_db)):
    """Добавить отдельный сайт-источник (kind='host')."""
    host = body.value.strip().replace("https://", "").replace("http://", "").strip("/")
    if not host:
        raise HTTPException(400, "Пустой адрес источника")
    if db.query(ParseSource).filter(ParseSource.value == host).first():
        raise HTTPException(409, "Такой источник уже есть")
    s = ParseSource(kind="host", value=host, label=body.label or host, note=body.note,
                    enabled=True, added_by=staff.get("user_id"))
    db.add(s)
    db.commit()
    db.refresh(s)
    return _source_out(s)


class SourcePatch(BaseModel):
    enabled: Optional[bool] = None
    label: Optional[str] = None
    note: Optional[str] = None


@app.patch("/api/admin/sources/{source_id}")
def sources_patch(source_id: int, body: SourcePatch, staff: dict = Depends(verify_staff),
                  db: Session = Depends(get_db)):
    """Включить/выключить или отредактировать источник."""
    s = db.query(ParseSource).get(source_id)
    if not s:
        raise HTTPException(404, "Источник не найден")
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.label is not None:
        s.label = body.label
    if body.note is not None:
        s.note = body.note
    db.commit()
    db.refresh(s)
    return _source_out(s)


@app.delete("/api/admin/sources/{source_id}")
def sources_delete(source_id: int, staff: dict = Depends(verify_staff),
                   db: Session = Depends(get_db)):
    """Удалить источник. Авто-источник 103.kz (frontier) удалять нельзя — только выключить."""
    s = db.query(ParseSource).get(source_id)
    if not s:
        raise HTTPException(404, "Источник не найден")
    if s.kind == "frontier":
        raise HTTPException(400, "Базовый источник 103.kz нельзя удалить — выключите его вместо удаления.")
    db.delete(s)
    db.commit()
    return {"status": "deleted", "id": source_id}


# ---------- очередь ручной разметки (ТЗ §3.2) ----------
@app.get("/api/admin/unmatched")
def admin_unmatched(q: Optional[str] = None, limit: int = Query(50, le=200),
                    offset: int = Query(0, ge=0), staff: dict = Depends(verify_staff),
                    db: Session = Depends(get_db)):
    """Непривязанные строки прайсов, сгруппированные по названию (частые — выше)."""
    grp = (db.query(UnmatchedItem.raw_name.label("raw_name"),
                    func.count().label("cnt"),
                    func.min(UnmatchedItem.price).label("min_price"),
                    func.max(UnmatchedItem.price).label("max_price"))
           .group_by(UnmatchedItem.raw_name))
    if q:
        grp = grp.filter(UnmatchedItem.raw_name.ilike(f"%{q}%"))
    total = grp.count()
    rows = grp.order_by(func.count().desc(), UnmatchedItem.raw_name).offset(offset).limit(limit).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [{"raw_name": r.raw_name, "count": r.cnt,
                   "min_price": r.min_price, "max_price": r.max_price} for r in rows],
    }


class AssignBody(BaseModel):
    raw_name: str
    service_code: str


def _refresh_service_counts(db, service_id: int):
    agg = (db.query(func.count(PriceOffer.id),
                    func.count(func.distinct(PriceOffer.clinic_id)))
           .filter(PriceOffer.service_id == service_id).first())
    s = db.query(Service).get(service_id)
    if s:
        s.n_offers, s.n_clinics = agg[0] or 0, agg[1] or 0


@app.post("/api/admin/unmatched/assign")
def admin_unmatched_assign(body: AssignBody, staff: dict = Depends(verify_staff),
                           db: Session = Depends(get_db)):
    """Привязать все строки с этим названием к канонической услуге → создать сравнимые цены."""
    svc = db.query(Service).filter(Service.code == body.service_code).first()
    if not svc:
        raise HTTPException(404, "Услуга с таким кодом не найдена")
    items = db.query(UnmatchedItem).filter(UnmatchedItem.raw_name == body.raw_name).all()
    if not items:
        raise HTTPException(404, "Строки с таким названием уже нет в очереди")

    created = 0
    for u in items:
        if u.clinic_id is not None and u.price is not None:
            db.add(PriceOffer(
                clinic_id=u.clinic_id, service_id=svc.id, raw_name=u.raw_name,
                price=u.price, currency="KZT", match_method="manual", match_score=1.0,
                source_type="manual", parsed_at=dt.datetime.now(dt.timezone.utc), is_active=True,
            ))
            created += 1
        db.delete(u)

    # запомнить решение (переживает пересборку витрины) — upsert по norm_key
    nk = normalize(body.raw_name)
    lm = db.query(LearnedMatch).filter(LearnedMatch.norm_key == nk).first()
    if lm:
        lm.service_code, lm.service_name, lm.category = svc.code, svc.name, svc.category
        lm.occurrences = (lm.occurrences or 0) + len(items)
        lm.added_by = staff.get("user_id")
    else:
        db.add(LearnedMatch(norm_key=nk, service_code=svc.code, service_name=svc.name,
                            category=svc.category, raw_example=body.raw_name,
                            occurrences=len(items), added_by=staff.get("user_id")))
    db.commit()
    _refresh_service_counts(db, svc.id)
    db.commit()
    return {"status": "assigned", "raw_name": body.raw_name, "service": svc.name,
            "rows_closed": len(items), "offers_created": created}


class SkipBody(BaseModel):
    raw_name: str


@app.post("/api/admin/unmatched/skip")
def admin_unmatched_skip(body: SkipBody, staff: dict = Depends(verify_staff),
                         db: Session = Depends(get_db)):
    """Пометить строки как «не услуга» и убрать из очереди (решение запоминается)."""
    items = db.query(UnmatchedItem).filter(UnmatchedItem.raw_name == body.raw_name).all()
    if not items:
        raise HTTPException(404, "Строки с таким названием уже нет в очереди")
    n = len(items)
    for u in items:
        db.delete(u)
    nk = normalize(body.raw_name)
    lm = db.query(LearnedMatch).filter(LearnedMatch.norm_key == nk).first()
    if lm:
        lm.service_code, lm.occurrences = None, (lm.occurrences or 0) + n
        lm.added_by = staff.get("user_id")
    else:
        db.add(LearnedMatch(norm_key=nk, service_code=None, raw_example=body.raw_name,
                            occurrences=n, added_by=staff.get("user_id")))
    db.commit()
    return {"status": "skipped", "raw_name": body.raw_name, "rows_closed": n}


@app.get("/api/parse-log")
def parse_log(db: Session = Depends(get_db)):
    """Журнал парсинга источников (ТЗ §3.1)."""
    rows = db.query(ParseLog).order_by(ParseLog.id).all()
    return [
        {"source_file": r.source_file, "clinic": r.clinic, "rows_total": r.rows_total,
         "rows_matched": r.rows_matched, "rows_unmatched": r.rows_unmatched,
         "note": r.note, "parsed_at": r.parsed_at.isoformat() if r.parsed_at else None}
        for r in rows
    ]


# ---------- live-ингест (демо «кейса 1») ----------
class RawItem(BaseModel):
    name: str
    price: Optional[int] = None


class IngestBody(BaseModel):
    items: list[RawItem]
    city: Optional[str] = None


@app.post("/api/ingest/match")
def ingest_match(body: IngestBody, db: Session = Depends(get_db)):
    """Сырые строки прайса -> сопоставление с услугой + рыночный диапазон цен."""
    results = []
    for it in body.items:
        m = _matcher.match(it.name)
        entry = {"input": it.name, "input_price": it.price, "matched": None}
        if m:
            entry["matched"] = {"code": m["code"], "name": m["name"],
                                "method": m["method"], "score": m["score"]}
            s = db.query(Service).filter(Service.code == m["code"]).first()
            if s:
                best = _clinic_min_prices(db, s.id, body.city, "all")
                prices = [po.price for po, _, _ in best.values()]
                if prices:
                    mn = min(prices)
                    entry["market"] = {"clinics": len(prices), "min": mn, "max": max(prices),
                                       "avg": round(statistics.mean(prices))}
                    if it.price is not None:
                        entry["verdict"] = ("дороже рынка" if it.price > statistics.mean(prices)
                                            else "дешевле среднего")
                        entry["vs_min_pct"] = round((it.price - mn) / mn * 100, 1) if mn else 0.0
        results.append(entry)
    return {"count": len(results), "results": results}


# ---------- история цен (фича 3) ----------
def _service_current_price(db, service_id, clinic_id=None, city=None):
    """Текущая минимальная цена услуги: в конкретной клинике или по рынку (с фильтром города)."""
    if clinic_id:
        return (
            db.query(func.min(PriceOffer.price))
            .filter(PriceOffer.service_id == service_id, PriceOffer.clinic_id == clinic_id,
                    PriceOffer.price.isnot(None)).scalar()
        )
    best = _clinic_min_prices(db, service_id, city)
    prices = [po.price for po, _, _ in best.values()]
    return min(prices) if prices else None


@app.get("/api/services/{code}/history")
def service_history(code: str, db: Session = Depends(get_db)):
    """Динамика цены услуги по клиникам и годам (из архивных прайсов price_history)."""
    s = db.query(Service).filter(Service.code == code).first()
    if not s:
        raise HTTPException(404, "Услуга не найдена")
    rows = (
        db.query(PriceHistory, Clinic)
        .join(Clinic, Clinic.id == PriceHistory.clinic_id)
        .filter(PriceHistory.service_id == s.id)
        .order_by(Clinic.name, PriceHistory.recorded_at).all()
    )
    by_clinic: dict = {}
    for ph, cl in rows:
        d = by_clinic.setdefault(cl.id, {"clinic_id": cl.id, "clinic": cl.name, "points": []})
        d["points"].append({"date": ph.recorded_at.date().isoformat(),
                            "year": ph.recorded_at.year, "price": ph.price})
    series = sorted(by_clinic.values(), key=lambda x: x["clinic"])
    years = sorted({p["year"] for s_ in series for p in s_["points"]})
    return {"code": s.code, "name": s.name, "years": years, "series": series}


# ---------- сравнение «корзины» услуг по клиникам (фича 2) ----------
class BasketBody(BaseModel):
    codes: list[str]
    city: Optional[str] = None
    source: str = "all"


@app.post("/api/compare/basket")
def compare_basket(body: BasketBody, db: Session = Depends(get_db)):
    """Матрица: услуги (строки) × клиники (столбцы). Итог по клинике + самая выгодная."""
    codes = [c for c in dict.fromkeys(body.codes) if c][:25]
    services = db.query(Service).filter(Service.code.in_(codes)).all()
    smap = {s.code: s for s in services}
    ordered = [smap[c] for c in codes if c in smap]

    clinics: dict = {}
    for s in ordered:
        best = _clinic_min_prices(db, s.id, body.city, body.source)
        for po, cl, ct in best.values():
            entry = clinics.setdefault(cl.id, {
                "clinic_id": cl.id, "clinic": cl.name, "city": ct.name if ct else None,
                "address": cl.address, "lat": cl.lat, "lng": cl.lng,
                "source_url": cl.source_url, "rating": cl.rating,
                "reviews_count": cl.reviews_count, "twogis_url": cl.twogis_url, "prices": {},
            })
            entry["prices"][s.code] = po.price

    n_services = len(ordered)
    rows = []
    for c in clinics.values():
        covered = len(c["prices"])
        total = sum(c["prices"].values())
        rows.append({**c, "covered": covered, "total": total,
                     "is_complete": covered == n_services})
    # сначала с полным покрытием, дешевле — выше
    rows.sort(key=lambda r: (-r["covered"], r["total"]))
    cheapest_complete = next((r["clinic_id"] for r in rows if r["is_complete"]), None)
    return {
        "services": [{"code": s.code, "name": s.name, "category": s.category} for s in ordered],
        "clinics": rows,
        "cheapest_complete": cheapest_complete,
        "city": body.city,
    }


# ---------- подписки на цену (фича 1) ----------
class SubscribeBody(BaseModel):
    email: str
    code: str
    clinic_id: Optional[int] = None
    city: Optional[str] = None


def _sub_out(db, sub: Subscription):
    s = db.query(Service).filter(Service.id == sub.service_id).first()
    cl = db.query(Clinic).filter(Clinic.id == sub.clinic_id).first() if sub.clinic_id else None
    current = _service_current_price(db, sub.service_id, sub.clinic_id, sub.city)
    delta = (current - sub.last_price) if (current is not None and sub.last_price is not None) else None
    return {
        "id": sub.id, "email": sub.email,
        "code": s.code if s else None, "service": s.name if s else None,
        "clinic_id": sub.clinic_id, "clinic": cl.name if cl else None,
        "city": sub.city, "last_price": sub.last_price, "current_price": current,
        "delta": delta, "changed": bool(delta),
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@app.post("/api/subscriptions")
def subscribe(body: SubscribeBody, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Некорректный email")
    s = db.query(Service).filter(Service.code == body.code).first()
    if not s:
        raise HTTPException(404, "Услуга не найдена")
    existing = (
        db.query(Subscription)
        .filter(Subscription.email == email, Subscription.service_id == s.id,
                Subscription.clinic_id == body.clinic_id, Subscription.is_active == True)  # noqa: E712
        .first()
    )
    if existing:
        return {"status": "exists", "subscription": _sub_out(db, existing)}
    current = _service_current_price(db, s.id, body.clinic_id, body.city)
    sub = Subscription(email=email, service_id=s.id, clinic_id=body.clinic_id,
                       city=body.city, last_price=current, last_checked_at=dt.datetime.utcnow())
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"status": "created", "subscription": _sub_out(db, sub)}


@app.get("/api/subscriptions")
def list_subscriptions(email: str, db: Session = Depends(get_db)):
    email = email.strip().lower()
    subs = (
        db.query(Subscription)
        .filter(Subscription.email == email, Subscription.is_active == True)  # noqa: E712
        .order_by(Subscription.created_at.desc()).all()
    )
    return {"email": email, "subscriptions": [_sub_out(db, s) for s in subs]}


@app.delete("/api/subscriptions/{sub_id}")
def unsubscribe(sub_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Подписка не найдена")
    sub.is_active = False
    db.commit()
    return {"status": "deleted", "id": sub_id}


@app.post("/api/subscriptions/check")
def check_subscriptions(db: Session = Depends(get_db), notify_email: bool = True):
    """Сверка цен по активным подпискам: при изменении — письмо (если настроен SMTP/Resend)."""
    subs = db.query(Subscription).filter(Subscription.is_active == True).all()  # noqa: E712
    changes = []
    now = dt.datetime.utcnow()
    for sub in subs:
        current = _service_current_price(db, sub.service_id, sub.clinic_id, sub.city)
        sub.last_checked_at = now
        if current is not None and sub.last_price is not None and current != sub.last_price:
            s = db.query(Service).filter(Service.id == sub.service_id).first()
            info = {"id": sub.id, "email": sub.email, "service": s.name if s else sub.service_id,
                    "old": sub.last_price, "new": current, "sent": False}
            if notify_email:
                info["sent"] = notify.send_price_change(sub.email, s.name if s else "услуга",
                                                        sub.last_price, current)
            sub.last_price = current
            sub.last_notified_at = now
            changes.append(info)
    db.commit()
    return {"checked": len(subs), "changed": len(changes), "changes": changes,
            "email_backend": notify.backend_name()}
