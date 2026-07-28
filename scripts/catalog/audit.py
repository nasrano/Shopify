#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сплошная проверка каталога: товары, не подходящие своей категории,
плюс структурные ошибки дерева коллекций."""
import json, re, sys
from collections import defaultdict
from rules import POS, EXCLUSIVE

cat = json.load(open("catalog.json"))
menu = json.load(open("tree.json"))

by_id = {p["id"]: p for p in cat}
in_col = defaultdict(list)
for p in cat:
    for h in p["cols"]:
        in_col[h].append(p)

parent = {}
names = {}


def walk(nodes, par=None):
    for n in nodes:
        names[n["handle"]] = n["name"]
        if par:
            parent[n["handle"]] = par
        walk(n["children"], n["handle"])


walk(menu)

SKIP = {"novinki", "khity-prodazh", "rasprodazha", "briendy", "ighry-18", "massazh",
        "pariki", "frontpage", "new", "deliveries", "expense-copy",
        "katieghoriia-korzina", "lovense", "satisfyer", "vpiervyie", "dlia-dvoikh"}

report = []


def add(kind, title, rows):
    if rows:
        report.append((kind, title, rows))


# 1. Товар в категории, но её ключевой признак не встречается ни в названии,
#    ни в описании.
for h, pat in POS.items():
    rx = re.compile(pat, re.I)
    bad = []
    for p in in_col.get(h, []):
        if not rx.search(p["title"] + " " + p["desc"]):
            bad.append(p)
    add("mismatch", f"«{names.get(h, h)}» [{h}] — признак «{pat[:38]}…» не найден", bad)

# 2. Взаимоисключающие категории.
for a, b, why in EXCLUSIVE:
    both = [p for p in cat if a in p["cols"] and b in p["cols"]]
    add("exclusive", f"{why}: одновременно в [{a}] и [{b}]", both)

# 3. Товар в подкатегории, но не в родительской коллекции.
for child, par in parent.items():
    if child in SKIP:
        continue
    bad = [p for p in in_col.get(child, []) if par not in p["cols"]]
    add("no-parent", f"в «{names.get(child, child)}» [{child}], но не в родителе [{par}]", bad)

# 4. Товар в родителе, но ни в одной подкатегории.
kids = defaultdict(list)
for c, p in parent.items():
    kids[p].append(c)
for par, ch in kids.items():
    bad = [p for p in in_col.get(par, []) if not (set(ch) & set(p["cols"]))]
    add("orphan", f"в «{names.get(par, par)}» [{par}], но ни в одной подкатегории", bad)

# 5. Товар вообще без категорий (на витрине недостижим).
add("no-collection", "не входит ни в одну коллекцию",
    [p for p in cat if not [c for c in p["cols"] if c not in ("frontpage", "new")]])

# 6. Одинаковые названия.
tt = defaultdict(list)
for p in cat:
    tt[p["title"].strip().lower()].append(p)
dupes = [p for v in tt.values() if len(v) > 1 for p in v]
add("dupe-title", "одинаковые названия товаров", dupes)

# ── вывод ────────────────────────────────────────────────────────────────
only = sys.argv[1] if len(sys.argv) > 1 else None
total = 0
for kind, title, rows in report:
    if only and only != kind:
        continue
    total += len(rows)
    print(f"\n### [{kind}] {title} — {len(rows)}")
    for p in sorted(rows, key=lambda x: x["sku"] or "~"):
        flag = "" if p["status"] == "ACTIVE" else f" ({p['status']})"
        print(f"   {(p['sku'] or '—'):8s} {p['title'][:76]}{flag}")
print(f"\n===== всего строк: {total}")
