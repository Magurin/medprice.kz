# -*- coding: utf-8 -*-
"""
notify.py — отправка email об изменении цены. Pluggable, без жёстких зависимостей.

Бэкенд выбирается по переменным окружения (приоритет сверху вниз):
  1. RESEND_API_KEY        -> Resend HTTP API (https://resend.com), отправитель MAIL_FROM
  2. SMTP_HOST (+ SMTP_USER/SMTP_PASS/SMTP_PORT) -> обычный SMTP
  3. ничего                -> «no-op»: только лог в консоль (для разработки)

Так фича работает сразу (пишет подписки в БД, проверка цен идёт), а реальная
рассылка включается добавлением ключа — менять код не нужно.
"""
import json
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

MAIL_FROM = os.environ.get("MAIL_FROM", "MedPrice KZ <onboarding@resend.dev>")
APP_URL = os.environ.get("APP_URL", "http://localhost:3000")


def backend_name() -> str:
    if os.environ.get("RESEND_API_KEY"):
        return "resend"
    if os.environ.get("SMTP_HOST"):
        return "smtp"
    return "noop"


def _tenge(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₸"


def _html(service: str, old: int, new: int) -> str:
    arrow = "снизилась" if new < old else "выросла"
    color = "#0d9488" if new < old else "#dc2626"
    diff = abs(new - old)
    pct = round(diff / old * 100) if old else 0
    return f"""\
<div style="font-family:system-ui,Arial,sans-serif;max-width:480px;margin:0 auto">
  <h2 style="margin:0 0 4px">Цена {arrow}</h2>
  <p style="color:#475569;margin:0 0 16px">{service}</p>
  <div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px">
    <div style="font-size:13px;color:#94a3b8">было</div>
    <div style="font-size:18px;text-decoration:line-through;color:#94a3b8">{_tenge(old)}</div>
    <div style="font-size:13px;color:#94a3b8;margin-top:8px">стало</div>
    <div style="font-size:28px;font-weight:700;color:{color}">{_tenge(new)}
      <span style="font-size:14px">({'−' if new < old else '+'}{pct}%)</span>
    </div>
  </div>
  <p style="margin-top:16px"><a href="{APP_URL}" style="color:#0d9488">Открыть MedPrice.kz →</a></p>
</div>"""


def _send_resend(to: str, subject: str, html: str) -> bool:
    key = os.environ["RESEND_API_KEY"]
    payload = json.dumps({"from": MAIL_FROM, "to": [to], "subject": subject,
                          "html": html}).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "MedPriceKZ/1.0"})  # без UA Cloudflare у Resend режет запрос (err 1010)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f"[notify] resend error: {e}")
        return False


def _send_smtp(to: str, subject: str, html: str) -> bool:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, MAIL_FROM, to
    msg.set_content("Цена изменилась. Откройте письмо в HTML-клиенте.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, port, timeout=15) as srv:
            srv.starttls(context=ssl.create_default_context())
            if user and pwd:
                srv.login(user, pwd)
            srv.send_message(msg)
        return True
    except Exception as e:
        print(f"[notify] smtp error: {e}")
        return False


def send_email(to: str, subject: str, html: str) -> bool:
    backend = backend_name()
    if backend == "resend":
        return _send_resend(to, subject, html)
    if backend == "smtp":
        return _send_smtp(to, subject, html)
    print(f"[notify:noop] -> {to} | {subject} (письмо не отправлено: нет SMTP/RESEND_API_KEY)")
    return False


def send_price_change(to: str, service: str, old: int, new: int) -> bool:
    verb = "снизилась" if new < old else "выросла"
    return send_email(to, f"MedPrice: цена {verb} — {service}", _html(service, old, new))
