#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Уникальные H1 для одноимённых товаров PRIVAT.

Находит товары с одинаковыми названиями и проставляет им метаполе
custom.h1_suffix («модель 2», «модель 3»…). Тема сама подхватывает его
в H1, title и description — страницы перестают быть дублями.

Шаг 1:  python3 h1_suffix.py           -> найдёт дубли, создаст dubli.csv
Шаг 2:  открыть dubli.csv, по желанию заменить «модель N» на реальное
        отличие («чёрные», «с кружевом», «размер S»)
Шаг 3:  python3 h1_suffix.py apply     -> запишет метаполя в магазин
"""

import csv, json, os, re, sys, time, urllib.request

STORE = os.environ.get("SHOPIFY_STORE", "")
CSV_FILE = "dubli.csv"
_token_cache = ""


def get_token():
    """shpat_-токен напрямую, либо обмен client_id+secret приложения из Dev Dashboard."""
    global _token_cache
    if _token_cache:
        return _token_cache
    tok = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
    if tok.startswith("shpat_") or tok.startswith("atkn_"):
        _token_cache = tok
        return tok
    cid = os.environ.get("SHOPIFY_CLIENT_ID", "")
    sec = os.environ.get("SHOPIFY_CLIENT_SECRET", "") or (tok if tok.startswith("shpss_") else "")
    if not (cid and sec):
        sys.exit(
            "Нужны переменные окружения:\n"
            "  export SHOPIFY_STORE=\"0fd8ca-b7.myshopify.com\"\n"
            "и либо токен custom app:  export SHOPIFY_ADMIN_TOKEN=shpat_...\n"
            "либо реквизиты приложения из Dev Dashboard:\n"
            "  export SHOPIFY_CLIENT_ID=...\n"
            "  export SHOPIFY_CLIENT_SECRET=shpss_..."
        )
    req = urllib.request.Request(
        f"https://{STORE}/admin/oauth/access_token",
        data=json.dumps({"client_id": cid, "client_secret": sec,
                         "grant_type": "client_credentials"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            _token_cache = json.loads(r.read())["access_token"]
            return _token_cache
    except urllib.error.HTTPError as e:
        sys.exit(
            f"Не удалось получить токен (HTTP {e.code}): {e.read().decode()[:300]}\n"
            "Проверь в Dev Dashboard: приложение установлено на магазин и в его настройках "
            "заданы Admin API scopes read_products и write_products."
        )


def gql(query, variables=None):
    if not STORE:
        sys.exit("Задайте: export SHOPIFY_STORE=\"0fd8ca-b7.myshopify.com\"")
    TOKEN = get_token()
    req = urllib.request.Request(
        f"https://{STORE}/admin/api/2026-01/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": TOKEN},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
            if "errors" in data:
                if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in data["errors"]):
                    time.sleep(2 ** attempt)
                    continue
                sys.exit(f"Ошибка API: {json.dumps(data['errors'], ensure_ascii=False)[:300]}")
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                # троттлинг и случайные 502/503 от Shopify — ретраим с паузой
                time.sleep(3 * (attempt + 1))
                continue
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(3 * (attempt + 1))
            continue
    sys.exit("API перегружен (не ответил после 5 попыток), попробуйте позже")


def find_duplicates():
    query = """
    query($cursor: String) {
      products(first: 250, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id title handle metafield(namespace: "custom", key: "h1_suffix") { value } }
      }
    }"""
    products, cursor = [], None
    while True:
        page = gql(query, {"cursor": cursor})["products"]
        products += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    groups = {}
    for p in products:
        groups.setdefault(p["title"].strip().lower(), []).append(p)

    rows = []
    for grp in groups.values():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda p: (len(p["handle"]), p["handle"]))
        for i, p in enumerate(grp, start=1):
            current = (p.get("metafield") or {}).get("value") or ""
            m = re.search(r"-(\d+)$", p["handle"])
            proposed = current or (f"модель {m.group(1)}" if m else "модель 1")
            rows.append({
                "название": p["title"],
                "ссылка": f"https://{STORE}/products/{p['handle']}",
                "h1_suffix": proposed,
                "id": p["id"],
            })

    if not rows:
        print("Дублей не найдено — всё чисто!")
        return
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["название", "ссылка", "h1_suffix", "id"])
        w.writeheader()
        w.writerows(rows)
    print(f"Найдено {len(rows)} товаров-дублей -> {CSV_FILE}")
    print("Открой файл, замени «модель N» на реальные отличия (цвет, фасон) где знаешь их,")
    print("потом запусти:  python3 h1_suffix.py apply")


def apply():
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["h1_suffix"].strip()]
    mutation = """
    mutation($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) { userErrors { field message } }
    }"""
    done = 0
    for i in range(0, len(rows), 25):  # metafieldsSet принимает до 25 за раз
        batch = [{
            "ownerId": r["id"], "namespace": "custom", "key": "h1_suffix",
            "type": "single_line_text_field", "value": r["h1_suffix"].strip(),
        } for r in rows[i:i + 25]]
        errs = gql(mutation, {"metafields": batch})["metafieldsSet"]["userErrors"]
        if errs:
            print("ОШИБКА:", errs)
        else:
            done += len(batch)
            print(f"...записано {done} из {len(rows)}")
        time.sleep(0.5)
    print(f"Готово: {done} товаров получили уникальный H1.")


if __name__ == "__main__":
    if "apply" in sys.argv:
        apply()
    else:
        find_duplicates()
