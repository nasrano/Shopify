# Shopify-приложение «Ценники PRIVAT» — кнопка в админке

Тонкое приложение: добавляет в карточку товара (меню действий) кнопку
**«Печать ценника»**, которая открывает страницу печати `/print?...&auto=1` на
хосте `application_url`. Страница сама тянет данные из Admin API и открывает
диалог печати браузера.

```
shopify-app/
├── shopify.app.toml                     # конфиг приложения (client_id впишет CLI)
└── extensions/print-label-link/
    ├── shopify.extension.toml           # admin_link, target admin.product.action.link, url=/print
    └── locales/{en.default,ru}.json     # подпись кнопки
```

## Как это работает

1. Мерчант на карточке товара жмёт «⋯ / Ещё действия → Печать ценника».
2. Shopify открывает `<application_url>/print?auto=1&shop=…&id=<productId>`.
3. `pricetag_server.py` (на портале) по `id` тянет вариант(ы) товара из Admin API,
   рендерит HTML-ценник и вызывает `window.print()` — открывается диалог печати,
   мерчант выбирает Zebra и печатает.
4. Если у товара несколько вариантов — страница сперва покажет выбор варианта.

Кнопка **не** печатает сама (веб-страница не имеет доступа к принтеру) — она даёт
диалог печати браузера. Это и есть выбранный подход.

## Деплой

Предпосылка: страница печати уже поднята на публичном хосте (портал), например
`https://print.privat.kg` (см. `../README.md`). Этот хост = `application_url`.

```bash
npm i -g @shopify/cli@latest
cd scripts/labels/shopify-app

# 1) привязать/создать приложение в вашем Dev Dashboard (впишет client_id)
shopify app config link

# 2) в shopify.app.toml заменить application_url на реальный хост страницы печати
#    (и redirect_urls под него)

# 3) залить admin-link расширение
shopify app deploy

# 4) установить приложение на магазин 0fd8ca-b7.myshopify.com
#    (ссылка на установку появится в выводе / в Dev Dashboard)
```

После установки кнопка появится на страницах товаров. Проверить без деплоя целиком
можно `shopify app dev` (даст временный URL-туннель — но для реальной печати всё
равно нужен постоянный хост на портале).

## Заметки на будущее

- Нужна кнопка ещё и на странице **варианта** — добавить второй target
  `admin.product-variant-details.action.link` с `url = "/print?auto=1"`
  (Shopify подставит `id` варианта; для этого в `/print` поддержать вариант по `id`).
- `application_url` и `redirect_urls` в `shopify.app.toml` — заменить на реальный
  хост перед `deploy`.
- `uid` в расширении можно оставить как есть (уникальный идентификатор расширения).
