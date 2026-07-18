#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Массовое обновление SEO-полей магазина PRIVAT через Shopify Admin API (GraphQL).

Правила:
  - meta title:       50–60 символов
  - meta description: 130–160 символов
  - H1 одноимённых товаров различается человекочитаемым уточнением
    (метаполе custom.h1_suffix), а не кодом товара.

Использование:
  export SHOPIFY_STORE="0fd8ca-b7.myshopify.com"
  export SHOPIFY_ADMIN_TOKEN="shpat_..."

  python3 seo_update.py export              # выгрузить текущее состояние -> seo_current.csv
  python3 seo_update.py generate            # предложить новые title/description -> seo_proposed.csv
  python3 seo_update.py apply --dry-run     # показать, что будет отправлено
  python3 seo_update.py apply               # применить seo_proposed.csv к магазину

Между generate и apply файл seo_proposed.csv можно (и стоит) отредактировать руками:
колонки new_title / new_description / h1_suffix — источник истины для apply.
Строки с пустым new_title и new_description пропускаются.
"""

import csv
import json
import os
import re
import sys
import time
import urllib.request

API_VERSION = "2026-01"
STORE = os.environ.get("SHOPIFY_STORE", "")
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")

TITLE_MIN, TITLE_MAX = 50, 60
DESC_MIN, DESC_MAX = 130, 160

# Лесенки суффиксов: берём самый длинный, который влезает в TITLE_MAX.
PRODUCT_TITLE_SUFFIXES = [
    " — купить в Бишкеке | Секс шоп PRIVAT",
    " — купить в Бишкеке | PRIVAT",
    " | Секс шоп PRIVAT, Бишкек",
    " | Секс шоп PRIVAT",
    " | PRIVAT",
]
COLLECTION_TITLE_SUFFIXES = [
    " — купить в Бишкеке недорого ❤️ Секс шоп Privat",
    " — купить в Бишкеке ❤️ Секс шоп Privat",
    " — купить в Бишкеке ❤️ Privat",
    " ❤️ Секс шоп Privat | Бишкек",
    " ❤️ Privat Бишкек",
]
# Хвосты описания добавляются по очереди, пока не наберём DESC_MIN.
DESC_EXTRAS = [
    " Анонимная доставка за 1 час, дискретная упаковка.",
    " Оплата при получении.",
    " Секс шоп PRIVAT ☎ 0500-690-690.",
    " Бережный подбор без неловкости.",
]


def gql(query: str, variables: dict = None) -> dict:
    if not STORE or not TOKEN:
        sys.exit("Задайте переменные окружения SHOPIFY_STORE и SHOPIFY_ADMIN_TOKEN")
    req = urllib.request.Request(
        f"https://{STORE}/admin/api/{API_VERSION}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": TOKEN,
        },
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
            if "errors" in data and any(
                e.get("extensions", {}).get("code") == "THROTTLED" for e in data["errors"]
            ):
                time.sleep(2**attempt)
                continue
            if "errors" in data:
                sys.exit(f"GraphQL error: {json.dumps(data['errors'], ensure_ascii=False)}")
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2**attempt)
                continue
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:500]}")
    sys.exit("Слишком много попыток — API троттлит запросы")


# ---------- выгрузка ----------

PRODUCTS_QUERY = """
query($cursor: String) {
  products(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title handle
      seo { title description }
      priceRangeV2 { minVariantPrice { amount } }
      variants(first: 5) { nodes { sku selectedOptions { name value } } }
      metafield(namespace: "custom", key: "h1_suffix") { value }
    }
  }
}
"""

COLLECTIONS_QUERY = """
query($cursor: String) {
  collections(first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id title handle seo { title description } }
  }
}
"""


def fetch_all(query: str, root: str):
    cursor, out = None, []
    while True:
        data = gql(query, {"cursor": cursor})
        page = data[root]
        out.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def cmd_export(path="seo_current.csv"):
    rows = []
    for p in fetch_all(PRODUCTS_QUERY, "products"):
        v = (p.get("variants") or {}).get("nodes") or [{}]
        rows.append({
            "type": "product",
            "id": p["id"],
            "handle": p["handle"],
            "name": p["title"],
            "sku": v[0].get("sku") or "",
            "price": (p.get("priceRangeV2") or {}).get("minVariantPrice", {}).get("amount", ""),
            "cur_title": (p.get("seo") or {}).get("title") or "",
            "cur_description": (p.get("seo") or {}).get("description") or "",
            "h1_suffix": (p.get("metafield") or {}).get("value") or "",
        })
    for c in fetch_all(COLLECTIONS_QUERY, "collections"):
        rows.append({
            "type": "collection",
            "id": c["id"],
            "handle": c["handle"],
            "name": c["title"],
            "sku": "", "price": "",
            "cur_title": (c.get("seo") or {}).get("title") or "",
            "cur_description": (c.get("seo") or {}).get("description") or "",
            "h1_suffix": "",
        })
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Выгружено {len(rows)} записей -> {path}")


# ---------- генерация ----------

def pick_title(name: str, suffixes) -> str:
    """Самый длинный суффикс, укладывающий title в 60; иначе самый короткий."""
    best = name + suffixes[-1]
    for s in suffixes:
        t = name + s
        if len(t) <= TITLE_MAX:
            return t
    return best  # имя слишком длинное само по себе — пометим флагом


def build_description(base: str) -> str:
    d = base
    for extra in DESC_EXTRAS:
        if len(d) >= DESC_MIN:
            break
        if len(d + extra) <= DESC_MAX:
            d += extra
    return d


def fmt_price(amount: str) -> str:
    try:
        n = float(amount)
        return str(int(n)) if n == int(n) else str(n)
    except (TypeError, ValueError):
        return ""


def model_number(handle: str) -> str:
    m = re.search(r"-(\d+)$", handle)
    return m.group(1) if m else "1"


def cmd_generate(src="seo_current.csv", dst="seo_proposed.csv", only_missing=False):
    if not os.path.exists(src):
        cmd_export(src)
    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # группы одноимённых товаров -> h1_suffix
    groups = {}
    for r in rows:
        if r["type"] == "product":
            groups.setdefault(r["name"].strip().lower(), []).append(r)

    for name, grp in groups.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda r: (len(r["handle"]), r["handle"]))
        for i, r in enumerate(grp, start=1):
            if not r["h1_suffix"]:
                # заглушка «модель N» — замените на цвет/фасон в CSV, где знаете отличие
                r["h1_suffix"] = f"модель {model_number(r['handle']) if i > 1 else '1'}"

    seen_titles = {}
    out = []
    for r in rows:
        name = r["name"].strip()
        display_name = name
        if r["type"] == "product" and r["h1_suffix"]:
            display_name = f"{name} ({r['h1_suffix']})"

        if r["type"] == "product":
            title = pick_title(display_name, PRODUCT_TITLE_SUFFIXES)
            price = fmt_price(r["price"])
            base = f"Купить {name} в Бишкеке" + (f" — {price} сом." if price else ".")
            if r["h1_suffix"]:
                base = f"Купить {name} ({r['h1_suffix']}) в Бишкеке" + (f" — {price} сом." if price else ".")
            desc = build_description(base)
        else:
            title = pick_title(name, COLLECTION_TITLE_SUFFIXES)
            desc = build_description(f"{name} — большой выбор и честные цены в секс шопе PRIVAT, Бишкек.")

        flags = []
        if len(title) > TITLE_MAX:
            flags.append(f"title>{TITLE_MAX}")
        if len(title) < TITLE_MIN:
            flags.append(f"title<{TITLE_MIN}")
        if not (DESC_MIN <= len(desc) <= DESC_MAX):
            flags.append("desc_len")
        if title.lower() in seen_titles:
            flags.append(f"dup_title_with:{seen_titles[title.lower()]}")
        seen_titles.setdefault(title.lower(), r["handle"])

        out.append({
            "type": r["type"], "id": r["id"], "handle": r["handle"], "name": name,
            "h1_suffix": r["h1_suffix"],
            "cur_title": r["cur_title"], "new_title": title, "title_len": len(title),
            "cur_description": r["cur_description"], "new_description": desc,
            "desc_len": len(desc), "flags": ";".join(flags),
        })

    if only_missing:
        # режим для регулярного запуска: трогаем только записи без заполненных SEO-полей
        out = [r for r in out if not r["cur_title"] or not r["cur_description"]]
        if not out:
            print("Все SEO-поля заполнены — обновлять нечего.")
            return

    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    flagged = sum(1 for r in out if r["flags"])
    print(f"Сгенерировано {len(out)} записей -> {dst}; с флагами (посмотреть руками): {flagged}")
    print("Отредактируйте CSV при необходимости и запустите: python3 seo_update.py apply")


# ---------- применение ----------

PRODUCT_MUTATION = """
mutation($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id }
    userErrors { field message }
  }
}
"""

COLLECTION_MUTATION = """
mutation($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { id }
    userErrors { field message }
  }
}
"""

METAFIELD_MUTATION = """
mutation($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { id }
    userErrors { field message }
  }
}
"""


def cmd_apply(src="seo_proposed.csv", dry=False):
    with open(src, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    done = errors = 0
    for r in rows:
        title = (r.get("new_title") or "").strip()
        desc = (r.get("new_description") or "").strip()
        if not title and not desc:
            continue
        seo = {}
        if title:
            seo["title"] = title
        if desc:
            seo["description"] = desc
        if dry:
            print(f"[dry] {r['type']} {r['handle']}: {title[:70]}")
            done += 1
            continue

        if r["type"] == "product":
            data = gql(PRODUCT_MUTATION, {"input": {"id": r["id"], "seo": seo}})
            errs = data["productUpdate"]["userErrors"]
            suffix = (r.get("h1_suffix") or "").strip()
            if not errs and suffix:
                mf = gql(METAFIELD_MUTATION, {"metafields": [{
                    "ownerId": r["id"], "namespace": "custom", "key": "h1_suffix",
                    "type": "single_line_text_field", "value": suffix,
                }]})
                errs = mf["metafieldsSet"]["userErrors"]
        else:
            data = gql(COLLECTION_MUTATION, {"input": {"id": r["id"], "seo": seo}})
            errs = data["collectionUpdate"]["userErrors"]

        if errs:
            errors += 1
            print(f"ОШИБКА {r['handle']}: {errs}")
        else:
            done += 1
            if done % 50 == 0:
                print(f"...обновлено {done}")
        time.sleep(0.3)  # щадим лимиты API
    print(f"Готово: обновлено {done}, ошибок {errors}")


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "export":
        cmd_export()
    elif cmd == "generate":
        if "--only-missing" in args and os.path.exists("seo_current.csv"):
            os.remove("seo_current.csv")  # всегда свежая выгрузка в регулярном режиме
        cmd_generate(only_missing="--only-missing" in args)
    elif cmd == "apply":
        cmd_apply(dry="--dry-run" in args)
    else:
        print(__doc__)
