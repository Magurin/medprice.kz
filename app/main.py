"""
MedPrice KZ — API агрегатора и сравнения цен на медуслуги в Казахстане.

Источники данных:
  • web  — харвест сети 103.kz
  • file — приложенный архив прайсов 8 клиник (нормализован на «Справочник услуг»)

Запуск:  uvicorn app.main:app --reload   ·   Docs: /docs
"""
import datetime as dt
import functools
import re
import statistics
import time as _time
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import case, func, or_
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


# Кэш на эдже Cloudflare: проставляем Cache-Control только на публичных GET-витринах.
# Витрина обновляется раз в сутки -> ответы можно держать на эдже у пользователей (КЗ).
# НЕ кэшируем: /api/admin/* (нет в списке), /api/subscriptions* (персональные),
# POST-эндпоинты, и любой запрос с Authorization.
_CACHEABLE_PATH = re.compile(r"^/api/(stats|cities|categories|services|search|clinics)(/|$)")


@app.middleware("http")
async def _public_cache_headers(request, call_next):
    response = await call_next(request)
    if (
        request.method == "GET"
        and response.status_code == 200
        and not request.headers.get("authorization")
        and _CACHEABLE_PATH.match(request.url.path)
    ):
        response.headers.setdefault(
            "Cache-Control",
            "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400",
        )
    return response


# ---------- схемы ----------
class OfferOut(BaseModel):
    clinic: str
    clinic_id: Optional[int] = None   # для ссылки на карточку клиники
    city: Optional[str]
    address: Optional[str]
    working_hours: Optional[str] = None  # режим работы (ТЗ §3.3)
    raw_name: str
    price: int
    is_from: bool
    source_url: Optional[str]
    source_type: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    twogis_url: Optional[str] = None
    lat: Optional[float] = None       # для сортировки по расстоянию
    lng: Optional[float] = None
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


# Витрина обновляется раз в сутки, а БД (eu-central-1) далеко от сервера (me-abudhabi-1,
# ~120мс RTT) — поэтому одинаковые агрегаты кэшируем в памяти процесса, чтобы не ходить
# в БД на каждый запрос. У каждого gunicorn-воркера свой кэш; ключ — имя функции + аргументы
# (кроме сессии БД). TTL с запасом меньше суточного цикла.
_TTL_CACHE: dict = {}


def ttl_cache(seconds: int):
    def deco(fn):
        @functools.wraps(fn)  # сохраняем сигнатуру -> FastAPI по-прежнему инжектит Depends
        def wrapper(*args, **kwargs):
            key = (fn.__name__, tuple(sorted((k, v) for k, v in kwargs.items() if k != "db")))
            now = _time.monotonic()
            cached = _TTL_CACHE.get(key)
            if cached and now - cached[0] < seconds:
                return cached[1]
            result = fn(*args, **kwargs)
            _TTL_CACHE[key] = (now, result)
            return result
        return wrapper
    return deco


# ---------- базовые ----------
@app.get("/")
def root():
    return {"service": "MedPrice KZ", "docs": "/docs", "health": "ok"}


def _count_if(cond):
    """Условный COUNT внутри одного запроса (заменяет отдельный round-trip к БД)."""
    return func.coalesce(func.sum(case((cond, 1), else_=0)), 0)


# Байесовский (IMDB-style) рейтинг: оценка с большим числом отзывов весомее.
# 4.9 при 1500 отзывах обходит 5.0 при 5 отзывах — количество тоже имеет вес.
RATING_PRIOR_M = 40.0   # «вес» априорной оценки, выраженный в отзывах
RATING_PRIOR_C = 4.6    # априорная средняя оценка по рынку


def _weighted_rating_expr():
    """ORDER BY-выражение: (v·R + m·C)/(v + m); клиники без оценки — в конец."""
    v = func.coalesce(Clinic.reviews_count, 0)
    return case(
        (Clinic.rating.is_(None), -1.0),
        else_=(v * Clinic.rating + RATING_PRIOR_M * RATING_PRIOR_C) / (v + RATING_PRIOR_M),
    )


