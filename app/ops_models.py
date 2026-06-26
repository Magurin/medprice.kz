"""
ops_models.py — операционные таблицы модуля сбора данных (ТЗ §3.1).

Вынесены в ОТДЕЛЬНЫЙ Base (OpsBase), потому что app/ingest.py делает
Base.metadata.drop_all()/create_all() и пересобирает витрину «с нуля».
Эти таблицы (прогоны/ошибки/raw-слой) должны переживать пересборку, поэтому
их metadata не пересекается с основной — ingest их не трогает.

Слои:
  parse_runs      — журнал прогонов парсера (что/когда/итог)
  parse_errors    — ошибки парсинга с указанием источника и стадии (ТЗ: журналирование)
  raw_price_items — СЫРОЙ слой: позиции «как пришли», отдельно от нормализованных
                    price_offers. content_hash UNIQUE = дедупликация при повторном запуске.
"""
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import declarative_base

OpsBase = declarative_base()


class ParseRun(OpsBase):
    __tablename__ = "parse_runs"
    id = Column(Integer, primary_key=True)
    source_kind = Column(String, index=True)   # web | file
    trigger = Column(String)                    # manual | cron | dispatch
    status = Column(String, default="running", index=True)  # queued | running | done | failed
    started_at = Column(DateTime, server_default=func.now(), index=True)
    finished_at = Column(DateTime)
    sources_total = Column(Integer, default=0)
    sources_ok = Column(Integer, default=0)
    sources_failed = Column(Integer, default=0)
    rows_raw = Column(Integer, default=0)       # всего распознано позиций
    rows_new = Column(Integer, default=0)       # вставлено новых (после дедупа)
    rows_dup = Column(Integer, default=0)       # отброшено как дубли
    note = Column(Text)


class ParseError(OpsBase):
    __tablename__ = "parse_errors"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("parse_runs.id"), index=True)
    source = Column(String, index=True)   # хост / URL / путь к файлу
    stage = Column(String)                # fetch | parse | store
    error = Column(Text)                  # причина
    created_at = Column(DateTime, server_default=func.now())


class RawPriceItem(OpsBase):
    __tablename__ = "raw_price_items"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("parse_runs.id"), index=True)
    source_kind = Column(String)          # web | file
    source = Column(String, index=True)   # хост / файл
    clinic_host = Column(String, index=True)
    raw_name = Column(Text)
    category = Column(String)
    price = Column(Integer)               # тенге; NULL если «уточняйте»
    price_text = Column(String)           # как было в источнике
    currency = Column(String, default="KZT")
    content_hash = Column(String, unique=True, index=True)  # дедуп-ключ
    captured_at = Column(DateTime, server_default=func.now())
