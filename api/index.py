"""Точка входа для Vercel Python (@vercel/python детектит ASGI-объект `app`)."""
import os
import sys

# корень проекта в путь, чтобы импортировался пакет app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

# Vercel использует переменную `app` как ASGI-приложение