@app.get("/api/stats")
@ttl_cache(3600)
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
@ttl_cache(3600)
def cities(db: Session = Depends(get_db)):
    rows = (
        db.query(City.name, func.count(Clinic.id))
        .outerjoin(Clinic, Clinic.city_id == City.id)
        .group_by(City.id).order_by(func.count(Clinic.id).desc()).all()
    )
    return [{"city": n, "clinics": c} for n, c in rows]


@app.get("/api/categories")
@ttl_cache(3600)
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
            clinic=cl.name, clinic_id=cl.id, city=ct.name if ct else None, address=cl.address,
            working_hours=cl.working_hours,
            raw_name=po.raw_name, price=po.price, is_from=bool(po.is_from),
            source_url=cl.source_url, source_type=po.source_type,
            rating=cl.rating, reviews_count=cl.reviews_count, twogis_url=cl.twogis_url,
            lat=cl.lat, lng=cl.lng,
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
    min_rating: float = Query(0, ge=0, le=5),
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
    if min_rating > 0:
        query = query.filter(Clinic.rating >= min_rating)
    # от лучших оценок к худшим, с учётом числа отзывов (байесовский вес)
    rows = query.order_by(_weighted_rating_expr().desc(), Clinic.name.asc()).limit(limit).all()
    return [
        {"id": cl.id, "name": cl.name, "city": ct.name if ct else None, "address": cl.address,
         "host": cl.host, "source_url": cl.source_url, "source_type": cl.source_type,
         "lat": cl.lat, "lng": cl.lng, "rating": cl.rating,
         "reviews_count": cl.reviews_count, "twogis_url": cl.twogis_url}
        for cl, ct in rows
    ]


# Точное число клиник под текущие фильтры (для счётчика — список отдаётся с потолком limit).
# Должен быть объявлен ДО /api/clinics/{clinic_id}, иначе "count" уйдёт в int-параметр.
@app.get("/api/clinics/count")
def clinics_count(
    city: Optional[str] = None,
    q: Optional[str] = None,
    source: str = Query("all", pattern="^(all|web|file)$"),
    with_coords: bool = Query(False),
    min_rating: float = Query(0, ge=0, le=5),
    db: Session = Depends(get_db),
):
    query = db.query(func.count(Clinic.id)).outerjoin(City, City.id == Clinic.city_id)
    if city:
        query = query.filter(City.name == city)
    if q:
        query = query.filter(Clinic.name.ilike(f"%{q}%"))
    if source != "all":
        query = query.filter(Clinic.source_type == source)
    if with_coords:
        query = query.filter(Clinic.lat.isnot(None), Clinic.lng.isnot(None))
    if min_rating > 0:
        query = query.filter(Clinic.rating >= min_rating)
    return {"count": query.scalar() or 0}


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

from .ops_models import (
    ParseRun, ParseError, ParseRunLog, RawPriceItem, LearnedMatch, ParseSource,
    ParseSchedule, OpsBase,
)
from .database import engine as _ops_engine
from . import scheduling


@app.get("/api/admin/me")
def admin_me(staff: dict = Depends(verify_staff)):
    """Проверка доступа: вернёт {user_id, role}, если токен валиден и юзер в staff."""
    return staff


