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
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CSV_FILE = "dubli.csv"


def gql(query, variables=None):
    if not STORE or not TOKEN:
        sys.exit("Сначала задайте переменные: export SHOPIFY_STORE=... и export SHOPIFY_ADMIN_TOKEN=shpat_...")
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
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")
    sys.exit("API перегружен, попробуйте позже")


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
