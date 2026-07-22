#!/bin/bash
# Запуск инструмента печати ценников PRIVAT.
#   ./run.sh
# Подхватывает реквизиты Shopify из .env.local (если есть) и стартует сервер.
cd "$(dirname "$0")" || exit 1

if [ -f .env.local ]; then
  # shellcheck disable=SC1091
  source .env.local
fi

if [ -z "$SHOPIFY_STORE" ]; then
  echo "Не задан SHOPIFY_STORE. Заполни .env.local (см. README.md)." >&2
  exit 1
fi

# Локально нет файла аккаунтов портала (users.json) — отключаем вход для дева.
# На портале авторизация активна (аккаунты те же, что у продавцов).
export PRICETAG_AUTH_OFF="${PRICETAG_AUTH_OFF:-1}"

exec python3 pricetag_server.py
