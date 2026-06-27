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

# Postgres через пулер Supabase на serverless (Vercel):
#  - NullPool: не держим коннекты между вызовами функции
#  - prepare_threshold=None: транзакционный пулер (6543) несовместим с prepared statements
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"prepare_threshold": None},
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
