"""
SQLAlchemy engine/сессия.

Источник БД — переменная окружения DATABASE_URL (только Postgres / Supabase):
  DATABASE_URL=postgresql+psycopg://<user>:<pwd>@<host>:6543/postgres

Порты пулера Supabase:
  • 6543 — transaction pooler: для приложения (FastAPI/serverless), короткие запросы.
  • 5432 — session pooler:    для пакетных скриптов (ingest/geocode/enrich).

SQLite больше не поддерживается — единый источник правды для дев и прода один и тот же.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не задана. Нужна строка подключения к Postgres (Supabase), напр.: "
        "postgresql+psycopg://<user>:<pwd>@<host>:6543/postgres"
    )
if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("SQLite больше не поддерживается — задай Postgres DATABASE_URL.")

# Принимаем и postgresql://, и postgresql+psycopg:// — приводим к psycopg3-драйверу.
# Так ОДИН и тот же секрет DATABASE_URL годится и для psycopg-скриптов (enrich_2gis),
# и для SQLAlchemy (app.parser/app.ingest на том же раннере GitHub Actions).
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

# Режим пула (DB_POOL):
#  • persistent (по умолчанию) — постоянный сервер (gunicorn на VM): держим тёплые
#    соединения и НЕ платим TCP+TLS+auth к Supabase на каждый запрос. Критично,
#    т.к. VM (me-abudhabi-1) и БД (eu-central-1) в разных регионах (~120мс RTT) —
#    переустановка коннекта добавляла ~1с к каждому запросу.
#  • null — для serverless/одноразовых скриптов (DB_POOL=null): не держим коннекты.
_POOL = os.environ.get("DB_POOL", "persistent").lower()

# connect_args:
#  - prepare_threshold=None: транзакционный пулер (6543) несовместим с prepared statements
#  - keepalives: пулер Supabase/NAT рвут простаивающие коннекты — не даём им стухнуть
_connect_args = {
    "prepare_threshold": None,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

if _POOL == "null":
    engine = create_engine(
        DATABASE_URL, poolclass=NullPool, connect_args=_connect_args, future=True,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,           # тёплые коннекты на воркер (×2 воркера gunicorn)
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=180,      # короче времени жизни idle-коннекта у пулера Supabase
        pool_pre_ping=True,    # молча отбрасываем стухший коннект вместо ошибки клиенту
        connect_args=_connect_args,
        future=True,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
