-- Подробные логи прогонов парсера + расписание ежедневного парсинга (ТЗ §3.1).
-- Эти таблицы также создаются автоматически через OpsBase.metadata.create_all,
-- но миграция нужна для явного контроля схемы в проде. Запусти в Supabase -> SQL Editor.

-- Подробный хронологический лог прогона (старт / результат по источнику / финал).
CREATE TABLE IF NOT EXISTS parse_run_logs (
    id      SERIAL PRIMARY KEY,
    run_id  INTEGER REFERENCES parse_runs(id),
    ts      TIMESTAMP DEFAULT now(),
    level   VARCHAR DEFAULT 'info',   -- info | warn | error
    source  VARCHAR,                  -- хост / файл (опц.)
    stage   VARCHAR,                  -- run | fetch | parse | store (опц.)
    message TEXT
);
CREATE INDEX IF NOT EXISTS ix_parse_run_logs_run_id ON parse_run_logs(run_id);
CREATE INDEX IF NOT EXISTS ix_parse_run_logs_ts      ON parse_run_logs(ts);

-- Расписание ежедневного парсинга (singleton, id=1), редактируется из админки.
-- Время хранится в UTC; workflow сверяется с ним через app.scheduling (gate).
CREATE TABLE IF NOT EXISTS parse_schedule (
    id         INTEGER PRIMARY KEY,
    enabled    BOOLEAN DEFAULT TRUE,
    hour       INTEGER DEFAULT 2,    -- UTC, 0..23
    minute     INTEGER DEFAULT 30,   -- UTC, 0..59
    kind       VARCHAR DEFAULT 'web',
    run_limit  INTEGER DEFAULT 200,
    updated_at TIMESTAMP DEFAULT now(),
    updated_by VARCHAR
);

-- Стартовое значение расписания: 02:30 UTC (как было в cron), парсинг включён.
INSERT INTO parse_schedule (id, enabled, hour, minute, kind, run_limit)
VALUES (1, TRUE, 2, 30, 'web', 200)
ON CONFLICT (id) DO NOTHING;
