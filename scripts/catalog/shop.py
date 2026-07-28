#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мини-клиент Shopify Admin GraphQL (client credentials из sync/.env)."""
import json, os, sys, urllib.request, urllib.error

ENV = "/Users/dima/Downloads/sync/.env"
for line in open(ENV, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

STORE = os.environ["SHOPIFY_STORE"]
API = os.environ.get("SHOPIFY_API_VERSION", "2024-10")
_tok = ""


def token():
    global _tok
    if _tok:
        return _tok
    req = urllib.request.Request(
        f"https://{STORE}/admin/oauth/access_token",
        data=json.dumps({
            "client_id": os.environ["SHOPIFY_CLIENT_ID"],
            "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"],
            "grant_type": "client_credentials",
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        _tok = json.loads(r.read())["access_token"]
    return _tok


def gql(query, variables=None):
    req = urllib.request.Request(
        f"https://{STORE}/admin/api/{API}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token()},
    )
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:500]}")
    if "errors" in data:
        sys.exit(json.dumps(data["errors"], ensure_ascii=False, indent=2))
    return data["data"]
