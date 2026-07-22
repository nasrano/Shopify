#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Печать ценников PRIVAT на Zebra ZD230 (ZPL, 203 dpi).

Локальный веб-инструмент: поиск товара в Shopify по названию / SKU / штрихкоду,
превью ценника и печать нативным ZPL прямо на принтер (очередь CUPS `Zebra_ZPL`).

Ценник:
    Код товара: <SKU>
    |||| штрихкод (кодирует поле barcode) ||||
    Цена: <цена> сом

Почему картинкой (ZPL ^GFA), а не «нативным текстом» ZPL:
встроенные шрифты Zebra не содержат кириллицы — «Код товара», «Цена», «сом»
напечатались бы квадратами. Поэтому вся этикетка рисуется в чёткую 1-битную
картинку под точное разрешение принтера (203 dpi) и уходит как ^GFA. Это по-
прежнему нативный ZPL прямо на принтер (без браузерного окна печати), а превью
на экране = ровно то, что напечатается. Штрихкод рисуется в том же разрешении и
сканируется нормально.

Запуск:
    export SHOPIFY_STORE="0fd8ca-b7.myshopify.com"
    export SHOPIFY_CLIENT_ID=...        (или SHOPIFY_ADMIN_TOKEN=shpat_...)
    export SHOPIFY_CLIENT_SECRET=shpss_...
    python3 pricetag_server.py
    -> открой http://localhost:8765

