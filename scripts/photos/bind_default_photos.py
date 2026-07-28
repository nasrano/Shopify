#!/usr/bin/env python3
"""Привязать общее фото товара к варианту, которому оно принадлежит.

Почему это вообще нужно. В Odoo своё фото варианта лежит в image_variant_1920,
но у варианта-по-умолчанию его нет: его фотография хранится на шаблоне. Первый
проход это учитывал слишком осторожно и оставлял такой вариант вовсе без фото —
на витрине он не переключал галерею.

Правило безопасности: привязываем, только если вариант без своего фото в товаре
РОВНО ОДИН. Тогда картинка шаблона заведомо его. Если таких вариантов два и
больше, чьё это фото — из данных не следует, и мы не трогаем (у VITA UDIN 500 мл
такой случай: этикетка на общем фото говорит «Персик», а Клубнику надо снимать).

Если картинки шаблона в Shopify вообще нет — заливаем её из Odoo.

  python3 bind_default_photos.py            — план
  python3 bind_default_photos.py --apply    — записать
"""
import base64, io, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from shop_odoo import all_products, odoo, rest

APPLY = "--apply" in sys.argv
SAME = 0.55

# Разобрано вручную по этикетке на фото — там, где вариантов без своего фото
# несколько и правило «ровно один» не срабатывает.
MANUAL = {"lubrikant-vita-udin-na-vodnoy-osnove-500-ml": "1235B"}   # общее фото — Персик


def sig(raw, n=64):
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    return list(bg.resize((n, n), Image.LANCZOS).getdata())


def diff(a, b):
    return sum(abs(x[i] - y[i]) for x, y in zip(a, b) for i in range(3)) / (len(a) * 3)


def ext_of(raw):
    fmt = (Image.open(io.BytesIO(raw)).format or "PNG").lower()
    return {"jpeg": "jpg", "mpo": "jpg"}.get(fmt, fmt)


products = [p for p in all_products() if len(p.get("variants", [])) > 1]
okw = odoo()
skus = [v["sku"] for p in products for v in p["variants"] if v.get("sku")]
ids = okw("product.product", "search", [["default_code", "in", skus]])
rows = {r["default_code"]: r for r in okw("product.product", "read", ids,
        fields=["default_code", "image_variant_1920", "image_1920"])}

stats = {"bind": 0, "upload": 0, "skip": 0, "err": 0}
left = []
for p in sorted(products, key=lambda x: x["title"]):
    naked = [v for v in p["variants"]
             if not rows.get(v.get("sku") or "", {}).get("image_variant_1920")]
    if not naked:
        continue
    if len(naked) > 1:
        pick = MANUAL.get(p["handle"])
        chosen = next((v for v in naked if v["sku"] == pick), None)
        if not chosen:
            print(f"- {p['title'][:50]!r}: без своего фото {len(naked)} вариантов "
                  f"({', '.join(v['title'] for v in naked)}) — не трогаем")
            stats["skip"] += len(naked)
            left += [f"{p['title']} / {v['title']} (sku {v['sku']})" for v in naked]
            continue
        for v in naked:
            if v is not chosen:
                left.append(f"{p['title']} / {v['title']} (sku {v['sku']})")
                stats["skip"] += 1
        naked = [chosen]

    v = naked[0]
    shown = rows.get(v["sku"], {}).get("image_1920")
    if not shown:
        print(f"- {p['title'][:50]!r}: {v['title']} — в Odoo нет картинки вовсе")
        left.append(f"{p['title']} / {v['title']} (sku {v['sku']})")
        stats["skip"] += 1
        continue
    raw = base64.b64decode(shown)
    s = sig(raw)
    free = [im for im in p["images"] if not im.get("variant_ids")]
    hit = next((im["id"] for im in free
                if diff(sig(urllib.request.urlopen(im["src"]).read()), s) < SAME), None)
    try:
        if hit:
            print(f"- {p['title'][:50]!r}: {v['title']} (sku {v['sku']}) -> привязка к image {hit}")
            if APPLY:
                rest(f"variants/{v['id']}.json", "PUT",
                     {"variant": {"id": v["id"], "image_id": hit}})
                time.sleep(0.3)
            stats["bind"] += 1
        else:
            name = f"{p['handle']}-{v['sku']}.{ext_of(raw)}"
            print(f"- {p['title'][:50]!r}: {v['title']} (sku {v['sku']}) -> заливка {name} "
                  f"({len(raw)//1024} КБ), в Shopify её не было")
            if APPLY:
                rest(f"products/{p['id']}/images.json", "POST",
                     {"image": {"attachment": base64.b64encode(raw).decode(), "filename": name,
                                "alt": f"{p['title']} — {v['title']}", "variant_ids": [v["id"]]}})
                time.sleep(0.6)
            stats["upload"] += 1
    except Exception as e:
        print(f"  ОШИБКА {v['sku']}: {str(e)[:200]}")
        stats["err"] += 1

print(f"\n{'ЗАПИСАНО' if APPLY else 'ПЛАН'}: {stats}")
if left:
    print("\nОстаются без фото (нужен человек):")
    for s in left:
        print("  ·", s)
