#!/usr/bin/env bash
# parser-run.sh — запуск модуля сбора (app.parser) на самой VM, заменяет прежний
# прогон на GitHub Actions. Расписание теперь — systemd timer на сервере (см.
# medcompare-parser.timer), а точное время по-прежнему задаётся из админки (БД):
# таймер будит этот скрипт каждые 30 мин, «гейт» (app.scheduling) сверяется с
# таблицей parse_schedule и реально парсит только в выбранное окно.
#
# Режимы:
#   parser-run.sh                  — по расписанию (через гейт). Так дёргает timer.
#   parser-run.sh now [kind] [lim] — немедленно, без гейта (ручной запуск/из админки).
#
# Окружение (DATABASE_URL -> локальный Postgres) берётся из EnvironmentFile юнита
# при запуске через systemd; при ручном запуске — подхватывается из /etc/medcompare.
set -euo pipefail

APP_DIR=/opt/medcompare
PY="$APP_DIR/.venv/bin/python3"
cd "$APP_DIR"

# Ручной запуск из шелла (не из systemd): подтянуть env самому.
if [ -z "${DATABASE_URL:-}" ] && [ -r /etc/medcompare/medcompare.env ]; then
  set -a; . /etc/medcompare/medcompare.env; set +a
fi

mode="${1:-schedule}"

if [ "$mode" = "now" ]; then
  kind="${2:-web}"
  limit="${3:-200}"
  echo "parser-run: ручной запуск kind=$kind limit=$limit"
  exec "$PY" -X utf8 -m app.parser --kind "$kind" --limit "$limit" --trigger dispatch
fi

# Режим по расписанию: спросить гейт, что и нужно ли запускать сейчас.
gate="$("$PY" -X utf8 -m app.scheduling)"
run=$(printf '%s\n'  "$gate" | sed -n 's/^run=//p'   | tail -1)
kind=$(printf '%s\n' "$gate" | sed -n 's/^kind=//p'  | tail -1)
limit=$(printf '%s\n' "$gate" | sed -n 's/^limit=//p' | tail -1)
echo "parser-run: гейт -> run=${run:-?} kind=${kind:-?} limit=${limit:-?}"

if [ "$run" = "true" ]; then
  exec "$PY" -X utf8 -m app.parser --kind "${kind:-web}" --limit "${limit:-200}" --trigger cron
fi
echo "parser-run: вне окна расписания — пропуск"