Проще: ./run.sh  (подхватит .env.local с реквизитами).
"""

import base64
import hashlib
import hmac
import html
import io
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

try:
    import barcode
    from barcode.writer import ImageWriter, SVGWriter
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError as e:
    sys.exit(
        f"Нет зависимости: {e.name}. Установи:\n"
        "  pip3 install python-barcode pillow"
    )

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PRICETAG_PORT", "8765"))

# ---- Статика (фавиконка): отдаётся публично, по белому списку --------------
STATIC_DIR = os.path.join(HERE, "static")
STATIC_TYPES = {".ico": "image/x-icon", ".svg": "image/svg+xml", ".png": "image/png",
                ".webmanifest": "application/manifest+json"}
STATIC_FILES = {
    "/favicon.ico", "/favicon.svg", "/apple-touch-icon.png", "/site.webmanifest",
    "/favicon-16.png", "/favicon-32.png", "/favicon-48.png", "/favicon-64.png",
    "/favicon-192.png", "/favicon-512.png",
}
FAVICON_TAGS = (
    '<link rel="icon" href="/favicon.ico" sizes="any">'
    '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
    '<link rel="manifest" href="/site.webmanifest">'
)

# ---- Конфиг (config.json; секреты — только из окружения) -------------------

DEFAULT_CONFIG = {
    "store": "0fd8ca-b7.myshopify.com",
    "api_version": "2026-01",
    "printer_queue": "Zebra_ZPL",   # очередь CUPS (lpstat -p)
    "dpi": 203,
    "label_mm": {"w": 40, "h": 30},  # размер этикетки — ПОМЕНЯЙ под свою бумагу
    "margin_mm": 1.5,
    "currency": "сом",
    "symbology": "auto",            # auto | code128 | ean13 | ean8 | upca
    "barcode_source": "sku",        # что кодировать в штрихкоде: sku | barcode
    "barcode_text": False,          # рисовать цифры под штрихкодом (артикул уже сверху)
    "supersample": 4,               # качество текста: рендер ×N и уменьшение (2..6)
    "threshold": 128,               # порог ч/б (меньше = буквы жирнее)
    "code_label": "Код",
    "price_label": "Цена",
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(HERE, "config.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            cfg.update({k: v for k, v in user.items() if v is not None})
        except (json.JSONDecodeError, OSError) as e:
            print(f"config.json не прочитан ({e}), беру значения по умолчанию", file=sys.stderr)
    # env может переопределить магазин
    cfg["store"] = os.environ.get("SHOPIFY_STORE", cfg["store"])
    return cfg


CONFIG = load_config()

# ---- Шаблоны этикеток (размер и оформление; редактируются в интерфейсе) -----

TEMPLATES_FILE = os.path.join(HERE, "templates.json")
TEMPLATE_FIELDS = ("margin_mm", "currency", "code_label", "price_label",
                   "barcode_source", "symbology")


def _default_templates():
    lm = CONFIG["label_mm"]
    return {"active": "default", "templates": [{
        "id": "default", "name": f"{lm['w']}×{lm['h']} мм",
        "w_mm": lm["w"], "h_mm": lm["h"],
        "margin_mm": CONFIG.get("margin_mm", 1.5),
        "currency": CONFIG.get("currency", "сом"),
        "code_label": CONFIG.get("code_label", "Код товара"),
        "price_label": CONFIG.get("price_label", "Цена"),
        "barcode_source": CONFIG.get("barcode_source", "sku"),
        "symbology": CONFIG.get("symbology", "auto"),
    }]}


def load_templates():
    try:
        with open(TEMPLATES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("templates"):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    data = _default_templates()
    save_templates(data)
    return data


def save_templates(data):
    tmp = TEMPLATES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TEMPLATES_FILE)


def template_cfg(tpl_id=None):
    """Возвращает (cfg, template): CONFIG, перекрытый выбранным (или активным) шаблоном."""
    data = load_templates()
    by = {t["id"]: t for t in data["templates"]}
    t = by.get(tpl_id) or by.get(data.get("active")) or (data["templates"][0] if data["templates"] else {})
    cfg = dict(CONFIG)
    if t:
        cfg["label_mm"] = {"w": t.get("w_mm", cfg["label_mm"]["w"]),
                           "h": t.get("h_mm", cfg["label_mm"]["h"])}
        for k in TEMPLATE_FIELDS:
            v = t.get(k)
            if v not in (None, ""):
                cfg[k] = v
    return cfg, t


def upsert_template(t):
    data = load_templates()
    tid = (t.get("id") or "").strip() or uuid.uuid4().hex[:8]
    clean = {"id": tid, "name": (t.get("name") or "Без имени").strip()}
    for k in ("w_mm", "h_mm", "margin_mm"):
        try:
            clean[k] = round(float(t.get(k)), 2)   # размеры — 2 знака после запятой
        except (TypeError, ValueError):
            clean[k] = _default_templates()["templates"][0].get(k)
    for k in ("currency", "code_label", "price_label", "barcode_source", "symbology"):
        clean[k] = t.get(k) or _default_templates()["templates"][0].get(k)
    data["templates"] = [x for x in data["templates"] if x["id"] != tid] + [clean]
    if not data.get("active"):
        data["active"] = tid
    save_templates(data)
    return clean, data["active"]


def delete_template(tid):
    data = load_templates()
    data["templates"] = [x for x in data["templates"] if x["id"] != tid]
    if not data["templates"]:
        data = _default_templates()
    if data.get("active") == tid:
        data["active"] = data["templates"][0]["id"]
    save_templates(data)
    return data


def set_active_template(tid):
    data = load_templates()
    if any(x["id"] == tid for x in data["templates"]):
        data["active"] = tid
        save_templates(data)
    return data


# ---- Авторизация: те же аккаунты, что у портала (users.json, scrypt) --------
# Страница входа + подписанный cookie `sid` (без попапа Basic-auth браузера).

USERS_FILE = os.environ.get("PRICETAG_USERS_FILE", "/opt/privat-portal/users.json")
AUTH_OFF = os.environ.get("PRICETAG_AUTH_OFF", "") == "1"  # для локальной отладки
_SECRET = None


def session_secret():
    global _SECRET
    if _SECRET:
        return _SECRET
    s = os.environ.get("PRICETAG_SESSION_SECRET", "")
    if not s:
        keyfile = os.path.join(HERE, "session.key")
        try:
            with open(keyfile) as f:
                s = f.read().strip()
        except OSError:
            s = secrets.token_hex(32)
            try:
                with open(keyfile, "w") as f:
                    f.write(s)
                os.chmod(keyfile, 0o600)
            except OSError:
                pass
    _SECRET = s.encode()
    return _SECRET


def load_users():
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def verify_login(email, password):
    """Проверка по users.json портала: scrypt(password, salt, 64) == hash."""
    email = (email or "").strip().lower()
    for u in load_users():
        if u.get("email", "").lower() == email:
            try:
                h = hashlib.scrypt(str(password).encode(), salt=u["salt"].encode(),
                                   n=16384, r=8, p=1, dklen=64)
            except Exception:
                return None
            if hmac.compare_digest(h.hex(), u.get("hash", "")):
                return {"email": u["email"], "name": u.get("name", u["email"]),
                        "role": u.get("role", "seller")}
    return None


def make_token(user, days=30):
    payload = {"email": user["email"], "name": user.get("name", ""),
               "role": user.get("role", "seller"), "exp": int(time.time()) + days * 86400}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(session_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig


def verify_token(token):
    try:
        raw, sig = (token or "").split(".", 1)
    except ValueError:
        return None
    good = hmac.new(session_secret(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ---- Кириллические шрифты (macOS Arial) ------------------------------------

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",         # macOS
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      # Linux (кириллица)
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


FONT_REG = _first_existing(FONT_CANDIDATES)
FONT_BOLD = _first_existing(FONT_BOLD_CANDIDATES) or FONT_REG


def _font(bold, size):
    path = (FONT_BOLD if bold else FONT_REG)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---- Shopify Admin API (тот же способ авторизации, что в scripts/seo) -------

_token_cache = ""


def get_token():
    """shpat-токен напрямую либо обмен client_id+secret (client_credentials)."""
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
        raise RuntimeError(
            "Нет реквизитов Shopify. Задай в окружении: SHOPIFY_CLIENT_ID и "
            "SHOPIFY_CLIENT_SECRET (или SHOPIFY_ADMIN_TOKEN=shpat_...). "
            "Проще — заполни scripts/labels/.env.local и запусти через ./run.sh"
        )
    req = urllib.request.Request(
        f"https://{CONFIG['store']}/admin/oauth/access_token",
        data=json.dumps({"client_id": cid, "client_secret": sec,
                         "grant_type": "client_credentials"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        _token_cache = json.loads(r.read())["access_token"]
    return _token_cache


def gql(query, variables=None):
    token = get_token()
    req = urllib.request.Request(
        f"https://{CONFIG['store']}/admin/api/{CONFIG['api_version']}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read())
            if "errors" in data:
                if any(e.get("extensions", {}).get("code") == "THROTTLED" for e in data["errors"]):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False)[:300])
            return data["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")
    raise RuntimeError("Shopify API перегружен, попробуй ещё раз")


SEARCH_QUERY = """
query($q: String!) {
  products(first: 20, query: $q) {
    nodes {
      title
      status
      featuredImage { url }
      variants(first: 30) {
        nodes { sku barcode price title }
      }
    }
  }
}
"""


def search_variants(term):
    term = term.strip()
    if not term:
        return []
    data = gql(SEARCH_QUERY, {"q": term})
    rows = []
    for p in data["products"]["nodes"]:
        vs = p["variants"]["nodes"]
        multi = len(vs) > 1
        image = (p.get("featuredImage") or {}).get("url") or ""
        for v in vs:
            title = p["title"]
            if multi and v.get("title") and v["title"] != "Default Title":
                title = f"{title} — {v['title']}"
            rows.append({
                "title": title,
                "sku": v.get("sku") or "",
                "barcode": v.get("barcode") or "",
                "price": v.get("price") or "",
                "status": p.get("status") or "",
                "image": image,
            })
    return rows


# ---- Формат цены -----------------------------------------------------------

def fmt_price(raw):
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return str(raw)
    if d == d.to_integral_value():
        return f"{d:.0f}"
    return f"{d:.2f}"


# ---- Штрихкод --------------------------------------------------------------

def pick_symbology(data, configured):
    d = (data or "").strip()
    if configured and configured != "auto":
        return configured, d
    if d.isdigit():
        if len(d) == 13:
            return "ean13", d
        if len(d) == 12:
            return "upca", d
        if len(d) == 8:
            return "ean8", d
    return "code128", d


def render_barcode(data, symbology, avail_px, dpi, bars_mm, want_text=True):
    """PIL-картинка штрихкода не шире avail_px. При переполнении — один
    пересчёт module_width, чтобы не растягивать штрихи (плохо для скана)."""
    def _render(mw_mm):
        cls = barcode.get_barcode_class(symbology)
        opts = {
            "module_width": mw_mm,
            "module_height": bars_mm,
            "quiet_zone": 1.0,
            "font_size": 7,
            "text_distance": 1.2,
            "write_text": want_text,
            "dpi": dpi,
            "background": "white",
            "foreground": "black",
        }
        obj = cls(data, writer=ImageWriter())
        return obj.render(writer_options=opts)

    mw = 0.33  # ~2.6 точки на модуль при 203 dpi
    img = _render(mw)
    if img.width > avail_px:
        mw = max(0.19, mw * avail_px / img.width)  # не тоньше ~1.5 точки
        img = _render(mw)
    return img


# ---- Сборка этикетки -> PIL + ZPL ------------------------------------------

def mm2dot(mm, dpi):
    return int(round(mm * dpi / 25.4))


def build_label(sku, barcode_data, price, w_mm, h_mm, dpi, cfg):
    """Возвращает (PIL.Image 1-bit, метаданные dict).

    Текст рисуется на слое ×SS и качественно уменьшается (LANCZOS) — края
    ложатся точнее, буквы выглядят ровнее при печати в 1 бит на 203 dpi.
    Штрихкод рендерится сразу в device-res (штрихи должны быть точными).
    """
    W = mm2dot(w_mm, dpi)
    H = mm2dot(h_mm, dpi)
    margin = mm2dot(cfg.get("margin_mm", 1.5), dpi)
    SS = max(1, min(6, int(cfg.get("supersample", 4))))
    thr = int(cfg.get("threshold", 128))
    warnings = []

    meas = ImageDraw.Draw(Image.new("L", (W, H)))  # только для метрик в device-res

    price_fs = max(14, int(H * 0.15))   # цена чуть меньше
    sku_fs = price_fs                    # код — того же размера, что и цена

    def fit_font(text, bold, start_fs, max_w):
        fs = start_fs
        while fs > 8:
            f = _font(bold, fs)
            if meas.textlength(text, font=f) <= max_w:
                return f, fs
            fs -= 1
        return _font(bold, 8), 8

    avail_w = W - 2 * margin

    # текстовый слой в высоком разрешении
    big = Image.new("L", (W * SS, H * SS), 255)
    db = ImageDraw.Draw(big)

    # 1) Код товара: SKU (по центру)
    sku_line = f"{cfg.get('code_label', 'Код товара')}: {sku}" if sku else cfg.get("code_label", "Код товара")
    sku_font, sku_fs_u = fit_font(sku_line, False, sku_fs, avail_w)
    y = margin
    sku_x = max(margin, (W - meas.textlength(sku_line, font=sku_font)) // 2)
    db.text((sku_x * SS, y * SS), sku_line, font=_font(False, sku_fs_u * SS), fill=0)
    y = y + meas.textbbox((0, 0), sku_line, font=sku_font)[3] + max(3, int(H * 0.02))

    # 3) Цена (место снизу резервируем)
    price_line = f"{cfg.get('price_label', 'Цена')}: {fmt_price(price)} {cfg.get('currency', 'сом')}"
    price_font, price_fs_u = fit_font(price_line, True, price_fs, avail_w)
    price_h = meas.textbbox((0, 0), price_line, font=price_font)[3]
    price_top = H - margin - price_h
    px = max(margin, (W - meas.textlength(price_line, font=price_font)) // 2)
    db.text((px * SS, price_top * SS), price_line, font=_font(True, price_fs_u * SS), fill=0)

    # 2) Штрихкод между SKU и ценой (кодирует артикул/SKU по умолчанию)
    bar = Image.new("L", (W, H), 255)
    gap = max(3, int(H * 0.02))
    bc_area_top = y
    bc_area_h = (price_top - gap) - bc_area_top
    bc_source = cfg.get("barcode_source", "sku")  # sku | barcode
    if bc_source == "barcode":
        bc_data = (barcode_data or "").strip()
        if not bc_data:
            bc_data = (sku or "").strip()
            warnings.append("У товара нет поля barcode — в штрихкоде закодирован SKU")
    else:
        bc_data = (sku or "").strip()

    show_hr = bool(cfg.get("barcode_text", False))  # цифры под штрихкодом (по умолч. нет)

    if bc_data and bc_area_h > mm2dot(6, dpi):
        sym, payload = pick_symbology(bc_data, cfg.get("symbology", "auto"))
        if show_hr:
            hr_fs = max(10, int(H * 0.07))
            hr_font = _font(False, hr_fs * SS)
            hr_h = meas.textbbox((0, 0), "0", font=_font(False, hr_fs))[3]
            hr_gap = max(2, int(H * 0.01))
        else:
            hr_h = hr_gap = 0
        bars_area_h = bc_area_h - hr_h - hr_gap
        bars_mm = max(3.5, bars_area_h / dpi * 25.4)
        try:
            bc_img = render_barcode(payload, sym, avail_w, dpi, bars_mm, want_text=False)
        except Exception as e:  # невалидный EAN и т.п. -> Code128
            warnings.append(f"{sym} не принял '{payload}' ({e}) — использую Code128")
            sym = "code128"
            bc_img = render_barcode(payload, sym, avail_w, dpi, bars_mm, want_text=False)
        if bc_img.height > bars_area_h:  # пере-рендер по высоте, без пиксельного ресайза
            bars_mm = max(3.0, bars_mm * bars_area_h / bc_img.height)
            bc_img = render_barcode(payload, sym, avail_w, dpi, bars_mm, want_text=False)
        bc_img = bc_img.convert("L").point(lambda p: 0 if p < 128 else 255, mode="1")
        bx = max(0, (W - bc_img.width) // 2)
        bar.paste(bc_img, (bx, bc_area_top))
        if show_hr:  # цифры по центру под штрихами (на текстовом слое, тоже сглажены)
            hr_x = max(margin, (W - meas.textlength(payload, font=_font(False, hr_fs))) // 2)
            db.text((hr_x * SS, (bc_area_top + bc_img.height + hr_gap) * SS),
                    payload, font=hr_font, fill=0)
    elif bc_data:
        warnings.append("Мало места по высоте для штрихкода — увеличь размер этикетки")

    # уменьшаем текст, совмещаем со штрихкодом, режем порогом без дизеринга
    txt = big.resize((W, H), Image.LANCZOS)
    base = ImageChops.darker(txt, bar)
    bw = base.point(lambda p: 0 if p < thr else 255, mode="1")
    return bw, {"warnings": warnings, "w_dots": W, "h_dots": H}


def png_bytes(img):
    buf = io.BytesIO()
    img.convert("1").save(buf, format="PNG")
    return buf.getvalue()


def img_to_gfa(img):
    bw = img.convert("1")
    W, H = bw.size
    row_bytes = (W + 7) // 8
    raw = bw.tobytes()               # упаковано по битам, 1=белый, ряды по границе байта
    inv = bytes((~b) & 0xFF for b in raw)  # ZPL: 1=чёрная точка
    total = len(inv)
    return f"^FO0,0^GFA,{total},{total},{row_bytes},{inv.hex().upper()}^FS"


def make_zpl(img, w_dots, h_dots, copies=1):
    body = img_to_gfa(img)
    z = ["^XA", "^CI28", "^LH0,0", f"^PW{w_dots}", f"^LL{h_dots}", body]
    if copies > 1:
        z.append(f"^PQ{copies},0,0,Y")
    z.append("^XZ")
    return "\n".join(z) + "\n"


# ---- HTML-ценник для window.print() (печать через диалог браузера) ---------

def svg_barcode(data, cfg, h_mm):
    """Векторный штрихкод (SVG в мм) — чёткий при печати через браузер."""
    sym, payload = pick_symbology((data or "").strip(), cfg.get("symbology", "auto"))
    bars_mm = max(6.0, round(h_mm * 0.42, 1))
    for s in (sym, "code128"):
        try:
            buf = io.BytesIO()
            barcode.generate(s, payload, writer=SVGWriter(), output=buf, writer_options={
                "module_height": bars_mm, "module_width": 0.35,
                "quiet_zone": 1.0, "write_text": False,
            })
            svg = buf.getvalue().decode("utf-8")
            i = svg.find("<svg")
            return svg[i:] if i >= 0 else svg
        except Exception:
            continue
    return ""


def label_html(sku, price, w_mm, h_mm, cfg, copies=1, auto=False, barcode_value=""):
    """Готовая печатная HTML-страница ценника под window.print()."""
    margin = cfg.get("margin_mm", 1.5)
    sku = (sku or "").strip()
    code_line = f"{cfg.get('code_label', 'Код товара')}: {sku}" if sku else cfg.get("code_label", "Код товара")
    price_line = f"{cfg.get('price_label', 'Цена')}: {fmt_price(price)} {cfg.get('currency', 'сом')}"
    bc_src = sku if cfg.get("barcode_source", "sku") == "sku" else (barcode_value or sku)
    svg = svg_barcode(bc_src, cfg, h_mm)
    price_pt = max(7, round(h_mm * 0.40))   # цена чуть меньше прежнего
    code_pt = price_pt                       # код — того же размера, что и цена
    one = (
        '<div class="label"><div class="inner">'
        f'<div class="code">{html.escape(code_line)}</div>'
        f'<div class="bc">{svg}</div>'
        f'<div class="price">{html.escape(price_line)}</div>'
        '</div></div>'
    )
    labels = one * max(1, int(copies))
    auto_js = "window.focus();window.print();" if auto else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Ценник {html.escape(sku or '')}</title>
{FAVICON_TAGS}
<style>
@page {{ size: {w_mm}mm {h_mm}mm; margin: 0; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ background:#fff; }}
.label {{ width:{w_mm}mm; height:{h_mm}mm; padding:{margin}mm; background:#fff; color:#000;
  font-family:Arial,'Helvetica Neue',sans-serif; overflow:hidden; page-break-after:always; }}
.label:last-child {{ page-break-after:auto; }}
.inner {{ width:100%; height:100%; display:flex; flex-direction:column;
  align-items:center; justify-content:space-between; }}
.code {{ font-size:{code_pt}pt; font-weight:600; white-space:nowrap; line-height:1.05; }}
.bc {{ flex:1; display:flex; align-items:center; justify-content:center; width:100%; min-height:0; padding:0.5mm 0; }}
.bc svg {{ max-width:100%; max-height:100%; width:auto; height:auto; }}
.price {{ font-size:{price_pt}pt; font-weight:800; white-space:nowrap; line-height:1.05; }}
</style></head><body>
{labels}
<script>
(function(){{
  function fit(e, max){{ var s=parseFloat(getComputedStyle(e).fontSize);
    while(e.scrollWidth>max && s>5){{ s-=0.5; e.style.fontSize=s+'px'; }} }}
  document.querySelectorAll('.inner').forEach(function(inn){{
    inn.querySelectorAll('.code,.price').forEach(function(e){{ fit(e, inn.clientWidth*0.99); }});
  }});
  {auto_js}
}})();
</script></body></html>"""


