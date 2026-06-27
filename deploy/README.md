# Деплой бэкенда MedPrice KZ на свой сервер (OCI VM, Ubuntu)

Перенос FastAPI-бэкенда с Vercel на постоянный сервер. Фронт остаётся на Vercel,
БД остаётся на Supabase — меняется только адрес API.

```
Браузер ──HTTPS──> Vercel (web, фронт)
                      │  fetch NEXT_PUBLIC_API_BASE
                      ▼
            https://api.ВАШ-ДОМЕН  ──>  Caddy (TLS) ──> 127.0.0.1:8077 (gunicorn+uvicorn)
                                                              │
                                                              ▼
                                              Supabase Postgres (pooler :6543)
```

## Почему так
- Фронт отдаётся по HTTPS → API тоже **обязан** быть по HTTPS, иначе браузер
  заблокирует запросы (mixed content). HTTPS даёт Caddy автоматически.
- Бэкенд слушает только `127.0.0.1` — наружу торчит лишь Caddy (порты 80/443).
- 1 OCPU / 1 ГБ хватает: 2 воркера gunicorn ≈ 250 МБ + Caddy ≈ 30 МБ.

---

## Шаги

### 0. На VM создан пользователь `ubuntu` (стандартно для Ubuntu-образа OCI)
SSH:  `ssh ubuntu@<PUBLIC_IP>`

### 1. Открыть порты 80/443 в OCI (это НЕ делается с сервера)
OCI Console → Networking → VCN → Subnet → **Security List** (или NSG инстанса) →
Add Ingress Rules: Source `0.0.0.0/0`, TCP, Destination ports **80** и **443**.
(Порт 22 уже открыт по умолчанию.)

### 2. DNS: A-запись на IP сервера
У регистратора домена: `api.ВАШ-ДОМЕН  A  <PUBLIC_IP>`.
Проверка:  `dig +short api.ВАШ-ДОМЕН` → должен вернуть ваш IP.

### 3. Залить код на сервер
Вариант А — git (если репозиторий доступен):
```bash
sudo install -d -o ubuntu -g ubuntu /opt/medcompare
git clone https://github.com/Magurin/medprice.kz.git /opt/medcompare
# приватный репозиторий → используйте PAT или deploy-key
```
Вариант Б — rsync с Windows (из папки проекта, через WSL/Git-Bash):
```bash
rsync -az --exclude '.venv' --exclude 'web/node_modules' --exclude '.git' \
  ./ ubuntu@<PUBLIC_IP>:/opt/medcompare/
```

### 4. Заполнить окружение
```bash
sudo install -d /etc/medcompare
sudo cp /opt/medcompare/deploy/medcompare.env.example /etc/medcompare/medcompare.env
sudo chmod 600 /etc/medcompare/medcompare.env
sudo nano /etc/medcompare/medcompare.env   # значения уже подставлены, проверьте
```

### 5. Запустить bootstrap
```bash
sudo bash /opt/medcompare/deploy/bootstrap.sh api.ВАШ-ДОМЕН
```
Скрипт ставит Python-venv, зависимости, Caddy, systemd-сервис, firewall и
поднимает всё. Caddy сам получит TLS-сертификат (несколько секунд).

### 6. Проверка
```bash
systemctl status medcompare --no-pager
curl -s http://127.0.0.1:8077/            # {"service":"MedPrice KZ",...}
curl -s https://api.ВАШ-ДОМЕН/            # то же, но снаружи и по HTTPS
journalctl -u medcompare -f               # логи
```

### 7. Переключить фронт на новый API
Vercel → проект **web** → Settings → Environment Variables →
`NEXT_PUBLIC_API_BASE = https://api.ВАШ-ДОМЕН` → **Redeploy**.

(Старый бэкенд-проект `medcompare` на Vercel можно после этого удалить/выключить.)

---

## Обновление кода потом
```bash
cd /opt/medcompare && git pull   # или rsync заново
sudo bash /opt/medcompare/deploy/update.sh
```

## Опционально: cron проверки цен по подпискам
Эндпоинт `POST /api/subscriptions/check` сверяет цены и шлёт письма. На Vercel
это был cron — на VM можно повторить systemd-таймером (раз в сутки):
```bash
# /etc/systemd/system/medcompare-subscheck.service  (Type=oneshot)
#   ExecStart=/usr/bin/curl -fsS -X POST http://127.0.0.1:8077/api/subscriptions/check
# + .timer с OnCalendar=daily; затем: systemctl enable --now medcompare-subscheck.timer
```

## Диагностика
| Симптом | Причина / решение |
|---|---|
| `curl https://...` висит/timeout | Порты 80/443 не открыты в OCI Security List (шаг 1) |
| Caddy не выдаёт сертификат | DNS ещё не указывает на IP (шаг 2), или 80/443 закрыты |
| 500 «авторизация не настроена» | пустые `SUPABASE_URL`/`SUPABASE_ANON_KEY` в env |
| фронт: запросы блокируются | `NEXT_PUBLIC_API_BASE` всё ещё http:// или старый адрес |
| сервис не стартует | `journalctl -u medcompare -e` — обычно неверный `DATABASE_URL` |
