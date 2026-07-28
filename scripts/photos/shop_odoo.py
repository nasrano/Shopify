"""Общие клиенты Shopify (REST Admin API) и Odoo (xmlrpc) для скриптов с фото.

Реквизиты: Shopify — scripts/labels/.env.local (client credentials «Privat API»),
Odoo — ~/Downloads/sync/.env (те же, что у демона синка в /opt/privat-sync/.env).
"""
import json, os, time, urllib.request, urllib.error, xmlrpc.client


def load_env(path):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.startswith("export "):
            k = k[7:].strip()
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))


_here = os.path.dirname(os.path.abspath(__file__))
load_env(os.path.expanduser("~/Downloads/sync/.env"))
load_env(os.path.join(_here, "..", "labels", ".env.local"))

STORE = os.environ["SHOPIFY_STORE"]
API = "2024-10"
_token = ""


def token():
    global _token
    if not _token:
        body = json.dumps({"grant_type": "client_credentials",
                           "client_id": os.environ["SHOPIFY_CLIENT_ID"],
                           "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"]}).encode()
        req = urllib.request.Request(f"https://{STORE}/admin/oauth/access_token", data=body,
                                     headers={"Content-Type": "application/json"})
        _token = json.loads(urllib.request.urlopen(req).read())["access_token"]
    return _token


def rest(path, method="GET", payload=None):
    """REST Admin API с ретраем на 429/5xx."""
    data = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(6):
        req = urllib.request.Request(f"https://{STORE}/admin/api/{API}/{path}", data=data,
                                     method=method,
                                     headers={"X-Shopify-Access-Token": token(),
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return (json.loads(raw) if raw else {}), r.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read()[:400]!r}")
    raise RuntimeError("unreachable")


def all_products(fields="id,title,handle,status,options,variants,images"):
    page, out = f"products.json?limit=250&fields={fields}", []
    while page:
        data, link = rest(page)
        out += data["products"]
        page = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                page = (f"products.json?limit=250&fields={fields}&page_info=" +
                        part.split("page_info=")[1].split(">")[0])
    return out


def odoo():
    url, db = os.environ["ODOO_URL"], os.environ["ODOO_DB"]
    user, key = os.environ["ODOO_USER"], os.environ["ODOO_API_KEY"]
    uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, key, {})
    mo = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def kw(model, method, *a, **k):
        return mo.execute_kw(db, uid, key, model, method, list(a), k)
    return kw
