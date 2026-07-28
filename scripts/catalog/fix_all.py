#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Раскладка товаров по категориям: добавить туда, где им место по названию,
и убрать оттуда, где название категории прямо противоречит товару.

python3 fix_all.py         — только показать
python3 fix_all.py apply   — применить
"""
import json, re, sys
from collections import defaultdict
from shop import gql

cat = json.load(open("catalog.json"))
in_col = defaultdict(list)
by_sku = {}
for p in cat:
    by_sku[p["sku"]] = p
    for h in p["cols"]:
        in_col[h].append(p)

COL_ID = {}  # handle -> gid, заполняется ниже

# (родитель, куда класть, что должно быть в названии, чего быть не должно)
ADD = [
    ("masturbatory", "vaghiny", r"вагин", r"tenga|тенга|\begg\b"),
    ("masturbatory", "anusy-i-popy", r"попк|\bпопа\b|ягодиц|анус", r"tenga|тенга|\begg\b"),
    ("masturbatory", "rotik", r"рот\b|ротик", None),
    ("masturbatory", "avtomatichieskiie", r"автоматическ", None),
    ("dlya-anala", "anal-nyie-probki", r"пробк", None),
    ("dlya-anala", "anal-nyie-vibratory", r"вибрац|вибратор|вибро", r"без вибрац"),
    ("vibratory", "dlia-klitora", r"клитор", None),
    ("vibratory", "dvoinyie", r"кролик|rabbit|двойн", r"двойного действия"),
    ("vibratory", "tochka-g", r"точк[аиуе] ?g|g-?spot", None),
    ("vibratory", "mini-vibratory", r"\bмини\b", None),
    ("nasadki-na-chlien", "stimuliruiushchiie", r"стимулирующ|ребрист|шипам|усик", None),
    ("nasadki-na-chlien", "vibriruiushchiie", r"вибрац", r"без вибрац"),
    ("smazki", "fruktovyie-siedobnyie", r"вкус|клубнич|фруктов", None),
    ("ero-biel-io", "trusiki-stringhi", r"стринг|танга", None),
    ("ero-biel-io", "chulki-i-poiasa-k-nim", r"гартер", None),
    ("prieziki", "ul-tratonkiie", r"ультратонк", None),
    ("strapony", "dvoinyie-strapony", r"двусторонн", None),
    ("bdsm", "oshieiniki-i-povodki", r"ошейник|поводок", None),
]

# (sku, откуда убрать, почему)
REMOVE = [
    ("1082", "massazhiery-prostaty", "это анальные бусы, а не массажёр простаты"),
    ("0165B", "naruchniki", "это ошейник с поводком"),
    ("1171", "bdsm-kostiumy", "поводок — не костюм"),
    ("1172", "bdsm-kostiumy", "поводок — не костюм"),
    ("1099A", "obychnyie", "смазка с фруктовым вкусом → Фруктовые"),
]

plan_add = defaultdict(list)
for parent, target, pos, neg in ADD:
    rp, rn = re.compile(pos, re.I), re.compile(neg, re.I) if neg else None
    for p in in_col.get(parent, []):
        if target in p["cols"]:
            continue
        if not rp.search(p["title"]):
            continue
        if rn and rn.search(p["title"]):
            continue
        plan_add[target].append(p)

plan_rm = defaultdict(list)
for sku, h, why in REMOVE:
    p = by_sku.get(sku)
    if p and h in p["cols"]:
        plan_rm[h].append((p, why))

n = 0
print("=== ДОБАВИТЬ ===")
for h, items in sorted(plan_add.items(), key=lambda x: -len(x[1])):
    print(f"\n+ в «{h}» — {len(items)}")
    for p in items:
        n += 1
        st = "" if p["status"] == "ACTIVE" else f" ({p['status']})"
        print(f"    {(p['sku'] or '—'):7s} {p['title'][:70]}{st}")
print("\n=== УБРАТЬ ===")
for h, items in plan_rm.items():
    for p, why in items:
        n += 1
        print(f"  − {p['sku']:7s} {p['title'][:52]:52s} из «{h}» — {why}")
print(f"\nвсего изменений: {n}")

if "apply" not in sys.argv:
    print("\nDRY RUN — ничего не тронуто")
    sys.exit()

Q = """query($h:String!){collectionByHandle(handle:$h){id}}"""
M_ADD = """mutation($id:ID!,$ids:[ID!]!){collectionAddProducts(id:$id,productIds:$ids){
  userErrors{field message}}}"""
M_RM = """mutation($id:ID!,$ids:[ID!]!){collectionRemoveProducts(id:$id,productIds:$ids){
  job{id} userErrors{field message}}}"""


def cid(h):
    if h not in COL_ID:
        COL_ID[h] = gql(Q, {"h": h})["collectionByHandle"]["id"]
    return COL_ID[h]


gid = lambda p: f"gid://shopify/Product/{p['id']}"

for h, items in plan_add.items():
    r = gql(M_ADD, {"id": cid(h), "ids": [gid(p) for p in items]})
    err = r["collectionAddProducts"]["userErrors"]
    print(f"+ {h}: {len(items)}", "ОШИБКА " + str(err) if err else "ок")
for h, items in plan_rm.items():
    r = gql(M_RM, {"id": cid(h), "ids": [gid(p) for p, _ in items]})
    err = r["collectionRemoveProducts"]["userErrors"]
    print(f"− {h}: {len(items)}", "ОШИБКА " + str(err) if err else "ок")
print("готово")
