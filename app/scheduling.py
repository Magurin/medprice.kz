"""
scheduling.py — расписание ежедневного парсинга + «гейт» для GitHub Actions.

Зачем гейт: точное время cron нельзя задать из админки, не переписывая YAML
workflow. Поэтому workflow запускается ЧАСТО (каждые 30 мин), а реально парсит
только в окне выбранного в админке времени. Эта логика — здесь, чтобы и бэкенд
(GET/PUT /api/admin/parse/schedule), и раннер использовали один и тот же код.

Запуск гейта на раннере (см. .github/workflows/parser.yml):
    python -m app.scheduling
  -> печатает в $GITHUB_OUTPUT: run=true|false, kind=..., limit=...
"""
import datetime as dt
import os

from .database import SessionLocal, engine
from .ops_models import OpsBase, ParseSchedule

# Шаг cron в workflow (мин). Окно срабатывания = [время; время+STEP):
# при каждом запуске cron сверяемся, попадает ли «сейчас» в окно после
# запланированного времени. Ровно один запуск за сутки попадёт в окно.
STEP_MINUTES = 30


def get_or_create_schedule(db):
    """Singleton-строка расписания (id=1). Создаёт со значениями по умолчанию."""
    s = db.get(ParseSchedule, 1)
    if not s:
        s = ParseSchedule(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def should_run_now(s: ParseSchedule, now: dt.datetime | None = None) -> bool:
    """Пора ли парсить: расписание включено и «сейчас» в окне [hh:mm; +STEP)."""
    if not s or not s.enabled:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    scheduled = now.replace(hour=s.hour or 0, minute=s.minute or 0,
                            second=0, microsecond=0)
    delta = (now - scheduled).total_seconds()
    return 0 <= delta < STEP_MINUTES * 60


def main() -> None:
    """Гейт для раннера: решает, запускать ли парсинг по расписанию сейчас."""
    OpsBase.metadata.create_all(engine)
    db = SessionLocal()
    try:
        s = get_or_create_schedule(db)
        run = should_run_now(s)
        kind = s.kind or "web"
        limit = s.run_limit or 200
    finally:
        db.close()

    lines = [
        f"run={'true' if run else 'false'}",
        f"kind={kind}",
        f"limit={limit}",
    ]
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
