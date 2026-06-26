-- Поля рейтинга/отзывов 2ГИС у клиник. Запусти в Supabase -> SQL Editor.
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS rating            DOUBLE PRECISION;  -- оценка 0..5
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS reviews_count     INTEGER;           -- число отзывов
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS twogis_url        VARCHAR;           -- ссылка на отзывы
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS twogis_id         VARCHAR;           -- id организации 2ГИС
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS rating_updated_at TIMESTAMP;         -- дневной рефреш
