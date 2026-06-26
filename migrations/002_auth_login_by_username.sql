-- Вход по логину ИЛИ почте.
-- Supabase Auth логинит по email. Чтобы пускать и по логину (username из метаданных
-- при регистрации), фронтенд вызывает RPC email_for_login(login) -> email, затем
-- обычный signInWithPassword(email, password).
--
-- SECURITY DEFINER: функция читает auth.users (недоступную anon напрямую), но отдаёт
-- только email по точному совпадению логина/почты — это нужно для самого логина.
-- Запусти в Supabase -> SQL Editor.

CREATE OR REPLACE FUNCTION public.email_for_login(login text)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path = auth, public
AS $$
  SELECT email
  FROM auth.users
  WHERE lower(raw_user_meta_data->>'username') = lower(login)
     OR lower(email) = lower(login)
  ORDER BY (lower(email) = lower(login)) DESC  -- точное совпадение по email приоритетнее
  LIMIT 1;
$$;

GRANT EXECUTE ON FUNCTION public.email_for_login(text) TO anon, authenticated;
