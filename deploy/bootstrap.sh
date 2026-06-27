#!/usr/bin/env bash
# bootstrap.sh — развёртывание бэкенда MedPrice KZ на чистой Ubuntu (OCI VM).
# Идемпотентен: можно запускать повторно.
#
#   sudo bash deploy/bootstrap.sh api.ВАШ-ДОМЕН
#
# Перед запуском убедитесь, что:
#   1) DNS A-запись api.ВАШ-ДОМЕН -> публичный IP этой VM уже создана;
#   2) в OCI: Security List / NSG подсети открыты ingress TCP 80 и 443 (0.0.0.0/0);
#   3) код проекта лежит в /opt/medcompare (см. README — git clone / rsync);
#   4) /etc/medcompare/medcompare.env заполнен (см. medcompare.env.example).
set -euo pipefail

DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: sudo bash deploy/bootstrap.sh api.ВАШ-ДОМЕН" >&2
  exit 1
fi

APP_DIR=/opt/medcompare
APP_USER=ubuntu
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/7] Системные пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-pip git curl ufw \
  debian-keyring debian-archive-keyring apt-transport-https

echo "==> [2/7] Caddy (если ещё не установлен)"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

echo "==> [3/7] Код проекта в $APP_DIR"
if [[ "$REPO_DIR" != "$APP_DIR" ]]; then
  install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
  # копируем рабочее дерево (без .git/node_modules не нужно — данные/код берём как есть)
  rsync -a --delete --exclude '.venv' --exclude 'web/node_modules' \
    "$REPO_DIR"/ "$APP_DIR"/
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

echo "==> [4/7] Python venv + зависимости"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -U pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/deploy/requirements.txt"

echo "==> [5/7] Проверка окружения"
if [[ ! -f /etc/medcompare/medcompare.env ]]; then
  install -d /etc/medcompare
  cp "$APP_DIR/deploy/medcompare.env.example" /etc/medcompare/medcompare.env
  chmod 600 /etc/medcompare/medcompare.env
  echo "    !! /etc/medcompare/medcompare.env создан из примера — проверьте значения."
fi

echo "==> [6/7] systemd-сервис бэкенда"
cp "$APP_DIR/deploy/medcompare.service" /etc/systemd/system/medcompare.service
systemctl daemon-reload
systemctl enable medcompare
systemctl restart medcompare

echo "==> [7/7] Caddy (TLS) + firewall"
sed "s/__DOMAIN__/$DOMAIN/g" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
systemctl restart caddy
ufw allow 22/tcp  >/dev/null 2>&1 || true
ufw allow 80/tcp  >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true
yes | ufw enable  >/dev/null 2>&1 || true

echo
echo "Готово. Проверка:"
echo "  systemctl status medcompare --no-pager"
echo "  curl -s http://127.0.0.1:8077/            # локально"
echo "  curl -s https://$DOMAIN/                  # снаружи (после выдачи сертификата)"
echo
echo "Не забудьте на фронте (Vercel, проект web) выставить:"
echo "  NEXT_PUBLIC_API_BASE=https://$DOMAIN"