def _run_out(r: ParseRun) -> dict:
    duration = None
    if r.started_at and r.finished_at:
        duration = round((r.finished_at - r.started_at).total_seconds(), 1)
    return {
        "id": r.id, "source_kind": r.source_kind, "trigger": r.trigger, "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_sec": duration,
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
    logs = (db.query(ParseRunLog).filter(ParseRunLog.run_id == run_id)
            .order_by(ParseRunLog.id).limit(2000).all())
    return {
        **_run_out(r),
        "errors": [
            {"source": e.source, "stage": e.stage, "error": e.error,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in errs
        ],
        "logs": [
            {"ts": l.ts.isoformat() if l.ts else None, "level": l.level,
             "source": l.source, "stage": l.stage, "message": l.message}
            for l in logs
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


# ---------- расписание ежедневного парсинга (ТЗ §3.1: запуск по cron) ----------
# Время задаётся из админки и хранится в БД (UTC). Workflow на GitHub Actions
# запускается часто и сверяется с этой записью через app.scheduling — так время
# можно менять из UI без правки cron в YAML. См. .github/workflows/parser.yml.
ALMATY_OFFSET = 5  # Asia/Almaty = UTC+5 (без перехода на летнее время)


def _schedule_out(s: ParseSchedule) -> dict:
    local_h = ((s.hour or 0) + ALMATY_OFFSET) % 24
    return {
        "enabled": s.enabled,
        "hour": s.hour, "minute": s.minute,
        "time_utc": f"{(s.hour or 0):02d}:{(s.minute or 0):02d}",
        "time_almaty": f"{local_h:02d}:{(s.minute or 0):02d}",
        "kind": s.kind, "run_limit": s.run_limit,
        "step_minutes": scheduling.STEP_MINUTES,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "updated_by": s.updated_by,
    }


@app.get("/api/admin/parse/schedule")
def parse_schedule_get(staff: dict = Depends(verify_staff), db: Session = Depends(get_db)):
    """Текущее расписание ежедневного парсинга (ТЗ §3.1)."""
    OpsBase.metadata.create_all(_ops_engine)  # таблицы могут ещё не существовать
    s = scheduling.get_or_create_schedule(db)
    return _schedule_out(s)


class ScheduleBody(BaseModel):
    enabled: Optional[bool] = None
    hour: Optional[int] = None       # UTC, 0..23
    minute: Optional[int] = None     # UTC, 0..59
    kind: Optional[str] = None       # web | file
    run_limit: Optional[int] = None


@app.put("/api/admin/parse/schedule")
def parse_schedule_put(body: ScheduleBody, staff: dict = Depends(verify_staff),
                       db: Session = Depends(get_db)):
    """Изменить время/параметры ежедневного парсинга из админки (ТЗ §3.1)."""
    OpsBase.metadata.create_all(_ops_engine)
    s = scheduling.get_or_create_schedule(db)
    if body.hour is not None:
        if not 0 <= body.hour <= 23:
            raise HTTPException(400, "Час должен быть в диапазоне 0..23 (UTC)")
        s.hour = body.hour
    if body.minute is not None:
        if not 0 <= body.minute <= 59:
            raise HTTPException(400, "Минуты должны быть в диапазоне 0..59")
        s.minute = body.minute
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.kind is not None:
        if body.kind not in ("web", "file"):
            raise HTTPException(400, "kind должен быть web или file")
        s.kind = body.kind
    if body.run_limit is not None:
        if body.run_limit < 1:
            raise HTTPException(400, "Лимит должен быть положительным")
        s.run_limit = body.run_limit
    s.updated_by = staff.get("user_id")
    db.commit()
    db.refresh(s)
    return _schedule_out(s)


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


# ============================================================================
# Ручное ведение каталога модераторами (ТЗ §3.2): клиники, услуги, цены + импорт
#   прайс-листов (HTML / PDF / DOCX / Excel) с авто-распознаванием и правкой.
# Все данные пишутся в основную витрину с пометкой source_type='manual'|'file',
# чтобы переживать пересборку ingest (см. app/ingest.py: DELETE только 'web').
# ============================================================================
from .fileparse import parse_bytes, parse_html_string, SUPPORTED_EXT

MAX_UPLOAD = 25 * 1024 * 1024  # 25 МБ на прайс-файл


def _slug_host(name: str) -> str:
    base = "manual-" + normalize(name).replace(" ", "-")[:60]
    return base.strip("-") or "manual-clinic"


def _record_price_point(db, clinic_id, service_id, price, raw_name=None, source="manual"):
    """Точка истории изменения цены — пишем, только если цена отличается от последней
    записанной для пары клиника+услуга (см. также срез в app/ingest.py)."""
    if price is None or clinic_id is None or service_id is None:
        return
    last = (db.query(PriceHistory.price)
            .filter(PriceHistory.clinic_id == clinic_id,
                    PriceHistory.service_id == service_id)
            .order_by(PriceHistory.recorded_at.desc(), PriceHistory.id.desc()).first())
    if last and last[0] == price:
        return
    db.add(PriceHistory(clinic_id=clinic_id, service_id=service_id, price=price,
                        recorded_at=dt.datetime.now(dt.timezone.utc),
                        raw_name=raw_name, source_file=source))


def _ensure_city(db, name):
    name = (name or "").strip()
    if not name:
        return None
    c = db.query(City).filter(City.name == name).first()
    if not c:
        c = City(name=name)  # id из sequence cities_id_seq
        db.add(c)
        db.flush()
    return c.id


def _ensure_service(db, code=None, name=None, category=None, method="manual",
                    curated=False):
    """Найти услугу по коду или создать новую (для ручной привязки/импорта)."""
    if code:
        s = db.query(Service).filter(Service.code == code).first()
        if s:
            return s
    if not code:
        if not name:
            return None
        code = "manual:" + normalize(name)
        s = db.query(Service).filter(Service.code == code).first()
        if s:
            return s
    s = Service(code=code, name=(name or code), category=(category or "Прочее"),
                is_curated=curated, match_method=method, n_offers=0, n_clinics=0)
    db.add(s)
    db.flush()
    return s


# ---------- клиники ----------
def _clinic_admin_out(c: Clinic, city_name=None, n_offers=None) -> dict:
    return {
        "id": c.id, "host": c.host, "name": c.name,
        "city": city_name, "city_id": c.city_id, "address": c.address,
        "phone": c.phone, "working_hours": c.working_hours,
        "source_url": c.source_url, "source_type": c.source_type,
        "lat": c.lat, "lng": c.lng, "rating": c.rating,
        "reviews_count": c.reviews_count, "n_offers": n_offers,
    }


@app.get("/api/admin/clinics")
def admin_clinics(q: Optional[str] = None, limit: int = Query(50, le=200),
                  offset: int = Query(0, ge=0), staff: dict = Depends(verify_staff),
                  db: Session = Depends(get_db)):
    """Список клиник для модерации (поиск по названию/host)."""
    base = db.query(Clinic, City.name).outerjoin(City, City.id == Clinic.city_id)
    if q:
        like = f"%{q.strip()}%"
        base = base.filter(or_(Clinic.name.ilike(like), Clinic.host.ilike(like)))
    total = base.count()
    rows = base.order_by(Clinic.name).offset(offset).limit(limit).all()
    ids = [c.id for c, _ in rows]
    counts = dict(
        db.query(PriceOffer.clinic_id, func.count())
        .filter(PriceOffer.clinic_id.in_(ids)).group_by(PriceOffer.clinic_id).all()
    ) if ids else {}
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [_clinic_admin_out(c, cn, counts.get(c.id, 0)) for c, cn in rows],
    }


class ClinicCreate(BaseModel):
    name: str
    city: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    working_hours: Optional[str] = None
    source_url: Optional[str] = None
    host: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@app.post("/api/admin/clinics")
def admin_clinic_create(body: ClinicCreate, staff: dict = Depends(verify_staff),
                        db: Session = Depends(get_db)):
    """Добавить клинику вручную (source_type='manual')."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Укажите название клиники")
    host = (body.host or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    if host:
        if db.query(Clinic).filter(Clinic.host == host).first():
            raise HTTPException(409, "Клиника с таким адресом (host) уже есть")
    else:
        base = _slug_host(name)
        host, i = base, 1
        while db.query(Clinic).filter(Clinic.host == host).first():
            i += 1
            host = f"{base}-{i}"
    c = Clinic(
        host=host, name=name, city_id=_ensure_city(db, body.city),  # id из sequence
        address=body.address, phone=body.phone, working_hours=body.working_hours,
        source_url=body.source_url, source_type="manual", lat=body.lat, lng=body.lng,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _clinic_admin_out(c, body.city, 0)


class ClinicPatch(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    working_hours: Optional[str] = None
    source_url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@app.patch("/api/admin/clinics/{clinic_id}")
def admin_clinic_patch(clinic_id: int, body: ClinicPatch,
                       staff: dict = Depends(verify_staff), db: Session = Depends(get_db)):
    """Поправить данные клиники (если что-то не так)."""
    c = db.query(Clinic).get(clinic_id)
    if not c:
        raise HTTPException(404, "Клиника не найдена")
    if body.name is not None:
        c.name = body.name.strip() or c.name
    if body.city is not None:
        c.city_id = _ensure_city(db, body.city)
    for f in ("address", "phone", "working_hours", "source_url", "lat", "lng"):
        v = getattr(body, f)
        if v is not None:
            setattr(c, f, v)
    db.commit()
    db.refresh(c)
    cn = db.query(City.name).filter(City.id == c.city_id).scalar() if c.city_id else None
    n = db.query(func.count(PriceOffer.id)).filter(PriceOffer.clinic_id == c.id).scalar()
    return _clinic_admin_out(c, cn, n)


@app.delete("/api/admin/clinics/{clinic_id}")
def admin_clinic_delete(clinic_id: int, staff: dict = Depends(verify_staff),
                        db: Session = Depends(get_db)):
    """Удалить клинику вместе с её ценами, историей и подписками."""
    c = db.query(Clinic).get(clinic_id)
    if not c:
        raise HTTPException(404, "Клиника не найдена")
    svc_ids = [r[0] for r in db.query(func.distinct(PriceOffer.service_id))
               .filter(PriceOffer.clinic_id == clinic_id).all()]
    db.query(PriceOffer).filter(PriceOffer.clinic_id == clinic_id).delete()
    db.query(PriceHistory).filter(PriceHistory.clinic_id == clinic_id).delete()
    db.query(Subscription).filter(Subscription.clinic_id == clinic_id).delete()
    db.query(UnmatchedItem).filter(UnmatchedItem.clinic_id == clinic_id).delete()
    db.delete(c)
    db.commit()
    for sid in svc_ids:
        _refresh_service_counts(db, sid)
    db.commit()
    return {"status": "deleted", "id": clinic_id}


# ---------- услуги (канонический справочник) ----------
class ServiceCreate(BaseModel):
    name: str
    category: Optional[str] = None
    code: Optional[str] = None


@app.post("/api/admin/services")
def admin_service_create(body: ServiceCreate, staff: dict = Depends(verify_staff),
                         db: Session = Depends(get_db)):
    """Создать каноническую услугу вручную."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Укажите название услуги")
    code = (body.code or "").strip() or ("manual:" + normalize(name))
    if db.query(Service).filter(Service.code == code).first():
        raise HTTPException(409, "Услуга с таким кодом уже есть")
    s = Service(code=code, name=name, category=(body.category or "Прочее"),
                is_curated=True, match_method="manual", n_offers=0, n_clinics=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "code": s.code, "name": s.name, "category": s.category}


class ServicePatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None


@app.patch("/api/admin/services/{service_id}")
def admin_service_patch(service_id: int, body: ServicePatch,
                        staff: dict = Depends(verify_staff), db: Session = Depends(get_db)):
    """Поправить название/категорию услуги."""
    s = db.query(Service).get(service_id)
    if not s:
        raise HTTPException(404, "Услуга не найдена")
    if body.name is not None and body.name.strip():
        s.name = body.name.strip()
    if body.category is not None:
        s.category = body.category.strip() or s.category
    db.commit()
    db.refresh(s)
    return {"id": s.id, "code": s.code, "name": s.name, "category": s.category}


# ---------- цены клиники (ручная правка) ----------
def _offer_out(o: PriceOffer, s: Service) -> dict:
    return {
        "id": o.id, "raw_name": o.raw_name, "price": o.price,
        "on_request": o.on_request, "is_from": o.is_from,
        "source_type": o.source_type, "match_method": o.match_method,
        "service_code": s.code if s else None,
        "service_name": s.name if s else None,
        "category": s.category if s else None,
    }


@app.get("/api/admin/clinics/{clinic_id}/offers")
def admin_clinic_offers(clinic_id: int, staff: dict = Depends(verify_staff),
                        db: Session = Depends(get_db)):
    """Все цены клиники с привязкой к услуге (для правки)."""
    c = db.query(Clinic).get(clinic_id)
    if not c:
        raise HTTPException(404, "Клиника не найдена")
    rows = (db.query(PriceOffer, Service)
            .join(Service, Service.id == PriceOffer.service_id)
            .filter(PriceOffer.clinic_id == clinic_id)
            .order_by(PriceOffer.raw_name).all())
    return {"clinic_id": clinic_id, "clinic": c.name,
            "offers": [_offer_out(o, s) for o, s in rows]}


class OfferCreate(BaseModel):
    clinic_id: int
    raw_name: str
    price: Optional[int] = None
    service_code: Optional[str] = None   # привязать к существующей услуге
    service_name: Optional[str] = None   # либо создать новую с этим названием
    category: Optional[str] = None


@app.post("/api/admin/offers")
def admin_offer_create(body: OfferCreate, staff: dict = Depends(verify_staff),
                       db: Session = Depends(get_db)):
    """Добавить услугу+цену клинике вручную."""
    c = db.query(Clinic).get(body.clinic_id)
    if not c:
        raise HTTPException(404, "Клиника не найдена")
    raw = (body.raw_name or "").strip()
    if not raw:
        raise HTTPException(400, "Укажите название услуги в прайсе")
    if body.service_code:
        svc = _ensure_service(db, code=body.service_code, name=body.service_name,
                              category=body.category)
    elif body.service_name:
        svc = _ensure_service(db, name=body.service_name, category=body.category)
    else:
        m = _matcher.match(raw)
        svc = _ensure_service(db, code=m["code"], name=m["name"],
                              category=m["category"], method=m["method"])
    if not svc:
        raise HTTPException(400, "Не удалось определить услугу")
    o = PriceOffer(
        clinic_id=c.id, service_id=svc.id, raw_name=raw, price=body.price,
        currency="KZT", on_request=(body.price is None), match_method="manual",
        match_score=1.0, source_type="manual",
        parsed_at=dt.datetime.now(dt.timezone.utc), is_active=True,
    )
    db.add(o)
    _record_price_point(db, c.id, svc.id, body.price, raw, "manual")
    db.commit()
    _refresh_service_counts(db, svc.id)
    db.commit()
    db.refresh(o)
    return _offer_out(o, svc)


class OfferPatch(BaseModel):
    raw_name: Optional[str] = None
    price: Optional[int] = None
    on_request: Optional[bool] = None
    service_code: Optional[str] = None   # перепривязать к другой услуге


@app.patch("/api/admin/offers/{offer_id}")
def admin_offer_patch(offer_id: int, body: OfferPatch,
                      staff: dict = Depends(verify_staff), db: Session = Depends(get_db)):
    """Поправить цену/название/привязку строки прайса."""
    o = db.query(PriceOffer).get(offer_id)
    if not o:
        raise HTTPException(404, "Строка прайса не найдена")
    old_sid = o.service_id
    if body.raw_name is not None and body.raw_name.strip():
        o.raw_name = body.raw_name.strip()
    if body.price is not None:
        o.price = body.price
        o.on_request = False
    if body.on_request is not None:
        o.on_request = body.on_request
        if body.on_request:
            o.price = None
    if body.service_code:
        svc = db.query(Service).filter(Service.code == body.service_code).first()
        if not svc:
            raise HTTPException(404, "Услуга с таким кодом не найдена")
        o.service_id = svc.id
    if body.price is not None:
        _record_price_point(db, o.clinic_id, o.service_id, o.price, o.raw_name, "manual")
    db.commit()
    if o.service_id != old_sid:
        _refresh_service_counts(db, old_sid)
    _refresh_service_counts(db, o.service_id)
    db.commit()
    s = db.query(Service).get(o.service_id)
    return _offer_out(o, s)


@app.delete("/api/admin/offers/{offer_id}")
def admin_offer_delete(offer_id: int, staff: dict = Depends(verify_staff),
                       db: Session = Depends(get_db)):
    """Удалить строку прайса."""
    o = db.query(PriceOffer).get(offer_id)
    if not o:
        raise HTTPException(404, "Строка прайса не найдена")
    sid = o.service_id
    db.delete(o)
    db.commit()
    _refresh_service_counts(db, sid)
    db.commit()
    return {"status": "deleted", "id": offer_id}


# ---------- импорт прайс-листов (HTML/PDF/DOCX/Excel) с авто-распознаванием ----------
def _import_preview(db, recs: list, source: str) -> dict:
    """Распознанные строки + авто-сопоставление с услугой (учитывая ручные решения)."""
    learned = {lm.norm_key: lm for lm in db.query(LearnedMatch).all()}
    rows, auto = [], 0
    for r in recs:
        nm = (r.get("raw_name") or "").strip()
        if not nm:
            continue
        entry = {"raw_name": nm, "price": r.get("price"), "unit": r.get("unit"),
                 "section": r.get("section"), "code": r.get("code"),
                 "match": None, "known_skip": False}
        lm = learned.get(normalize(nm))
        if lm is not None and lm.service_code is None:
            entry["known_skip"] = True            # ранее помечено «не услуга»
        elif lm is not None and lm.service_code:
            entry["match"] = {"code": lm.service_code, "name": lm.service_name,
                              "category": lm.category, "method": "learned", "score": 1.0}
            auto += 1
        else:
            m = _matcher.match(nm)
            if m:
                entry["match"] = {"code": m["code"], "name": m["name"],
                                  "category": m["category"], "method": m["method"],
                                  "score": m["score"]}
                if m["method"] in ("curated", "curated_fuzzy"):
                    auto += 1
        rows.append(entry)
    return {"source": source, "total": len(rows), "auto_matched": auto, "rows": rows}


@app.post("/api/admin/import/parse")
async def admin_import_parse(request: Request, filename: str = Query(...),
                             staff: dict = Depends(verify_staff),
                             db: Session = Depends(get_db)):
    """Загрузить прайс-файл (тело запроса = байты файла, ?filename=…) и распознать.
    Ничего не пишет в БД — только превью для правки модератором."""
    data = await request.body()
    if not data:
        raise HTTPException(400, "Пустой файл")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Файл больше 25 МБ")
    try:
        recs = parse_bytes(data, filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(422, f"Не удалось разобрать файл: {e}")
    if not recs:
        raise HTTPException(422, "В файле не найдено строк прайса (название + цена). "
                                 "Проверьте формат или внесите услуги вручную.")
    return _import_preview(db, recs, filename)


class ImportUrlBody(BaseModel):
    url: str


@app.post("/api/admin/import/url")
def admin_import_url(body: ImportUrlBody, staff: dict = Depends(verify_staff),
                     db: Session = Depends(get_db)):
    """Распознать прайс с открытой веб-страницы (или файла по ссылке)."""
    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Укажите http(s)-ссылку")
    req = _urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0 medprice-admin"})
    try:
        with _urlreq.urlopen(req, timeout=25) as r:
            data = r.read(MAX_UPLOAD + 1)
    except Exception as e:
        raise HTTPException(502, f"Не удалось загрузить страницу: {e}")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Страница/файл больше 25 МБ")
    low = url.lower().split("?")[0]
    try:
        if low.endswith(SUPPORTED_EXT) and not low.endswith((".html", ".htm")):
            recs = parse_bytes(data, low)
        else:
            recs = parse_html_string(data.decode("utf-8", "ignore"))
    except Exception as e:
        raise HTTPException(422, f"Не удалось разобрать страницу: {e}")
    if not recs:
        raise HTTPException(422, "На странице не найдено строк прайса (название + цена).")
    return _import_preview(db, recs, url)


class ImportRow(BaseModel):
    raw_name: str
    price: Optional[int] = None
    service_code: Optional[str] = None   # подтверждённая услуга
    service_name: Optional[str] = None   # имя для новой услуги
    category: Optional[str] = None
    create_new: bool = False             # создать новую каноническую услугу
    skip: bool = False                   # не импортировать строку


class ImportCommit(BaseModel):
    clinic_id: int
    source: Optional[str] = None
    replace: bool = False                # заменить ранее импортированные цены клиники
    rows: list[ImportRow]


@app.post("/api/admin/import/commit")
def admin_import_commit(body: ImportCommit, staff: dict = Depends(verify_staff),
                        db: Session = Depends(get_db)):
    """Записать выверенные строки прайса как цены клиники (source_type='file')."""
    c = db.query(Clinic).get(body.clinic_id)
    if not c:
        raise HTTPException(404, "Клиника не найдена")
    now = dt.datetime.now(dt.timezone.utc)
    affected: set[int] = set()

    if body.replace:
        old = (db.query(PriceOffer)
               .filter(PriceOffer.clinic_id == c.id,
                       PriceOffer.source_type.in_(("file", "manual"))).all())
        for o in old:
            affected.add(o.service_id)
            db.delete(o)

    created, svc_created = 0, 0
    for row in body.rows:
        if row.skip:
            continue
        raw = (row.raw_name or "").strip()
        if not raw:
            continue
        if row.create_new:
            svc = _ensure_service(db, name=(row.service_name or raw),
                                  category=row.category, method="manual")
            if svc and svc.n_offers == 0:
                svc_created += 1
        elif row.service_code:
            existed = db.query(Service.id).filter(Service.code == row.service_code).first()
            svc = _ensure_service(db, code=row.service_code, name=row.service_name,
                                  category=row.category)
            if not existed and svc:
                svc_created += 1
        else:
            continue  # не привязано — пропускаем
        if not svc:
            continue
        db.add(PriceOffer(
            clinic_id=c.id, service_id=svc.id, raw_name=raw, price=row.price,
            currency="KZT", on_request=(row.price is None), match_method="import",
            match_score=1.0, source_type="file", parsed_at=now, is_active=True,
        ))
        _record_price_point(db, c.id, svc.id, row.price, raw, body.source or "import")
        created += 1
        affected.add(svc.id)
        # запоминаем решение (переживает пересборку витрины)
        nk = normalize(raw)
        lm = db.query(LearnedMatch).filter(LearnedMatch.norm_key == nk).first()
        if lm:
            lm.service_code, lm.service_name, lm.category = svc.code, svc.name, svc.category
            lm.occurrences = (lm.occurrences or 0) + 1
            lm.added_by = staff.get("user_id")
        else:
            db.add(LearnedMatch(norm_key=nk, service_code=svc.code, service_name=svc.name,
                                category=svc.category, raw_example=raw, occurrences=1,
                                added_by=staff.get("user_id")))
    db.commit()
    for sid in affected:
        _refresh_service_counts(db, sid)
    db.add(ParseLog(source_file=(body.source or "импорт"), clinic=c.name,
                    rows_total=len(body.rows), rows_matched=created,
                    rows_unmatched=len(body.rows) - created,
                    note=f"ручной импорт ({staff.get('role')})"))
    db.commit()
    return {"status": "imported", "clinic": c.name, "offers_created": created,
            "services_created": svc_created}


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
    """Динамика цены услуги по клиникам и датам (лента изменений из price_history).
    На услугу может приходиться много клиник — отдаём топ-8 по числу точек истории
    (клиники с трендом ≥2 точек приоритетнее), чтобы график оставался читаемым."""
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
    all_series = list(by_clinic.values())
    total_clinics = len(all_series)
    # приоритет: больше точек = виднее тренд; затем по названию
    all_series.sort(key=lambda x: (-len(x["points"]), x["clinic"]))
    series = all_series[:8]
    series.sort(key=lambda x: x["clinic"])
    years = sorted({p["year"] for s_ in series for p in s_["points"]})
    return {"code": s.code, "name": s.name, "years": years, "series": series,
            "total_clinics": total_clinics, "shown_clinics": len(series)}


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
