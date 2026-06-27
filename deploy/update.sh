#!/usr/bin/env bash
# update.sh — выкатить новую версию кода на VM (после git pull / rsync) и перезапустить.
#   sudo bash deploy/update.sh
set -euo pipefail
APP_DIR=/opt/medcompare
APP_USER=ubuntu

cd "$APP_DIR"
if [[ -d .git ]]; then
  sudo -u "$APP_USER" git pull --ff-only
fi
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/deploy/requirements.txt"
systemctl restart medcompare
systemctl status medcompare --no-pager
