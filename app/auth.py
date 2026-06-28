"""
auth.py — серверная проверка доступа сотрудников для админ-ручек.

Зачем: FastAPI ходит в Postgres под привилегированной ролью и обходит RLS,
поэтому фронтовый гейт (скрыть кнопку) ничего не защищает. Реальную границу
держит этот модуль: каждая админ-ручка зависит от verify_staff.

Как работает:
  1. Из заголовка Authorization берём Supabase access token (Bearer).
  2. Валидируем его через Supabase Auth (GET /auth/v1/user) — это проверяет
     подпись/срок без знания JWT-секрета и работает с любым алгоритмом подписи.
  3. По user_id ищем строку в public.staff: явная роль (напр. 'admin') берётся
     оттуда. Строки нет -> по умолчанию 'moderator' (каждый зарегистрированный
     аккаунт — модератор, см. миграцию 005_auto_enroll_moderator). Раньше здесь
     был 403, но триггер пишет в staff *Supabase*, а бэкенд читает staff
     *локальной БД VM*, где строки нет, — поэтому новый пользователь не проходил.
     Опираемся на сам факт валидного токена, а не на наличие строки.

Env (бэкенд):
  SUPABASE_URL       — https://<ref>.supabase.co
  SUPABASE_ANON_KEY  — публичный anon-ключ (нужен как apikey для /auth/v1/user)
"""
import json
import os
import urllib.request

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _verify_token(token: str) -> str:
    """Supabase access token -> user_id. Бросает 401, если токен невалиден."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(500, "Авторизация сотрудников не настроена на сервере "
                                 "(нет SUPABASE_URL/SUPABASE_ANON_KEY).")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        raise HTTPException(401, "Невалидный или истёкший токен.")
    uid = data.get("id")
    if not uid:
        raise HTTPException(401, "Не удалось определить пользователя по токену.")
    return uid


def verify_staff(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency: пускает только сотрудников из public.staff. Возвращает {user_id, role}."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Требуется авторизация сотрудника.")
    token = authorization.split(" ", 1)[1].strip()
    uid = _verify_token(token)
    row = db.execute(
        text("SELECT role FROM public.staff WHERE user_id = :uid"), {"uid": uid}
    ).first()
    # Любой валидный аккаунт = модератор по умолчанию; явная строка staff
    # (например role='admin') имеет приоритет. Не зависим от того, доехала ли
    # строка из триггера Supabase до локальной staff на VM.
    role = row[0] if row else "moderator"
    return {"user_id": uid, "role": role}
