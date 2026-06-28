"""
ops_models.py — операционные таблицы модуля сбора данных (ТЗ §3.1).

Вынесены в ОТДЕЛЬНЫЙ Base (OpsBase), потому что app/ingest.py делает
Base.metadata.drop_all()/create_all() и пересобирает витрину «с нуля».
Эти таблицы (прогоны/ошибки/raw-слой) должны переживать пересборку, поэтому
их metadata не пересекается с основной — ingest их не трогает.

Слои:
  parse_runs      — журнал прогонов парсера (что/когда/итог)
  parse_errors    — ошибки парсинга с указанием источника и стадии (ТЗ: журналирование)
  raw_price_items — СЫРОЙ слой позиций: «как пришли», отдельно от нормализованных
                    price_offers. content_hash UNIQUE = дедупликация при повторном запуске.
  raw_clinics     — СЫРОЙ слой клиник: метаданные (город/улица/телефон/часы) из JSON-LD,
                    один ряд на host. Нужен ingest для построения НОВЫХ клиник.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import declarative_base

OpsBase = declarative_base()


class ParseSource(OpsBase):
    """Источник парсинга, управляемый из админки (ТЗ §3.1).
    kind='frontier' — весь авто-список 103.kz (frontier.txt); kind='host' — отдельный сайт/хост."""
    __tablename__ = "parse_sources"
    id = Column(Integer, primary_key=True)
    kind = Column(String, default="host")          # frontier | host
    value = Column(String)                          # '103.kz' для frontier, иначе хост
    label = Column(String)
    enabled = Column(Boolean, default=True, index=True)
    note = Column(String)
    added_by = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    last_run_at = Column(DateTime)
    last_count = Column(Integer)                     # строк собрано в последний прогон


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


class ParseRunLog(OpsBase):
    """Подробный хронологический лог одного прогона (ТЗ §3.1: журналирование).
    В отличие от parse_errors (только ошибки) — пишет весь ход прогона:
    старт, результат по каждому источнику, финал. Это и есть «подробные логи»
    в админке. Имя таблицы parse_run_logs, чтобы не путать с legacy models.ParseLog."""
    __tablename__ = "parse_run_logs"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("parse_runs.id"), index=True)
    ts = Column(DateTime, server_default=func.now(), index=True)
    level = Column(String, default="info")   # info | warn | error
    source = Column(String)                   # хост / файл (опц.)
    stage = Column(String)                    # run | fetch | parse | store (опц.)
    message = Column(Text)


class ParseSchedule(OpsBase):
    """Расписание ежедневного парсинга, редактируемое из админки (ТЗ §3.1).
    Singleton (id=1). Время хранится в UTC; workflow на GitHub Actions запускается
    часто (каждые 30 мин) и сверяется с этой записью через app.scheduling (gate):
    парсит только в выбранный час:минуту. Так время можно менять из UI без правки
    cron в .github/workflows/parser.yml."""
    __tablename__ = "parse_schedule"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, default=True)
    hour = Column(Integer, default=2)         # UTC, 0..23
    minute = Column(Integer, default=30)      # UTC, 0..59
    kind = Column(String, default="web")      # web | file (что парсить по расписанию)
    run_limit = Column(Integer, default=200)  # лимит хостов за прогон (web)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String)


class LearnedMatch(OpsBase):
    """Ручная привязка модератора (ТЗ §3.2): нормализованное raw-название -> услуга.
    Живёт отдельно от витрины, чтобы переживать пересборку. service_code NULL = «не услуга»."""
    __tablename__ = "learned_matches"
    id = Column(Integer, primary_key=True)
    norm_key = Column(String, unique=True, nullable=False, index=True)
    service_code = Column(String, index=True)
    service_name = Column(String)
    category = Column(String)
    raw_example = Column(Text)
    occurrences = Column(Integer, default=0)
    added_by = Column(String)
    added_at = Column(DateTime, server_default=func.now())


class RawClinic(OpsBase):
    """Сырьё по клинике из веб-харвестера (метаданные LocalBusiness JSON-LD).
    Один ряд на host (UPSERT) — текущий снимок. app.ingest строит из него clinics
    для НОВЫХ хостов; существующие клиники (с 2ГИС-обогащением) переиспользуются по host.
    Раньше эти поля жили в harvester/raw/clinics.jsonl; после переезда сбора на VM
    парсер пишет их сюда, чтобы БД-слой был самодостаточен для ingest."""
    __tablename__ = "raw_clinics"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("parse_runs.id"), index=True)
    host = Column(String, unique=True, index=True)
    name = Column(String)              # бренд (различение филиалов по street делает ingest)
    brand = Column(String)
    street = Column(String)
    city = Column(String)
    address = Column(String)
    phone = Column(String)
    working_hours = Column(String)
    source_url = Column(String)
    branches = Column(Text)            # JSON-список филиалов [{city,address,phone}] (если сеть)
    captured_at = Column(DateTime, server_default=func.now())


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
    is_from = Column(Boolean, default=False)    # цена «от» (нижняя граница)
    on_request = Column(Boolean, default=False) # «уточняйте» (нет числовой цены)
    content_hash = Column(String, unique=True, index=True)  # дедуп-ключ
    captured_at = Column(DateTime, server_default=func.now())
