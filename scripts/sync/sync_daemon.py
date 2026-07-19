#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Постоянная синхронизация Odoo -> Shopify (Odoo — мастер).

Каждый прогон (launchd раз в 10 минут):
  1. Остатки:   изменившиеся квоты Odoo -> inventorySetQuantities (Магазин/Склад)
  2. Заказы:    новые из Odoo -> orderCreate (bypass, оплачен, историческая дата);
                отменённые в Odoo -> orderCancel в Shopify
  3. Товары:    изменения цены/себестоимости/названия -> обновление;
                новые SKU -> черновик карточки (фото, цена, себестоимость, описание)

Состояние: ~/Downloads/sync/state.json (watermark заказов, кэши остатков и цен).
Логи:      ~/Downloads/sync/sync.log
Запуск вручную: python3 sync_daemon.py run
"""
import json, os, re, sys, time, uuid
import urllib.request, urllib.error
import xmlrpc.client
from datetime import datetime, timezone

SYNC_DIR = os.environ.get("SYNC_DIR") or os.path.expanduser("~/Downloads/sync")
STATE_F = os.path.join(SYNC_DIR, "state.json")
LOCK_F = os.path.join(SYNC_DIR, "sync.lock")
DISABLED_F = os.path.join(SYNC_DIR, "DISABLED")   # существует -> прогоны пропускаются

# --- реквизиты: из окружения, иначе из ~/Downloads/sync/.env ---
def load_env():
    envf = os.path.join(SYNC_DIR, ".env")
    if os.path.exists(envf):
        for line in open(envf):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
load_env()
STORE = os.environ["SHOPIFY_STORE"]
CID = os.environ["SHOPIFY_CLIENT_ID"]
CSECRET = os.environ["SHOPIFY_CLIENT_SECRET"]
OURL = os.environ["ODOO_URL"]
ODB = os.environ["ODOO_DB"]
OUSER = os.environ["ODOO_USER"]
OKEY = os.environ["ODOO_API_KEY"]

LOCATION_MAP = {"Магазин": "Магазин", "Склад": "Склад"}   # leaf Odoo -> имя локации Shopify


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


# ---------------- Shopify client ----------------
_token = ""
def token():
    global _token
    if _token: return _token
    req = urllib.request.Request(
        f"https://{STORE}/admin/oauth/access_token",
        data=json.dumps({"client_id": CID, "client_secret": CSECRET,
                         "grant_type": "client_credentials"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        _token = json.loads(r.read())["access_token"]
    return _token


def gql(query, variables=None):
    req = urllib.request.Request(
        f"https://{STORE}/admin/api/2026-01/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token()})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
            if "errors" in data:
                if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in data["errors"]):
                    time.sleep(2 * (attempt + 1)); continue
                raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False)[:400])
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(3 * (attempt + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(3 * (attempt + 1)); continue
    raise RuntimeError("Shopify API не ответил после 6 попыток")


# ---------------- Odoo client ----------------
_ouid = None
_omodels = None
def odoo():
    global _ouid, _omodels
    if _ouid is None:
        common = xmlrpc.client.ServerProxy(f"{OURL}/xmlrpc/2/common")
        _ouid = common.authenticate(ODB, OUSER, OKEY, {})
        if not _ouid: raise RuntimeError("Odoo: авторизация не прошла")
        _omodels = xmlrpc.client.ServerProxy(f"{OURL}/xmlrpc/2/object")
    return _ouid, _omodels


def okw(model, method, dom, **kw):
    uid, models = odoo()
    return models.execute_kw(ODB, uid, OKEY, model, method, [dom], kw)


def oread(model, ids, fields, ctx=None):
    uid, models = odoo()
    kw = {"fields": fields}
    if ctx: kw["context"] = ctx
    return models.execute_kw(ODB, uid, OKEY, model, "read", [ids], kw)


# ---------------- state ----------------
def load_state():
    if os.path.exists(STATE_F):
        return json.load(open(STATE_F))
    return {"orders_watermark": "", "stock_cache": {}, "prices_cache": {}, "known_skus": []}


def save_state(st):
    json.dump(st, open(STATE_F, "w"), ensure_ascii=False)


# ---------------- справочники Shopify ----------------
def shopify_variants():
    """sku -> {variantId, productId, inventoryItemId, price, title}"""
    q = """
    query($cursor: String) {
      productVariants(first: 250, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id sku price product { id title status } inventoryItem { id unitCost { amount } } }
      }
    }"""
    out, cursor = {}, None
    while True:
        page = gql(q, {"cursor": cursor})["productVariants"]
        for v in page["nodes"]:
            sku = (v["sku"] or "").strip()
            if sku and sku not in out:
                out[sku] = {"variantId": v["id"], "productId": v["product"]["id"],
                            "itemId": v["inventoryItem"]["id"], "price": v["price"],
                            "cost": (v["inventoryItem"].get("unitCost") or {}).get("amount"),
                            "title": v["product"]["title"]}
        if not page["pageInfo"]["hasNextPage"]: return out
        cursor = page["pageInfo"]["endCursor"]


def shopify_locations():
    return {l["name"]: l["id"] for l in gql("{ locations(first: 10) { nodes { id name } } }")["locations"]["nodes"]}


# ---------------- 1. остатки ----------------
def sync_inventory(st, skumap):
    quants = okw("stock.quant", "search_read", [["location_id.usage", "=", "internal"]],
                 fields=["product_id", "location_id", "quantity"], limit=10000)
    pids = sorted({q["product_id"][0] for q in quants})
    sku_of = {}
    for i in range(0, len(pids), 500):
        for p in oread("product.product", pids[i:i + 500], ["default_code"]):
            sku_of[p["id"]] = (p.get("default_code") or "").strip()
    stock = {}
    for q in quants:
        sku = sku_of.get(q["product_id"][0])
        if not sku: continue
        leaf = q["location_id"][1].split("/")[-1]
        loc = LOCATION_MAP.get(leaf)
        if not loc: continue
        stock.setdefault(sku, {}).setdefault(loc, 0)
        stock[sku][loc] += q["quantity"]

    locs = shopify_locations()
    changes = []
    cache = st.get("stock_cache", {})
    all_skus = set(stock) | set(cache)
    for sku in all_skus:
        if sku not in skumap: continue
        for loc_name, loc_id in locs.items():
            want = int(stock.get(sku, {}).get(loc_name, 0))
            had = cache.get(sku, {}).get(loc_name)
            if had != want:
                changes.append({"inventoryItemId": skumap[sku]["itemId"],
                                "locationId": loc_id, "quantity": want})
    if changes:
        M = """
        mutation($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) { userErrors { field message } }
        }"""
        for i in range(0, len(changes), 200):
            r = gql(M, {"input": {"name": "available", "reason": "correction",
                                  "ignoreCompareQuantity": True,
                                  "quantities": changes[i:i + 200]}})["inventorySetQuantities"]
            if r["userErrors"]: log(f"ОСТАТКИ ошибка: {r['userErrors'][:2]}")
        log(f"остатки: обновлено {len(changes)} позиций")
    st["stock_cache"] = {sku: {k: int(v) for k, v in d.items()} for sku, d in stock.items()}


# ---------------- 2. заказы ----------------
def order_exists(name):
    r = gql('query($q: String!) { orders(first: 1, query: $q) { nodes { id name cancelledAt } } }',
            {"q": f"name:{name}"})["orders"]["nodes"]
    return r[0] if r else None


def money(x):
    return {"shopMoney": {"amount": f"{x:.2f}", "currencyCode": "KGS"}}


def sync_orders(st, skumap):
    wm = st.get("orders_watermark") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new_wm = wm
    orders = okw("sale.order", "search_read",
                 ["&", ["write_date", ">", wm], ["state", "in", ["sale", "done", "cancel"]]],
                 fields=["name", "date_order", "write_date", "amount_total", "partner_id", "state"],
                 order="write_date asc", limit=300)
    if not orders:
        return
    ids = [o["id"] for o in orders]
    lines = okw("sale.order.line", "search_read",
                [["order_id", "in", ids], ["display_type", "=", False]],
                fields=["order_id", "product_id", "name", "product_uom_qty", "price_unit", "discount"])
    by_order = {}
    for l in lines: by_order.setdefault(l["order_id"][0], []).append(l)
    pids = sorted({l["product_id"][0] for l in lines if l.get("product_id")})
    pinfo = {}
    for i in range(0, len(pids), 500):
        for p in oread("product.product", pids[i:i + 500], ["default_code", "name"], ctx={"lang": "ru_RU"}):
            pinfo[p["id"]] = ((p.get("default_code") or "").strip(), p.get("name") or "")

    MCREATE = """
    mutation($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
      orderCreate(order: $order, options: $options) {
        order { id name } userErrors { field message }
      }
    }"""
    MCANCEL = """
    mutation($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!) {
      orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock, notifyCustomer: false) {
        userErrors { field message }
      }
    }"""
    created = cancelled = 0
    for o in orders:
        existing = order_exists(o["name"])
        if o["state"] == "cancel":
            if existing and not existing.get("cancelledAt"):
                r = gql(MCANCEL, {"orderId": existing["id"], "reason": "OTHER",
                                  "refund": False, "restock": False})["orderCancel"]
                if r["userErrors"]: log(f"ОТМЕНА {o['name']} ошибка: {r['userErrors']}")
                else: cancelled += 1; log(f"отменён заказ {o['name']}")
            new_wm = max(new_wm, o["write_date"]); continue
        if existing:
            new_wm = max(new_wm, o["write_date"]); continue   # уже есть (изменения сумм не трогаем)
        when = o["date_order"].replace(" ", "T") + "Z"
        items, total, discount = [], 0.0, 0.0
        for l in by_order.get(o["id"], []):
            qty = int(float(l["product_uom_qty"] or 0))
            if qty <= 0: continue
            eff = round(float(l["price_unit"] or 0) * (1 - float(l.get("discount") or 0) / 100.0), 2)
            total += eff * qty
            if eff < 0:
                discount += -eff * qty; continue
            sku, pname = pinfo.get(l["product_id"][0], ("", "")) if l.get("product_id") else ("", "")
            item = {"quantity": qty, "priceSet": money(eff), "requiresShipping": False}
            hit = skumap.get(sku) or skumap.get(re.sub(r'[A-Za-zА-Яа-я]+$', '', sku))
            if hit: item["variantId"] = hit["variantId"]
            else:
                item["title"] = pname or l.get("name") or "Товар"
                if sku: item["sku"] = sku
            items.append(item)
        if not items:
            total = float(o["amount_total"])
            items = [{"title": "Заказ Privat.kg (без детализации)", "quantity": 1,
                      "priceSet": money(total), "requiresShipping": False}]
        order = {}
        if discount > 0:
            order["discountCode"] = {"itemFixedDiscountCode": {"code": "Скидка", "amountSet": money(discount)}}
        order.update({
            "name": o["name"], "processedAt": when, "currency": "KGS",
            "financialStatus": "PAID", "tags": ["odoo-import"],
            "note": f"Синк из Odoo. Исходный номер: {o['name']}", "sourceName": "odoo",
            "lineItems": items,
            "transactions": [{"kind": "SALE", "status": "SUCCESS", "amountSet": money(total),
                              "gateway": "manual", "processedAt": when}] if total > 0 else [],
        })
        r = gql(MCREATE, {"order": order, "options": {"inventoryBehaviour": "BYPASS",
                                                      "sendReceipt": False,
                                                      "sendFulfillmentReceipt": False}})["orderCreate"]
        if r["userErrors"]:
            log(f"ЗАКАЗ {o['name']} ошибка: {r['userErrors']}")
        else:
            created += 1
        new_wm = max(new_wm, o["write_date"])
    if created or cancelled:
        log(f"заказы: создано {created}, отменено {cancelled}")
    st["orders_watermark"] = new_wm


# ---------------- 3. товары ----------------
def staged_upload_png(filename, blob):
    su = gql("""
    mutation($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets { url resourceUrl parameters { name value } }
        userErrors { field message }
      }
    }""", {"input": [{"resource": "IMAGE", "filename": filename,
                      "mimeType": "image/png", "httpMethod": "POST"}]})["stagedUploadsCreate"]
    t = su["stagedTargets"][0]
    boundary = uuid.uuid4().hex
    parts = b""
    for p in t["parameters"]:
        parts += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{p['name']}\"\r\n\r\n{p['value']}\r\n").encode()
    parts += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
              f"Content-Type: image/png\r\n\r\n").encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(t["url"], data=parts,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        r.read()
    return t["resourceUrl"]


def sync_products(st, skumap):
    fields = ["default_code", "name", "list_price", "standard_price", "sale_ok", "type"]
    prods, offset = [], 0
    while True:
        rs = okw("product.product", "search_read", [["default_code", "!=", False]],
                 fields=fields, limit=500, offset=offset, context={"lang": "ru_RU"})
        if not rs: break
        prods += rs; offset += 500
    cache = st.get("prices_cache", {})
    MVAR = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        userErrors { field message }
      }
    }"""
    MTITLE = """
    mutation($input: ProductInput!) { productUpdate(input: $input) { userErrors { field message } } }"""
    n_price = n_cost = n_title = 0
    new_skus = []
    for p in prods:
        sku = p["default_code"].strip()
        price = round(float(p["list_price"] or 0), 2)
        cost = round(float(p["standard_price"] or 0), 2)
        name = (p["name"] or "").strip()
        cur = cache.get(sku)
        hit = skumap.get(sku)
        if not hit:
            if p.get("sale_ok") and p.get("type") != "service" and price > 1:
                new_skus.append(p)
            continue
        if cur and cur == [price, cost, name]:
            continue
        # цена/себестоимость
        if float(hit["price"]) != price or (hit["cost"] is None) or float(hit["cost"] or 0) != cost:
            var = {"id": hit["variantId"], "price": f"{price:.2f}",
                   "inventoryItem": {"cost": f"{cost:.2f}"}}
            r = gql(MVAR, {"productId": hit["productId"], "variants": [var]})["productVariantsBulkUpdate"]
            if r["userErrors"]: log(f"ЦЕНА {sku} ошибка: {r['userErrors']}")
            else: n_price += 1
        # название
        if name and name != hit["title"]:
            r = gql(MTITLE, {"input": {"id": hit["productId"], "title": name}})["productUpdate"]
            if r["userErrors"]: log(f"ИМЯ {sku} ошибка: {r['userErrors']}")
            else: n_title += 1
        cache[sku] = [price, cost, name]
    # новые товары -> черновик
    MPCREATE = """
    mutation($input: ProductInput!, $media: [CreateMediaInput!]) {
      productCreate(input: $input, media: $media) {
        product { id variants(first: 1) { nodes { id } } }
        userErrors { field message }
      }
    }"""
    for p in new_skus[:10]:   # не больше 10 за прогон
        sku = p["default_code"].strip()
        full = okw("product.product", "search_read", [["default_code", "=", sku]],
                   fields=["name", "barcode", "image_1920", "description_ecommerce",
                           "website_description", "description_sale"],
                   limit=1, context={"lang": "ru_RU"})[0]
        media = None
        if full.get("image_1920"):
            try:
                import base64
                blob = base64.b64decode(full["image_1920"])
                urlres = staged_upload_png(f"{sku}.png", blob)
                media = [{"originalSource": urlres, "mediaContentType": "IMAGE", "alt": full["name"]}]
            except Exception as e:
                log(f"НОВЫЙ {sku}: фото не загрузилось ({e})")
        desc = (full.get("description_ecommerce") or full.get("website_description")
                or full.get("description_sale") or "")
        inp = {"title": full["name"], "status": "DRAFT", "vendor": "Privat.kg",
               "descriptionHtml": desc if desc and desc != "False" else ""}
        r = gql(MPCREATE, {"input": inp, "media": media})["productCreate"]
        if r["userErrors"]:
            log(f"НОВЫЙ {sku} ошибка создания: {r['userErrors']}"); continue
        pid = r["product"]["id"]
        vid = r["product"]["variants"]["nodes"][0]["id"]
        price = round(float(p["list_price"] or 0), 2)
        cost = round(float(p["standard_price"] or 0), 2)
        gql(MVAR, {"productId": pid, "variants": [{
            "id": vid, "price": f"{price:.2f}", "barcode": full.get("barcode") or sku,
            "inventoryItem": {"cost": f"{cost:.2f}", "sku": sku, "tracked": True}}]})
        log(f"НОВЫЙ товар {sku} «{full['name'][:40]}» создан ЧЕРНОВИКОМ — проверь и опубликуй")
        cache[sku] = [price, cost, full["name"]]
    if n_price or n_title:
        log(f"товары: цен/костов обновлено {n_price}, названий {n_title}")
    st["prices_cache"] = cache


def run():
    if os.path.exists(DISABLED_F):
        log("прогон пропущен: файл DISABLED (удалите его для включения синка)"); return
    if os.path.exists(LOCK_F) and time.time() - os.path.getmtime(LOCK_F) < 3600:
        log("прогон пропущен: lock"); return
    open(LOCK_F, "w").write(str(os.getpid()))
    try:
        st = load_state()
        skumap = shopify_variants()
        sync_inventory(st, skumap)
        sync_orders(st, skumap)
        sync_products(st, skumap)
        save_state(st)
        log("прогон завершён")
    finally:
        os.remove(LOCK_F)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run()
    else:
        print(__doc__)
