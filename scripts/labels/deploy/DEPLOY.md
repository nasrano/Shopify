# Деплой страницы печати ценников — РАЗВЁРНУТО

Живёт на портале (DigitalOcean droplet, Ubuntu 24.04, `104.248.134.132`) рядом с
Node-порталом (`portal.privat.kg` → :3000, юнит `privat-portal.service`).

- **URL:** https://print.privat.kg
- **Вход:** страница `/login` + cookie-сессия, аккаунты — те же, что у портала
  (`/opt/privat-portal/users.json`, scrypt). Basic-auth убран (никакого попапа Chrome).
- **Веб-сервер:** Caddy v2 (TLS автоматом; блок в `/etc/caddy/Caddyfile`)
- **Сервис:** `pricetags.service` → `/opt/privat-pricetags/venv/bin/python pricetag_server.py`, слушает `127.0.0.1:8765`
- **DNS:** `print.privat.kg` уже резолвится на IP портала (wildcard `*.privat.kg`)

## Что где на сервере

```
/opt/privat-pricetags/
├── pricetag_server.py          # код
├── config.json                 # дефолты
├── templates.json              # шаблоны магазина (НЕ перезаписывать при обновлении!)
├── .env                        # реквизиты Shopify (chmod 600, формат systemd)
└── venv/                       # python-barcode, pillow
/etc/systemd/system/pricetags.service
/etc/caddy/Caddyfile            # + блок print.privat.kg (basic_auth + reverse_proxy :8765)
```

## Обновить код (с ноутбука)

```bash
scp -i ~/.ssh/privat-portal scripts/labels/pricetag_server.py \
    root@104.248.134.132:/opt/privat-pricetags/
ssh -i ~/.ssh/privat-portal root@104.248.134.132 systemctl restart pricetags
```

`config.json` — тоже scp при изменении. `templates.json` НЕ трогать (рабочие шаблоны).

## Пользователи / пароли

Отдельных паролей у страницы печати нет — вход теми же аккаунтами, что в портале.
Управление пользователями и смена паролей — в самом портале (users.json). Сессия
живёт в подписанном cookie (ключ `/opt/privat-pricetags/session.key`); удалить
ключ = разлогинить всех.

## Полезное

```bash
systemctl status pricetags               # состояние
journalctl -u pricetags -n 50 --no-pager # логи
curl -s localhost:8765/api/config        # проверка сервиса локально
```

Бэкапы Caddyfile перед правкой: `/etc/caddy/Caddyfile.bak.<timestamp>`.

## Первичная установка с нуля (если поднимать заново)

```bash
apt update && apt install -y python3-venv fonts-dejavu-core
mkdir -p /opt/privat-pricetags
# scp pricetag_server.py config.json сюда
cd /opt/privat-pricetags && python3 -m venv venv
venv/bin/pip install python-barcode pillow
# создать .env (SHOPIFY_STORE / SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET / PRICETAG_PORT=8765), chmod 600
cp pricetags.service /etc/systemd/system/ && systemctl enable --now pricetags
# добавить блок из caddy-pricetags.conf в /etc/caddy/Caddyfile (хэш от caddy hash-password)
caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile && systemctl reload caddy
```
