#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выгрузка всего каталога: товар → название, описание, коллекции, статус."""
import json, time
from shop import gql

Q = """query($c:String){
  products(first:50, after:$c){
    pageInfo{hasNextPage endCursor}
    nodes{
      id title handle status productType vendor tags
      description(truncateAt:1500)
      totalInventory
      collections(first:40){nodes{handle title}}
      variants(first:1){nodes{sku price}}
    }}}"""

out, cur = [], None
while True:
    d = gql(Q, {"c": cur})["products"]
    for n in d["nodes"]:
        out.append({
            "id": n["id"].split("/")[-1],
            "sku": (n["variants"]["nodes"] or [{}])[0].get("sku", ""),
            "title": n["title"],
            "handle": n["handle"],
            "status": n["status"],
            "type": n["productType"],
            "vendor": n["vendor"],
            "tags": n["tags"],
            "qty": n["totalInventory"],
            "desc": n["description"] or "",
            "cols": [c["handle"] for c in n["collections"]["nodes"]],
        })
    if not d["pageInfo"]["hasNextPage"]:
        break
    cur = d["pageInfo"]["endCursor"]
    time.sleep(0.4)

json.dump(out, open("catalog.json", "w"), ensure_ascii=False)
print(len(out), "товаров выгружено")