def _variant_gid(v):
    v = (v or "").strip()
    if v.startswith("gid://"):
        return v
    if v.isdigit():
        return f"gid://shopify/ProductVariant/{v}"
    return v


def fetch_variant(variant_id):
    gid = _variant_gid(variant_id)
    data = gql("query($id: ID!){ productVariant(id:$id){ sku barcode price product{ title } } }",
               {"id": gid})
    v = data.get("productVariant")
    if not v:
        raise RuntimeError("Вариант не найден")
    return {"sku": v.get("sku") or "", "barcode": v.get("barcode") or "",
            "price": v.get("price") or "", "title": (v.get("product") or {}).get("title", "")}


def fetch_product_variants(product_id):
    pid = product_id.strip()
    if pid.isdigit():
        pid = f"gid://shopify/Product/{pid}"
    data = gql("""query($id: ID!){ product(id:$id){ title
        variants(first:50){ nodes{ id sku barcode price title } } } }""", {"id": pid})
    p = data.get("product")
    if not p:
        raise RuntimeError("Товар не найден")
    out = []
    for v in p["variants"]["nodes"]:
        out.append({"id": v["id"], "sku": v.get("sku") or "", "barcode": v.get("barcode") or "",
                    "price": v.get("price") or "", "title": v.get("title") or "",
                    "product": p["title"]})
    return p["title"], out


