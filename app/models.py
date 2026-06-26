"""ORM-модели агрегатора цен на медуслуги."""
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.orm import relationship

from .database import Base


class City(Base):
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)


class Clinic(Base):
    __tablename__ = "clinics"
    id = Column(Integer, primary_key=True)
    host = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    address = Column(String)
    source_url = Column(String)
    source_type = Column(String, default="web", index=True)  # web (скрапинг) | file (архив прайсов)
    phone = Column(String)
    working_hours = Column(String)
    lat = Column(Float)  # широта (geocode.py через Nominatim) -> маркер на карте 2ГИС
    lng = Column(Float)  # долгота
    rating = Column(Float)            # оценка 2ГИС (enrich_2gis.py), 0..5
    reviews_count = Column(Integer)   # число отзывов 2ГИС
    twogis_url = Column(String)       # ссылка на отзывы организации в 2ГИС
    twogis_id = Column(String)        # id организации в 2ГИС (кэш сопоставления)
    rating_updated_at = Column(DateTime)  # когда рейтинг обновлён (дневной рефреш)

    city = relationship("City")


class Service(Base):
    """Каноническая услуга (после нормализации/матчинга raw-названий)."""
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, index=True)
    is_curated = Column(Boolean, default=False, index=True)  # из кураторского справочника
    is_reference = Column(Boolean, default=False, index=True)  # из приложенного «Справочник услуг»
    tarificator_code = Column(String, index=True)           # код тарификатора/МКБ из справочника
    specialty = Column(String)                              # специальность из справочника
    match_method = Column(String)                            # как услуга впервые сопоставлена
    n_offers = Column(Integer, default=0, index=True)        # сколько ценовых предложений
    n_clinics = Column(Integer, default=0, index=True)       # в скольких клиниках


class PriceOffer(Base):
    """Цена конкретной услуги в конкретной клинике (как в её прайсе)."""
    __tablename__ = "price_offers"
    id = Column(Integer, primary_key=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    raw_name = Column(Text, nullable=False)     # оригинальное название из прайса клиники
    price = Column(Integer, index=True)         # тенге; NULL если «уточняйте»
    currency = Column(String, default="KZT")
    is_from = Column(Boolean, default=False)    # цена указана как «от N»
    on_request = Column(Boolean, default=False) # цена по запросу
    match_method = Column(String)               # curated / curated_fuzzy / auto / tarif / name_*
    match_score = Column(Float)
    source_type = Column(String, default="web", index=True)  # web | file
    tarificator_code = Column(String)           # код из прайса клиники (если был)
    parsed_at = Column(DateTime)                # когда распарсено (актуальность, ТЗ §4)
    is_active = Column(Boolean, default=True)

    clinic = relationship("Clinic")
    service = relationship("Service")


class UnmatchedItem(Base):
    """Строки прайсов, не привязанные к справочнику — очередь ручной разметки (ТЗ §3.2)."""
    __tablename__ = "unmatched_queue"
    id = Column(Integer, primary_key=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), index=True)
    raw_name = Column(Text, nullable=False)
    code = Column(String)
    price = Column(Integer)
    source_file = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class PriceHistory(Base):
    """Историческая точка цены: услуга в клинике на определённую дату (из архивных прайсов по годам)."""
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    price = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, nullable=False, index=True)  # дата прайса (год из имени файла)
    source_file = Column(String)
    raw_name = Column(Text)
    is_demo = Column(Boolean, default=False)  # синтетическая точка (если когда-нибудь засидим)

    clinic = relationship("Clinic")
    service = relationship("Service")


class Subscription(Base):
    """Подписка на изменение цены: услуга (+опц. клиника) на email."""
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    clinic_id = Column(Integer, ForeignKey("clinics.id"), index=True)  # NULL = любая клиника (минимум по услуге)
    city = Column(String)                       # фильтр города для агрегатной подписки
    last_price = Column(Integer)                # цена на момент подписки/последней проверки
    created_at = Column(DateTime, server_default=func.now())
    last_checked_at = Column(DateTime)
    last_notified_at = Column(DateTime)
    is_active = Column(Boolean, default=True, index=True)

    service = relationship("Service")
    clinic = relationship("Clinic")


class ParseLog(Base):
    """Журнал парсинга источников (ТЗ §3.1: журналирование)."""
    __tablename__ = "parse_log"
    id = Column(Integer, primary_key=True)
    source_file = Column(String, index=True)
    clinic = Column(String)
    rows_total = Column(Integer)
    rows_matched = Column(Integer)
    rows_unmatched = Column(Integer)
    note = Column(Text)
    parsed_at = Column(DateTime, server_default=func.now())


Index("ix_offer_service_price", PriceOffer.service_id, PriceOffer.price)
