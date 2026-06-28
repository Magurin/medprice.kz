-- Каждый новосозданный аккаунт автоматически становится модератором.
--
-- При регистрации Supabase Auth добавляет строку в auth.users. Этот триггер
-- следом заводит запись в public.staff с ролью 'moderator', поэтому новый
-- пользователь сразу видит раздел «Модерация» (фронтовый гейт isStaff) и
-- проходит verify_staff на бэкенде.
--
-- SECURITY DEFINER: функция пишет в public.staff в обход RLS (staff_self_read
-- отдаёт строку только владельцу, вставлять под обычной ролью нельзя).
-- ON CONFLICT DO NOTHING — идемпотентно, не падаем если строка уже есть.
-- Применять в Supabase -> SQL Editor (или через миграции).

CREATE OR REPLACE FUNCTION public.handle_new_user_staff()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.staff (user_id, role)
  VALUES (NEW.id, 'moderator')
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created_staff ON auth.users;
CREATE TRIGGER on_auth_user_created_staff
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user_staff();
