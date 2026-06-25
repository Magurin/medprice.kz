"""
report.py — отчёт покрытия по собранной базе.
Запуск:  python -m app.report
"""
from sqlalchemy import func

from .database import SessionLocal
from .models import City, Clinic, PriceOffer, Service


def main():
    db = SessionLocal()
    try:
        n_cities = db.query(func.count(City.id)).scalar()
        n_clinics = db.query(func.count(Clinic.id)).scalar()
        n_services = db.query(func.count(Service.id)).scalar()
        n_compar = db.query(func.count(Service.id)).filter(Service.n_clinics >= 2).scalar()
        n_offers = db.query(func.count(PriceOffer.id)).scalar()
        n_priced = db.query(func.count(PriceOffer.id)).filter(PriceOffer.price.isnot(None)).scalar()

        print("=" * 64)
        print("ОТЧЁТ ПОКРЫТИЯ — MedPrice KZ")
        print("=" * 64)
        print(f"Города:                 {n_cities}")
        print(f"Клиники:                {n_clinics}")
        print(f"Канонические услуги:    {n_services}")
        print(f"  из них сравнимых(>=2):{n_compar}")
        print(f"Ценовые предложения:    {n_offers}  (с ценой: {n_priced})")

        print("\n--- ТОП-12 сравнимых услуг (по числу клиник) ---")
        rows = (
            db.query(Service.name, Service.n_clinics, Service.n_offers)
            .filter(Service.n_clinics >= 2)
            .order_by(Service.n_clinics.desc())
            .limit(12)
            .all()
        )
        for name, nc, no in rows:
            print(f"  {nc:4d} клиник | {name[:50]}")

        print("\n--- Кураторские услуги с максимальным разбросом цен ---")
        cur = (
            db.query(Service)
            .filter(Service.is_curated, Service.n_clinics >= 5)
            .order_by(Service.n_clinics.desc())
            .limit(40)
            .all()
        )
        spreads = []
        for s in cur:
            prices = [p for (p,) in db.query(PriceOffer.price)
                      .filter(PriceOffer.service_id == s.id, PriceOffer.price.isnot(None)).all()]
            if len(prices) >= 5:
                mn, mx = min(prices), max(prices)
                spreads.append((round((mx - mn) / mx * 100, 1), s.name, mn, mx, len(prices)))
        spreads.sort(reverse=True)
        for pct, name, mn, mx, n in spreads[:12]:
            print(f"  разброс {pct:5.1f}% | {mn:>6}–{mx:<6} тг | {n:3d} клиник | {name[:38]}")

        print("\n--- Клиники по городам ---")
        rows = (
            db.query(City.name, func.count(Clinic.id))
            .outerjoin(Clinic, Clinic.city_id == City.id)
            .group_by(City.id).order_by(func.count(Clinic.id).desc()).limit(12).all()
        )
        for name, c in rows:
            print(f"  {c:5d} | {name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
