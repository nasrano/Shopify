#!/usr/bin/env python3
"""Фото вариантов Odoo -> Shopify: заливаем недостающие и привязываем к вариантам.

Odoo — источник истины: своё фото варианта лежит в `image_variant_1920`. Брать
`image_1920` нельзя: у варианта без своего фото оно отдаёт картинку шаблона, и
синий вариант получил бы фиолетовое фото. В Shopify при миграции попало одно фото
на товар, и ни одно не привязано к варианту — поэтому цвета не переключаются.

Сравнение картинок — по цвету (RGB 64x64, средняя разница каналов): побайтово
не сходится (Shopify пережимает), а серый dHash не отличает синюю пробку от
красной. Замеры на нашем каталоге: одна и та же картинка после пережатия — до
0.30; разные вкусы лубриканта (одинаковая бутылка, отличается только фрукт на
этикетке) — от 0.97; разные цвета — от 6. Порог 0.55 стоит между первыми двумя.

ВАЖНО про размер подписи: на 16x16 этикетка вкуса просто не видна, и «Персик»
склеивался с «Манго». Мельчить нельзя.

Реквизиты берутся из scripts/labels/.env.local (Shopify) и ~/Downloads/sync/.env (Odoo).

  python3 variant_photos.py            — только план
  python3 variant_photos.py --apply    — заливка
"""
import base64, io, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from shop_odoo import all_products, odoo, rest

APPLY = "--apply" in sys.argv
SAME = 0.55           # порог «та же картинка» по средней разнице RGB
OUT = os.path.dirname(os.path.abspath(__file__))


def sig(raw, n=64):
    """Цветная подпись картинки: прозрачный фон считаем белым, как в Shopify."""
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGBA")
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
# берём именно image_variant_1920 — своё фото варианта. image_1920 у варианта без
# своего фото возвращает картинку шаблона, и синий вариант получил бы фиолетовое фото.
odoo_img = {r["default_code"]: r.get("image_variant_1920") or ""
            for r in okw("product.product", "read", ids,
                         fields=["default_code", "image_variant_1920"])}

no_photo, stats = [], {"bind": 0, "upload": 0, "reuse": 0, "missing": 0, "err": 0}
for p in sorted(products, key=lambda x: x["title"]):
    print(f"\n- {p['title'][:60]!r} ({p['handle']})")
    known = []                       # [(подпись, image_id)] — что уже есть в Shopify
    for im in p["images"]:
        try:
            known.append((sig(urllib.request.urlopen(im["src"]).read()), im["id"]))
        except Exception as e:
            print(f"    !! не скачал {im['src']}: {e}")
    for v in p["variants"]:
        b64 = odoo_img.get(v.get("sku") or "")
        if not b64:
            # в Odoo у варианта нет своего фото — оставляем общее фото товара,
            # чужой цвет подсовывать нельзя
            print(f"    без фото     {v['title']!r} sku={v.get('sku')} — покажем общее")
            no_photo.append(f"{p['title']} / {v['title']} (sku {v.get('sku')})")
            stats["missing"] += 1
            continue
        raw = base64.b64decode(b64)
        s = sig(raw)
        hit = next((iid for ks, iid in known if diff(ks, s) < SAME), None)
        try:
            if hit:
                if APPLY:
                    rest(f"variants/{v['id']}.json", "PUT",
                         {"variant": {"id": v["id"], "image_id": hit}})
                    time.sleep(0.3)
                print(f"    привязка     {v['title']!r} sku={v['sku']} -> image {hit}")
                stats["bind"] += 1
            else:
                name = f"{p['handle']}-{(v.get('sku') or v['id'])}.{ext_of(raw)}"
                if APPLY:
                    r, _ = rest(f"products/{p['id']}/images.json", "POST",
                                {"image": {"attachment": base64.b64encode(raw).decode(),
                                           "filename": name,
                                           "alt": f"{p['title']} — {v['title']}",
                                           "variant_ids": [v["id"]]}})
                    known.append((s, r["image"]["id"]))
                    time.sleep(0.6)
                else:
                    known.append((s, "NEW"))
                print(f"    заливка      {v['title']!r} sku={v['sku']} -> {name} ({len(raw)//1024} КБ)")
                stats["upload"] += 1
        except Exception as e:
            print(f"    ОШИБКА       {v['title']!r} sku={v.get('sku')}: {str(e)[:200]}")
            stats["err"] += 1

print(f"\n{'ЗАЛИТО' if APPLY else 'ПЛАН'}: {stats}")
if no_photo:
    print("\nВ Odoo нет своего фото у вариантов (стоит доснять):")
    for s in no_photo:
        print("  ·", s)
if APPLY:
    json.dump({"stats": stats, "no_photo": no_photo},
              open(f"{OUT}/variant_photos_result.json", "w"), ensure_ascii=False, indent=1)