# ---- Печать ----------------------------------------------------------------

def list_printers():
    try:
        out = subprocess.run(["lpstat", "-p"], capture_output=True, text=True, timeout=10)
        names = []
        for line in out.stdout.splitlines():
            if line.startswith("printer "):
                names.append(line.split()[1])
        return names
    except Exception:
        return []


def send_to_printer(zpl, queue):
    """Сырой ZPL в очередь CUPS: lp -o raw -d <queue>."""
    if not queue:
        return False, "Не задан принтер (printer_queue)"
    try:
        p = subprocess.run(
            ["lp", "-d", queue, "-o", "raw"],
            input=zpl.encode("utf-8"),
            capture_output=True, timeout=30,
        )
        if p.returncode == 0:
            return True, (p.stdout.decode().strip() or "Отправлено на печать")
        return False, (p.stderr.decode().strip() or f"lp код {p.returncode}")
    except FileNotFoundError:
        return False, "Команда lp не найдена (это не macOS/CUPS?)"
    except Exception as e:
        return False, str(e)


# ---- HTTP ------------------------------------------------------------------

def _build_from_payload(payload):
    cfg, _ = template_cfg(payload.get("template"))
    w_mm = float(payload.get("w_mm") or cfg["label_mm"]["w"])
    h_mm = float(payload.get("h_mm") or cfg["label_mm"]["h"])
    dpi = int(payload.get("dpi") or cfg["dpi"])
    img, meta = build_label(
        payload.get("sku", ""), payload.get("barcode", ""),
        payload.get("price", ""), w_mm, h_mm, dpi, cfg,
    )
    return img, meta, w_mm, h_mm, dpi


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _html(self, markup, code=200):
        body = markup.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- авторизация
    def _cookie(self, name):
        for part in (self.headers.get("Cookie", "") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def _current_user(self):
        if AUTH_OFF:
            return {"name": "dev", "role": "admin", "email": "dev@local"}
        return verify_token(self._cookie("sid"))

    def _redirect(self, location, set_cookie=None, code=302):
        self.send_response(code)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _secure(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _guard(self):
        """True если пользователь авторизован; иначе уже отправлен ответ."""
        if self._current_user():
            return True
        if urlparse(self.path).path.startswith("/api/"):
            self._json({"ok": False, "error": "unauthorized"}, 401)
        else:
            self._redirect("/login?next=" + quote(self.path, safe=""))
        return False

    def _serve_login(self, qs):
        if self._current_user():   # уже вошли — на главную
            self._redirect("/")
            return
        nxt = (qs.get("next") or ["/"])[0]
        err = "Неверная почта или пароль" if (qs.get("error") or [""])[0] else ""
        self._html(LOGIN_PAGE.replace("__NEXT__", html.escape(nxt, quote=True))
                             .replace("__ERR__", html.escape(err)))

    def _do_login(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        data = parse_qs(self.rfile.read(n).decode("utf-8")) if n else {}
        email = (data.get("email") or [""])[0]
        password = (data.get("password") or [""])[0]
        nxt = (data.get("next") or ["/"])[0]
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        user = verify_login(email, password)
        if not user:
            self._redirect("/login?error=1&next=" + quote(nxt, safe=""))
            return
        token = make_token(user)
        cookie = f"sid={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age=2592000"
        if self._secure():
            cookie += "; Secure"
        self._redirect(nxt, set_cookie=cookie)

    def _do_logout(self):
        self._redirect("/login", set_cookie="sid=; HttpOnly; Path=/; Max-Age=0")

    def _serve_static(self, path):
        fpath = os.path.join(STATIC_DIR, os.path.basename(path))
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type",
                         STATIC_TYPES.get(os.path.splitext(fpath)[1], "application/octet-stream"))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_print(self, qs):
        """Печатная страница ценника. Открывается кнопкой из админки:
        /print?variant=<id> | /print?id=<productId> | /print?sku=...&price=...
        Размер/оформление берётся из шаблона (?template=<id> или активного)."""
        def g(k, d=""):
            return (qs.get(k) or [d])[0]
        cfg, tpl = template_cfg(g("template"))
        tid = tpl.get("id", "")
        sku, price, barcode_v = g("sku"), g("price"), g("barcode")
        w_mm = float(g("w") or cfg["label_mm"]["w"])
        h_mm = float(g("h") or cfg["label_mm"]["h"])
        copies = int(g("copies") or 1)
        auto = g("auto", "1").lower() not in ("0", "false", "no")
        # Shopify admin-link сам добавляет ?id=<productId> (и shop/host) — поддержим
        prod = g("product") or g("id") or (g("ids").split(",")[0] if g("ids") else "")
        try:
            if g("variant") and not sku:
                v = fetch_variant(g("variant"))
                sku, barcode_v = v["sku"], v["barcode"]
                price = price or v["price"]
            elif prod and not sku:
                title, variants = fetch_product_variants(prod)
                if len(variants) == 1:
                    v = variants[0]
                    sku, barcode_v, price = v["sku"], v["barcode"], price or v["price"]
                else:  # несколько вариантов — покажем выбор
                    rows = "".join(
                        f'<a class="v" href="/print?variant={html.escape(v["id"])}'
                        f'&template={html.escape(tid)}&copies={copies}&auto=1">'
                        f'<b>{html.escape(v["title"] or v["sku"])}</b>'
                        f'<span>SKU {html.escape(v["sku"])} · {html.escape(v["price"])} {cfg["currency"]}</span></a>'
                        for v in variants)
                    self._html(CHOOSER_PAGE.replace("__TITLE__", html.escape(title))
                                           .replace("__ROWS__", rows))
                    return
        except Exception as e:
            self._html(f"<!doctype html><meta charset=utf-8><p>Ошибка: {html.escape(str(e))}</p>", 200)
            return
        self._html(label_html(sku, price, w_mm, h_mm, cfg, copies, auto, barcode_v))

    # -- GET
    def do_GET(self):
        u = urlparse(self.path)
        # публичные маршруты (без авторизации)
        if u.path in STATIC_FILES:
            self._serve_static(u.path)
            return
        if u.path == "/login":
            self._serve_login(parse_qs(u.query))
            return
        if u.path == "/logout":
            self._do_logout()
            return
        if u.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # всё остальное — только для авторизованных
        if not self._guard():
            return
        if u.path == "/":
            self._html(HTML_PAGE)
            return
        if u.path == "/setup":
            self._html(SETUP_PAGE)
            return
        if u.path == "/print":
            self._serve_print(parse_qs(u.query))
            return
        if u.path == "/api/config":
            user = self._current_user() or {}
            self._json({
                "store": CONFIG["store"],
                "printer_queue": CONFIG["printer_queue"],
                "printers": list_printers(),
                "dpi": CONFIG["dpi"],
                "label_mm": CONFIG["label_mm"],
                "currency": CONFIG["currency"],
                "user": {"name": user.get("name", ""), "role": user.get("role", "")},
            })
            return
        if u.path == "/api/search":
            q = (parse_qs(u.query).get("q") or [""])[0]
            try:
                self._json({"ok": True, "items": search_variants(q)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 200)
            return
        if u.path == "/api/templates":
            self._json(load_templates())
            return
        self.send_error(404)

    # -- POST
    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/login":           # публичный (вход по форме)
            self._do_login()
            return
        if not self._guard():            # остальное — только авторизованным
            return
        try:
            payload = self._read_json()
        except Exception:
            self._json({"ok": False, "error": "плохой JSON"}, 400)
            return

        if u.path == "/api/render":
            img, meta, *_ = _build_from_payload(payload)
            self._json({
                "ok": True,
                "png": "data:image/png;base64," + base64.b64encode(png_bytes(img)).decode(),
                "warnings": meta["warnings"],
            })
            return

        if u.path == "/api/zpl":
            img, meta, w_mm, h_mm, dpi = _build_from_payload(payload)
            copies = int(payload.get("copies") or 1)
            zpl = make_zpl(img, meta["w_dots"], meta["h_dots"], copies)
            self._json({"ok": True, "zpl": zpl})
            return

        if u.path == "/api/print":
            img, meta, *_ = _build_from_payload(payload)
            copies = max(1, int(payload.get("copies") or 1))
            zpl = make_zpl(img, meta["w_dots"], meta["h_dots"], copies)
            queue = payload.get("printer") or CONFIG["printer_queue"]
            ok, msg = send_to_printer(zpl, queue)
            self._json({"ok": ok, "message": msg, "warnings": meta["warnings"]})
            return

        if u.path == "/api/templates/save":
            t, active = upsert_template(payload)
            self._json({"ok": True, "template": t, "active": active})
            return

        if u.path == "/api/templates/delete":
            self._json({"ok": True, **delete_template(payload.get("id", ""))})
            return

        if u.path == "/api/templates/active":
            self._json({"ok": True, **set_active_template(payload.get("id", ""))})
            return

        self.send_error(404)


def main():
    print(f"Ценники PRIVAT -> http://localhost:{PORT}")
    print(f"Магазин: {CONFIG['store']} | принтер: {CONFIG['printer_queue']} | "
          f"этикетка: {CONFIG['label_mm']['w']}x{CONFIG['label_mm']['h']} мм @ {CONFIG['dpi']}dpi")
    if not FONT_REG:
        print("ВНИМАНИЕ: не найден шрифт Arial — кириллица может не отрисоваться", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


# ---- Веб-страница (одностраничный UI) --------------------------------------

CHOOSER_PAGE = r"""<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Выбор варианта · PRIVAT barcode</title>
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link href="https://fonts.googleapis.com/css2?family=Prata&family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
<script>try{document.documentElement.dataset.theme=localStorage.getItem('theme')||'light'}catch(e){document.documentElement.dataset.theme='light'}</script>
<style>
  :root{--page-bg:#EFE9E1;--bg:#FAF6F0;--card:#FFFFFF;--ink:#2A211C;--sub:#75655A;
        --line:#EADFD3;--accent:#B4756A;--accent-ink:#FFF7F2;--accent-deep:#96594B;--soft:#F1E7DB;--r:16px;}
  :root[data-theme="dark"]{--page-bg:#17111A;--bg:#221A22;--card:#2D232D;--ink:#F3ECF0;
        --sub:#B29FAC;--line:#3D2F3C;--accent:#C9A26B;--accent-ink:#241B10;--accent-deep:#B08D57;--soft:#2A1F29;}
  *{box-sizing:border-box;margin:0;}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;
       font-family:'Manrope',sans-serif;background:var(--page-bg);color:var(--ink);}
  .box{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:26px;width:420px;max-width:94vw;}
  h1{font-family:'Prata',serif;font-weight:400;font-size:18px;margin-bottom:4px;}
  .sub{color:var(--sub);font-size:13px;margin-bottom:16px;}
  .v{display:flex;flex-direction:column;gap:2px;padding:12px 14px;border:1px solid var(--line);
     border-radius:12px;margin-bottom:8px;text-decoration:none;color:var(--ink);transition:.12s;}
  .v:hover{border-color:var(--accent);background:var(--soft);}
  .v span{color:var(--sub);font-size:12.5px;}
</style></head>
<body><div class="box">
  <h1>__TITLE__</h1>
  <p class="sub">Выбери вариант для печати</p>
  __ROWS__
</div></body></html>
"""

LOGIN_PAGE = r"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Вход · PRIVAT barcode</title>
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/site.webmanifest">
<link href="https://fonts.googleapis.com/css2?family=Prata&family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
<script>try{document.documentElement.dataset.theme=localStorage.getItem('theme')||'light'}catch(e){document.documentElement.dataset.theme='light'}</script>
<style>
  :root{--page-bg:#EFE9E1;--bg:#FAF6F0;--card:#FFFFFF;--ink:#2A211C;--sub:#75655A;
        --line:#EADFD3;--accent:#B4756A;--accent-ink:#FFF7F2;--accent-deep:#96594B;
        --soft:#F1E7DB;--chip:#F6EEE4;--r:16px;}
  :root[data-theme="dark"]{
        --page-bg:#17111A;--bg:#221A22;--card:#2D232D;--ink:#F3ECF0;--sub:#B29FAC;
        --line:#3D2F3C;--accent:#C9A26B;--accent-ink:#241B10;--accent-deep:#B08D57;
        --soft:#2A1F29;--chip:#372A36;}
  *{box-sizing:border-box;margin:0;}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;
       font-family:'Manrope',sans-serif;background:var(--page-bg);color:var(--ink);}
  form{background:var(--card);border:1px solid var(--line);border-radius:20px;
       padding:28px;width:320px;max-width:92vw;box-shadow:0 10px 34px rgba(0,0,0,.06);text-align:center;}
  .logo{font-family:'Prata',serif;font-size:24px;letter-spacing:.12em;line-height:1;}
  .logo-sub{display:block;font-family:'Manrope',sans-serif;font-size:8px;letter-spacing:.42em;
            color:var(--accent);font-weight:700;text-transform:uppercase;margin-top:3px;}
  .sub{color:var(--sub);font-size:13px;margin:8px 0 18px;}
  input{width:100%;height:44px;padding:0 14px;background:var(--bg);color:var(--ink);
        border:1px solid var(--line);border-radius:12px;font:inherit;margin-bottom:10px;}
  input:focus{outline:none;border-color:var(--accent);}
  button{width:100%;height:44px;margin-top:6px;border:none;border-radius:12px;font-family:inherit;
         background:var(--accent);color:var(--accent-ink);font-weight:600;font-size:15px;cursor:pointer;}
  button:hover{background:var(--accent-deep);}
  .err{color:#96311F;font-size:13px;margin-top:10px;min-height:16px;}
</style></head>
<body>
<form method="post" action="/login">
  <div class="logo">PRIVAT<span class="logo-sub">barcode</span></div>
  <p class="sub">Вход для админов</p>
  <input type="hidden" name="next" value="__NEXT__">
  <input type="email" name="email" placeholder="Почта" autocomplete="username" autofocus required>
  <input type="password" name="password" placeholder="Пароль" autocomplete="current-password" required>
  <button type="submit">Войти</button>
  <div class="err">__ERR__</div>
</form>
</body></html>
"""

SETUP_PAGE = r"""<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Кнопка печати · PRIVAT barcode</title>
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/site.webmanifest">
<link href="https://fonts.googleapis.com/css2?family=Prata&family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
<script>try{document.documentElement.dataset.theme=localStorage.getItem('theme')||'light'}catch(e){document.documentElement.dataset.theme='light'}</script>
<style>
  :root{--page-bg:#EFE9E1;--bg:#FAF6F0;--card:#FFFFFF;--ink:#2A211C;--sub:#75655A;
        --line:#EADFD3;--accent:#B4756A;--accent-ink:#FFF7F2;--accent-deep:#96594B;--soft:#F1E7DB;}
  :root[data-theme="dark"]{--page-bg:#17111A;--bg:#221A22;--card:#2D232D;--ink:#F3ECF0;--sub:#B29FAC;
        --line:#3D2F3C;--accent:#C9A26B;--accent-ink:#241B10;--accent-deep:#B08D57;--soft:#2A1F29;}
  *{box-sizing:border-box;margin:0;}
  body{font-family:'Manrope',sans-serif;background:var(--page-bg);color:var(--ink);
       min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}
  .box{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:32px;max-width:560px;}
  .logo{font-family:'Prata',serif;font-size:22px;letter-spacing:.14em;text-align:center;}
  .logo span{display:block;font-size:8px;letter-spacing:.42em;color:var(--accent);font-weight:700;text-transform:uppercase;margin-top:2px;font-family:'Manrope',sans-serif;}
  h2{font-family:'Prata',serif;font-weight:400;font-size:18px;margin:20px 0 10px;}
  p{color:var(--sub);font-size:14px;margin-bottom:12px;line-height:1.5;}
  ol{color:var(--ink);font-size:14px;margin:12px 0 0 18px;line-height:1.7;}
  .bm{display:inline-block;background:var(--accent);color:var(--accent-ink);font-weight:600;
      text-decoration:none;padding:12px 20px;border-radius:12px;cursor:grab;font-size:15px;}
  .hint{font-size:12.5px;color:var(--sub);margin-top:6px;}
  a.back{color:var(--accent-deep);font-size:13px;text-decoration:none;display:inline-block;margin-top:20px;}
</style></head>
<body><div class="box">
  <div class="logo">PRIVAT<span>barcode</span></div>
  <h2>Кнопка «Печать ценника» в браузере</h2>
  <p>Перетащи эту кнопку на панель закладок браузера (мышкой):</p>
  <p><a class="bm" href="javascript:(function(){var m=location.href.match(/products\/(\d+)/);if(!m){alert('Открой карточку товара в админке Shopify');return;}window.open('https://print.privat.kg/print?auto=1&id='+m[1]);})();">🏷️ Печать ценника</a></p>
  <p class="hint">Если панель закладок скрыта — включи её: View → Always Show Bookmarks Bar (⇧⌘B).</p>
  <ol>
    <li>Открой любой товар в админке Shopify (карточку товара).</li>
    <li>Нажми закладку «Печать ценника» на панели.</li>
    <li>Откроется печать ценника этого товара — первый раз спросит вход (тот же логин).</li>
  </ol>
  <a class="back" href="/">← к печати ценников</a>
</div></body></html>
"""

HTML_PAGE = r"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>PRIVAT barcode</title>
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/site.webmanifest">
<link href="https://fonts.googleapis.com/css2?family=Prata&family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
<script>try{document.documentElement.dataset.theme=localStorage.getItem('theme')||'light'}catch(e){document.documentElement.dataset.theme='light'}</script>
<style>
  :root { --page-bg:#EFE9E1; --bg:#FAF6F0; --card:#FFFFFF; --ink:#2A211C; --sub:#75655A;
          --line:#EADFD3; --accent:#B4756A; --accent-ink:#FFF7F2; --accent-deep:#96594B;
          --soft:#F1E7DB; --chip:#F6EEE4; --r:16px; --danger:#96311F; }
  :root[data-theme="dark"] {
          --page-bg:#17111A; --bg:#221A22; --card:#2D232D; --ink:#F3ECF0; --sub:#B29FAC;
          --line:#3D2F3C; --accent:#C9A26B; --accent-ink:#241B10; --accent-deep:#B08D57;
          --soft:#2A1F29; --chip:#372A36; }
  * { box-sizing:border-box; }
  html, body { height:100%; }
  body { margin:0; font-family:'Manrope',sans-serif; font-size:14px;
         background:var(--page-bg); color:var(--ink);
         display:flex; flex-direction:column; overflow:hidden; }
  header { padding:10px 20px; background:var(--bg); border-bottom:1px solid var(--line);
           display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; }
  .logo-c { justify-self:center; display:flex; flex-direction:column; align-items:center; line-height:1.05; }
  .logo-main { font-family:'Prata',serif; font-size:19px; letter-spacing:.12em; color:var(--ink); }
  .logo-sub { font-size:8px; letter-spacing:.42em; color:var(--accent); font-weight:700;
              text-transform:uppercase; margin-top:1px; }
  .who { color:var(--sub); font-size:12.5px; margin-left:4px; }
  .wrap { flex:1; min-height:0; display:grid; grid-template-columns:1fr 380px;
          grid-template-rows:minmax(0,1fr); gap:16px; padding:16px 20px;
          width:100%; max-width:1180px; margin:0 auto; }
  @media (max-width:860px){ .wrap{ grid-template-columns:1fr; grid-template-rows:none; overflow:auto; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:var(--r);
          padding:16px; max-height:100%; overflow:auto; }
  h2 { font-family:'Prata',serif; font-weight:400; font-size:15px; letter-spacing:.02em;
       color:var(--ink); margin:0 0 14px; }
  input, select, button { font-family:inherit; }
  input, select { width:100%; height:40px; padding:0 14px; background:var(--card); color:var(--ink);
                  border:1px solid var(--line); border-radius:12px; font-size:14px; }
  input:focus, select:focus { outline:none; border-color:var(--accent); }
  .row { display:flex; gap:8px; }
  .field { margin-bottom:10px; }
  .field label { display:block; font-size:12px; color:var(--sub); margin-bottom:5px; }
  .results { margin-top:12px; max-height:360px; overflow:auto; }
  .item { display:flex; gap:11px; align-items:center; padding:9px 11px; border:1px solid var(--line);
          border-radius:12px; margin-bottom:8px; cursor:pointer; transition:.12s; background:var(--card); }
  .item:hover { border-color:var(--accent); background:var(--soft); }
  .item.sel { border-color:var(--accent); background:var(--chip); }
  .item .it-txt { min-width:0; }
  .item .t { font-weight:600; }
  .item .s { color:var(--sub); font-size:12.5px; margin-top:3px; }
  .thumb { width:46px; height:46px; border-radius:9px; object-fit:cover; flex:none;
           background:var(--soft); border:1px solid var(--line); }
  .thumb.noimg { display:flex; align-items:center; justify-content:center; font-size:9px;
                 color:var(--sub); text-align:center; line-height:1.1; }
  .prodinfo { display:none; align-items:center; gap:11px; margin-bottom:12px; }
  .prodinfo .thumb { width:52px; height:52px; }
  .prodinfo .pt { font-weight:600; font-size:13.5px; }
  .badge { display:inline-block; font-size:11px; padding:2px 8px; border-radius:999px;
           background:var(--soft); color:var(--accent-deep); margin-left:6px; }
  button { cursor:pointer; border:none; border-radius:12px; padding:10px 14px; font-weight:600; }
  .btn-p { background:var(--accent); color:var(--accent-ink); width:100%; font-size:15px; height:46px; }
  .btn-p:hover { background:var(--accent-deep); }
  .btn-s { background:var(--chip); color:var(--accent-deep); border:1px solid var(--line); }
  .btn-s:hover { background:var(--soft); }
  .preview { background:#fff; border:1px solid var(--line); border-radius:12px; padding:12px;
             margin-bottom:12px; height:200px; display:flex; align-items:center;
             justify-content:center; overflow:hidden; }
  #tpreview { height:330px; }
  #pvwrap, #tpvwrap { position:relative; }
  #pv, #tpv { border:0; background:#fff; display:block; }
  .preview .ph { color:var(--sub); font-size:13px; }
  .warn { color:var(--danger); font-size:12.5px; margin-top:8px; }
  .msg { margin-top:10px; font-size:13px; min-height:18px; }
  .msg.ok { color:var(--accent-deep); } .msg.err { color:var(--danger); }
  .mini { display:flex; gap:8px; margin-bottom:10px; }
  .mini .field { flex:1; margin-bottom:0; }
  .mini > button { align-self:flex-end; }
  .nav { justify-self:end; display:flex; gap:8px; align-items:center; }
  .nav .who { color:var(--sub); font-size:12.5px; margin-right:2px; }
  .nav .pill { background:var(--chip); color:var(--accent-deep); border:1px solid var(--line);
               border-radius:999px; padding:7px 15px; font-size:13px; }
  .nav .pill:hover { background:var(--soft); }
  .nav .pill.on { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); }
  .icon-btn { width:34px; height:34px; border-radius:50%; background:var(--chip);
              border:1px solid var(--line); color:var(--sub); display:flex; align-items:center;
              justify-content:center; padding:0; cursor:pointer; text-decoration:none; font-size:15px; }
  .icon-btn:hover { background:var(--soft); color:var(--ink); }
  .tplbar { display:flex; gap:8px; align-items:flex-end; margin-bottom:12px; }
  .tplbar .field { flex:1; margin:0; }
  .trow { border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:14px;
          background:var(--card); }
  .trow.active { border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent); }
  .trow .hd { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
  .trow .hd .nm { flex:1; }
  .trow .hd .act { font-size:11px; color:var(--accent-deep); white-space:nowrap; }
  .btn-x { background:#F7DCD6; color:var(--danger); border:1px solid #E7C4BC; padding:9px 12px; }
  .btn-a { background:var(--soft); color:var(--accent-deep); border:1px solid var(--line); padding:9px 12px; }
  .hint { color:var(--sub); font-size:12px; margin:-4px 0 12px; }
  #view-tpl { grid-template-columns:340px 1fr; }
  @media (max-width:860px){ #view-tpl { grid-template-columns:1fr; } }
</style></head>
<body>
<header>
  <div class="hspacer"></div>
  <div class="logo-c"><span class="logo-main">PRIVAT</span><span class="logo-sub">barcode</span></div>
  <div class="nav">
    <span class="who" id="who"></span>
    <button id="nav-print" class="pill on">🖨 Печать</button>
    <button id="nav-tpl" class="pill">⚙ Шаблоны</button>
    <button id="theme" class="icon-btn" title="Светлая / тёмная тема">🌙</button>
    <a class="icon-btn logout" href="/logout" title="Выйти"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></a>
  </div>
</header>

<div class="wrap" id="view-print">
  <div class="card">
    <h2>Поиск товара</h2>
    <div class="row">
      <input id="q" placeholder="Название, SKU или штрихкод…" autofocus>
      <button class="btn-s" id="go">Найти</button>
    </div>
    <div class="results" id="results"></div>
  </div>

  <div class="card">
    <h2>Ценник</h2>
    <div class="tplbar">
      <div class="field"><label>Шаблон этикетки</label><select id="tpl"></select></div>
    </div>
    <div class="prodinfo" id="prodinfo"></div>
    <div class="preview" id="preview"><div id="pvwrap"><iframe id="pv" title="Ценник"></iframe></div><span class="ph" id="ph">выбери товар слева</span></div>
    <div class="mini">
      <div class="field"><label>Код (SKU)</label><input id="sku" placeholder="—"></div>
      <div class="field"><label>Штрихкод (Barcode)</label><input id="barcode" placeholder="—"></div>
    </div>
    <div class="mini">
      <div class="field"><label>Цена</label><input id="price" placeholder="0"></div>
      <div class="field" style="max-width:90px"><label>Копий</label><input id="copies" type="number" min="1" value="1"></div>
    </div>
    <div class="mini">
      <div class="field"><label>Ширина, мм</label><input id="wmm" type="number" step="0.01"></div>
      <div class="field"><label>Высота, мм</label><input id="hmm" type="number" step="0.01"></div>
      <button class="btn-s" id="savetpl" title="Сохранить размер как шаблон" style="height:40px;white-space:nowrap">💾 В шаблон</button>
    </div>
    <div class="row">
      <button class="btn-p" id="print" style="flex:1">🖨 Печать</button>
      <button class="btn-s" id="dl" title="Скачать .zpl (для прямой отправки на принтер)" style="flex:none">.zpl</button>
    </div>
    <div class="msg" id="msg"></div>
    <div class="warn" id="warn"></div>
  </div>
</div>

<div class="wrap" id="view-tpl" style="display:none;">
  <div class="card">
    <h2>Предпросмотр шаблона</h2>
    <div class="preview" id="tpreview"><div id="tpvwrap"><iframe id="tpv" title="Шаблон"></iframe></div></div>
    <p class="hint">Пример: SKU 0845A, цена 350. Размер меняется вживую при редактировании.</p>
    <button class="btn-p" id="tnew">＋ Новый шаблон</button>
  </div>
  <div class="card">
    <h2>Шаблоны этикеток</h2>
    <p class="hint">Активный шаблон используется печатью из админки Shopify.</p>
    <div id="tpllist"></div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
const PXMM = 96 / 25.4;                 // CSS-пикселей в мм
let CFG = null, TPLS = [], ACTIVE = null, CUR = null, tmr = null;

async function boot() {
  CFG = await (await fetch('/api/config')).json();
  $('#who').textContent = (CFG.user && CFG.user.name) ? CFG.user.name : '';
  await loadTemplates();
}

// ---- шаблоны ----
async function loadTemplates() {
  const d = await (await fetch('/api/templates')).json();
  TPLS = d.templates || []; ACTIVE = d.active;
  // селектор в режиме печати
  const sel = $('#tpl'); sel.innerHTML = '';
  TPLS.forEach(t => {
    const o = document.createElement('option');
    o.value = t.id; o.textContent = t.name + (t.id === ACTIVE ? ' • активный' : '');
    sel.appendChild(o);
  });
  if (!CUR || !TPLS.find(t => t.id === CUR.id)) CUR = TPLS.find(t => t.id === ACTIVE) || TPLS[0];
  if (CUR) { sel.value = CUR.id; applyTemplate(CUR); }
  renderTplList();
}

function applyTemplate(t) {
  CUR = t;
  $('#wmm').value = t.w_mm; $('#hmm').value = t.h_mm;
  render();
}

function scalePreview(pv, wrap, w, h, src) {
  const box = wrap.closest('.preview');
  let availW = 300, availH = 200;
  if (box) { const cs = getComputedStyle(box);
    availW = box.clientWidth  - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2;
    availH = box.clientHeight - parseFloat(cs.paddingTop)  - parseFloat(cs.paddingBottom) - 2; }
  if (!(availW > 40)) availW = 280;   // бокс ещё не в раскладке (скрытая вкладка) — дефолт
  if (!(availH > 40)) availH = 190;
  const pw = w * PXMM, ph = h * PXMM;
  const scale = Math.max(0.5, Math.min(4, availW / pw, availH / ph));  // вписываем по ширине и высоте
  wrap.style.width = (pw * scale) + 'px'; wrap.style.height = (ph * scale) + 'px';
  pv.style.width = pw + 'px'; pv.style.height = ph + 'px';
  pv.style.transform = `scale(${scale})`; pv.style.transformOrigin = 'top left';
  pv.src = src;
}

// ---- режим печати ----
function printUrl(extra) {
  const p = new URLSearchParams(Object.assign({
    sku: $('#sku').value, barcode: $('#barcode').value, price: $('#price').value,
    template: CUR ? CUR.id : '',
    w: +$('#wmm').value || (CUR ? CUR.w_mm : 40), h: +$('#hmm').value || (CUR ? CUR.h_mm : 30),
  }, extra));
  return '/print?' + p.toString();
}

async function search() {
  const q = $('#q').value.trim(); if (!q) return;
  const box = $('#results'); box.innerHTML = '<div class="s" style="color:#9aa3b2">Ищу…</div>';
  const r = await (await fetch('/api/search?q=' + encodeURIComponent(q))).json();
  if (!r.ok) { box.innerHTML = '<div class="warn">' + r.error + '</div>'; return; }
  if (!r.items.length) { box.innerHTML = '<div class="s" style="color:#9aa3b2">Ничего не найдено</div>'; return; }
  box.innerHTML = '';
  r.items.forEach(it => {
    const d = document.createElement('div'); d.className = 'item';
    const st = it.status && it.status !== 'ACTIVE' ? `<span class="badge">${it.status}</span>` : '';
    const cur = CUR ? CUR.currency : '';
    d.innerHTML = `${thumb(it.image)}
      <div class="it-txt">
        <div class="t">${esc(it.title)}${st}</div>
        <div class="s">SKU: ${esc(it.sku)||'—'} · Barcode: ${esc(it.barcode)||'—'} · ${esc(it.price)} ${cur}</div>
      </div>`;
    d.onclick = () => choose(it, d);
    box.appendChild(d);
  });
}

function thumb(url){
  return url ? `<img class="thumb" src="${esc(url)}${url.includes('?')?'&':'?'}width=100" alt="">`
             : `<div class="thumb noimg">нет фото</div>`;
}

function choose(it, el) {
  document.querySelectorAll('.item').forEach(x => x.classList.remove('sel'));
  el.classList.add('sel');
  $('#sku').value = it.sku; $('#barcode').value = it.barcode; $('#price').value = it.price;
  $('#prodinfo').innerHTML = `${thumb(it.image)}<div class="pt">${esc(it.title)}</div>`;
  $('#prodinfo').style.display = 'flex';
  render();
}

function render() {
  const w = +$('#wmm').value || (CUR ? CUR.w_mm : 40), h = +$('#hmm').value || (CUR ? CUR.h_mm : 30);
  $('#ph').style.display = 'none';
  scalePreview($('#pv'), $('#pvwrap'), w, h, printUrl({ copies: 1, auto: 0 }));
  $('#warn').textContent = '';
}
function debounced() { clearTimeout(tmr); tmr = setTimeout(render, 300); }

function doPrint() {
  const old = document.getElementById('pf'); if (old) old.remove();
  const f = document.createElement('iframe');
  f.id = 'pf';
  f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
  f.src = printUrl({ copies: +$('#copies').value || 1, auto: 1 });
  document.body.appendChild(f);
  const m = $('#msg'); m.className = 'msg ok'; m.textContent = '✓ открыл диалог печати браузера';
}

async function download() {
  const body = { sku: $('#sku').value, barcode: $('#barcode').value, price: $('#price').value,
    copies: +$('#copies').value || 1, template: CUR ? CUR.id : '',
    w_mm: +$('#wmm').value, h_mm: +$('#hmm').value, dpi: CFG.dpi };
  const r = await (await fetch('/api/zpl', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)})).json();
  if (!r.ok) return;
  const b = new Blob([r.zpl], {type:'text/plain'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = (($('#sku').value||'label') + '.zpl'); a.click();
}

// сохранить текущий размер (из «Печать») как новый шаблон и выбрать его
async function saveAsTemplate() {
  const w = +$('#wmm').value, h = +$('#hmm').value;
  if (!w || !h) { alert('Укажи ширину и высоту'); return; }
  const name = prompt('Название шаблона:', `${w}×${h} мм`);
  if (!name) return;
  const b = CUR || {};
  const r = await (await fetch('/api/templates/save', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ name, w_mm:w, h_mm:h,
      margin_mm: b.margin_mm ?? 1.5, currency: b.currency ?? 'сом',
      code_label: b.code_label ?? 'Код', price_label: b.price_label ?? 'Цена',
      barcode_source: b.barcode_source ?? 'sku', symbology: b.symbology ?? 'auto' })})).json();
  await loadTemplates();
  if (r.template) { const t = TPLS.find(x => x.id === r.template.id);
    if (t) { CUR = t; $('#tpl').value = t.id; applyTemplate(t); } }
  const m = $('#msg'); m.className = 'msg ok'; m.textContent = '✓ шаблон «' + name + '» сохранён и выбран';
}

// ---- режим шаблонов ----
const SYMS = ['auto','code128','ean13','ean8','upca'];
function opt(v, cur){ return `<option value="${v}"${v===cur?' selected':''}>${v}</option>`; }

function makeRow(t) {
  const row = document.createElement('div');
  row.className = 'trow' + (t.id === ACTIVE ? ' active' : '');
  row.dataset.id = t.id;
  row.innerHTML = `
    <div class="hd">
      <input class="nm f-name" value="${esc(t.name)}">
      <span class="act">${t.id === ACTIVE ? '● активный' : ''}</span>
    </div>
    <div class="mini">
      <div class="field"><label>Ширина, мм</label><input type="number" step="0.01" class="f-w_mm" value="${t.w_mm}"></div>
      <div class="field"><label>Высота, мм</label><input type="number" step="0.01" class="f-h_mm" value="${t.h_mm}"></div>
      <div class="field"><label>Отступ, мм</label><input type="number" step="0.1" class="f-margin_mm" value="${t.margin_mm}"></div>
    </div>
    <div class="mini">
      <div class="field"><label>Валюта</label><input class="f-currency" value="${esc(t.currency)}"></div>
      <div class="field"><label>В штрихкоде</label><select class="f-barcode_source">
        <option value="sku"${t.barcode_source==='sku'?' selected':''}>SKU (артикул)</option>
        <option value="barcode"${t.barcode_source==='barcode'?' selected':''}>поле barcode</option></select></div>
      <div class="field"><label>Тип кода</label><select class="f-symbology">${SYMS.map(s=>opt(s,t.symbology)).join('')}</select></div>
    </div>
    <div class="mini">
      <div class="field"><label>Подпись кода</label><input class="f-code_label" value="${esc(t.code_label)}"></div>
      <div class="field"><label>Подпись цены</label><input class="f-price_label" value="${esc(t.price_label)}"></div>
    </div>
    <div class="row">
      <button class="btn-p f-save" style="flex:1">Сохранить</button>
      <button class="btn-a f-active"${t.id===ACTIVE?' disabled style="opacity:.5"':''}>Сделать активным</button>
      <button class="btn-x f-del">Удалить</button>
    </div>`;
  const vals = () => ({
    id: t.id, name: row.querySelector('.f-name').value,
    w_mm: +row.querySelector('.f-w_mm').value, h_mm: +row.querySelector('.f-h_mm').value,
    margin_mm: +row.querySelector('.f-margin_mm').value,
    currency: row.querySelector('.f-currency').value,
    barcode_source: row.querySelector('.f-barcode_source').value,
    symbology: row.querySelector('.f-symbology').value,
    code_label: row.querySelector('.f-code_label').value,
    price_label: row.querySelector('.f-price_label').value,
  });
  const preview = () => { const v = vals(); previewTpl(v.id, v.w_mm, v.h_mm); };
  row.addEventListener('focusin', preview);
  row.querySelector('.f-w_mm').addEventListener('input', preview);
  row.querySelector('.f-h_mm').addEventListener('input', preview);
  row.querySelector('.f-save').onclick = () => saveTpl(vals());
  row.querySelector('.f-active').onclick = () => setActive(t.id);
  row.querySelector('.f-del').onclick = () => delTpl(t.id, t.name);
  return row;
}

function renderTplList() {
  const box = $('#tpllist'); box.innerHTML = '';
  TPLS.forEach(t => box.appendChild(makeRow(t)));
  const a = TPLS.find(t => t.id === ACTIVE) || TPLS[0];
  if (a) previewTpl(a.id, a.w_mm, a.h_mm);
}

let lastTplPreview = null;
function previewTpl(id, w, h) {
  lastTplPreview = [id, w, h];
  const p = new URLSearchParams({ sku: '0845A', barcode: '0845A', price: '350',
    template: id, w, h, copies: 1, auto: 0 });
  scalePreview($('#tpv'), $('#tpvwrap'), w || 40, h || 30, '/print?' + p.toString());
}

async function saveTpl(v) {
  await fetch('/api/templates/save', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(v)});
  await loadTemplates();
}
async function setActive(id) {
  await fetch('/api/templates/active', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id})});
  await loadTemplates();
}
async function delTpl(id, name) {
  if (!confirm('Удалить шаблон «' + name + '»?')) return;
  await fetch('/api/templates/delete', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id})});
  await loadTemplates();
}
async function newTpl() {
  await saveTpl({ name: 'Новый шаблон', w_mm: 40, h_mm: 30, margin_mm: 1.5,
    currency: 'сом', code_label: 'Код товара', price_label: 'Цена',
    barcode_source: 'sku', symbology: 'auto' });
}

// ---- вкладки ----
function showView(which) {
  $('#view-print').style.display = which === 'print' ? 'grid' : 'none';
  $('#view-tpl').style.display = which === 'tpl' ? 'grid' : 'none';
  $('#nav-print').classList.toggle('on', which === 'print');
  $('#nav-tpl').classList.toggle('on', which === 'tpl');
  // пересчёт превью, когда бокс стал видимым (иначе clientWidth=0 -> мелко)
  if (which === 'tpl' && lastTplPreview) requestAnimationFrame(() => previewTpl(...lastTplPreview));
  if (which === 'print') requestAnimationFrame(render);
}

function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

$('#go').onclick = search;
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') search(); });
let stmr;
$('#q').addEventListener('input', () => { clearTimeout(stmr);
  const q = $('#q').value.trim();
  if (q.length < 2) { $('#results').innerHTML = ''; return; }
  stmr = setTimeout(search, 300); });
$('#tpl').addEventListener('change', e => { const t = TPLS.find(x => x.id === e.target.value); if (t) applyTemplate(t); });
$('#print').onclick = doPrint;
$('#savetpl').onclick = saveAsTemplate;
$('#dl').onclick = download;
$('#tnew').onclick = newTpl;
$('#nav-print').onclick = () => showView('print');
$('#nav-tpl').onclick = () => showView('tpl');
function setTheme(t){ document.documentElement.dataset.theme = t;
  try { localStorage.setItem('theme', t); } catch(e){}
  $('#theme').textContent = t === 'dark' ? '☀️' : '🌙'; }
setTheme(document.documentElement.dataset.theme || 'light');
$('#theme').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
['price','sku','barcode','wmm','hmm'].forEach(id => $('#'+id).addEventListener('input', debounced));
// прокрутка колёсиком над числовым полем не должна менять его значение
document.addEventListener('wheel', () => {
  const a = document.activeElement;
  if (a && a.tagName === 'INPUT' && a.type === 'number') a.blur();
}, { passive: true });
boot();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
