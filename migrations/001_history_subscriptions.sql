-- MedPrice KZ — таблицы для истории цен и подписок.
-- Запусти в Supabase: Dashboard -> SQL Editor -> New query -> вставь -> Run.
-- (Роль loader не имеет прав CREATE в схеме public, поэтому через дашборд.)

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    clinic_id  INTEGER NOT NULL REFERENCES clinics(id),
    service_id INTEGER NOT NULL REFERENCES services(id),
    price       INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    source_file VARCHAR,
    raw_name    TEXT,
    is_demo     BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_price_history_clinic   ON price_history(clinic_id);
CREATE INDEX IF NOT EXISTS ix_price_history_service  ON price_history(service_id);
CREATE INDEX IF NOT EXISTS ix_price_history_recorded ON price_history(recorded_at);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    email       VARCHAR NOT NULL,
    service_id  INTEGER NOT NULL REFERENCES services(id),
    clinic_id   INTEGER REFERENCES clinics(id),
    city        VARCHAR,
    last_price       INTEGER,
    created_at       TIMESTAMP DEFAULT now(),
    last_checked_at  TIMESTAMP,
    last_notified_at TIMESTAMP,
    is_active   BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_subscriptions_email   ON subscriptions(email);
CREATE INDEX IF NOT EXISTS ix_subscriptions_service ON subscriptions(service_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_active  ON subscriptions(is_active);

-- Доступ роли приложения (loader работает через пулер; на всякий случай открываем стандартным ролям).
GRANT SELECT, INSERT, UPDATE, DELETE ON price_history, subscriptions TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE price_history_id_seq, subscriptions_id_seq TO anon, authenticated, service_role;
