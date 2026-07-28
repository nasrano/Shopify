#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка «название товара против его категории».

Для каждой группы родственных подкатегорий заданы признаки, которые
надёжно читаются ИЗ НАЗВАНИЯ товара. Дальше два вопроса:
  [чужой]  товар лежит в A, название говорит «это B», и про A в названии молчок
  [нет-в]  название говорит «это B», товар в родителе, но в B его нет
"""
import json, re, sys
from collections import defaultdict

cat = json.load(open("catalog.json"))
in_col = defaultdict(list)
for p in cat:
    for h in p["cols"]:
        in_col[h].append(p)

# группа: родитель -> {подкатегория: признак в названии}
GROUPS = {
    "smazki": {
        "obychnyie": r"на водной основе|водной основ",
        "na-silikonovoi-osnovie": r"силиконов",
        "anal-nyie": r"анальн",
        "vozbuzhdaiushchiie": r"возбужда|разогрев|согрева|термочувств|ментол",
        "prodlievaiushchiie": r"продлева|пролонг|анестет|задержк",
        "s-ghialuronovoi-kislotoi": r"гиалурон",
        "fruktovyie-siedobnyie": r"вкус|клубни|вишн|банан|шоколад|манго|дын|персик|яблок|фрукт",
    },
    "prieziki": {
        "c-aniestietikom": r"анестет|пролонг|продлева|продлевающ",
        "c-usikami-i-riebrami": r"усик|ребр|точечн|шип|рельеф|спиральн",
        "co-vkusami": r"вкус|аромат|клубни|банан|шоколад|вишн|мят|дын|фрукт",
        "xxl": r"\bxxl\b|\bxl\b|больш",
        "oral-nyie": r"орал|минет",
        "poliurietanovyie": r"полиуретан|безлатекс|без латекс",
        "ul-tratonkiie": r"ультратонк|супертонк|тонк",
        "tsvietnyie": r"цветн|разноцвет",
        "prostyie": r"классическ|гладк",
    },
    "vibratory": {
        "vakuumno-volnovyie": r"вакуум|волнов|бесконтакт",
        "vibrotrusiki": r"трусик|бабочк",
        "vibroiaitsa": r"яйц|виброяйц",
        "dvoinyie": r"двойн|кролик|rabbit",
        "dlia-klitora": r"клитор",
        "tochka-g": r"точк[аиуе] ?g|g-?spot|точки ?g",
        "mini-vibratory": r"\bмини|миниатюрн",
        "tochiechnyie": r"точечн",
    },
    "fallosy": {
        "biez-vibratsii": r"без вибрац",
        "s-vibratsiiami": r"вибрац|вибро|вибрир",
        "s-vrashchieniiem": r"вращ|ротац",
        "tolkaiushchiie": r"толка|фрикц|поступател",
        "bol-shiie": r"больш|огромн|макси",
        "fentazi": r"фэнтез|фентез|дракон|щупальц|монстр|фантаз",
        "fallosy-mini": r"\bмини|маленьк",
        "fallosy-iz-kibierkozhi": r"киберкож",
    },
    "nasadki-na-chlien": {
        "vibriruiushchiie": r"вибра|вибро|вибрир",
        "dvoinoie-proniknovieniie": r"двойного проникн|двойн",
        "iz-kibierkozhi": r"киберкож",
        "s-udlinieniiem": r"удлин|увеличен|\+ ?\d",
        "stimuliruiushchiie": r"стимулир|усик|шип|рельеф|точечн|ребр|нарост|бугорк",
    },
    "masturbatory": {
        "vaghiny": r"вагин|киск",
        "rotik": r"\bрот|ротик|минет|орал",
        "anusy-i-popy": r"анус|попк|ягодиц|\bпопа",
        "iaitsa-tiengha": r"яйц|tenga|тенга",
        "avtomatichieskiie": r"автомат",
        "s-vibratsiiei": r"вибра|вибро|вибрир",
        "sieks-kukly": r"кукл",
        "tielo-s-ghrud-iu": r"груд|торс",
        "urietral-nyie": r"уретр",
        "mul-tifunktsional-nyie": r"мультифункц|2 в 1|3 в 1",
    },
    "dlya-anala": {
        "anal-nyie-busy": r"бус|шарик|цепочк|ёлочк|елочк",
        "anal-nyie-probki": r"пробк|\bplug",
        "probki-s-khvostikom": r"хвост",
        "massazhiery-prostaty": r"простат",
        "rasshiritieli": r"расширит|растяг",
        "anal-nyie-dildo": r"дилдо|фаллос",
        "anal-nyie-vibratory": r"вибра|вибро|вибрир",
    },
    "bdsm": {
        "naruchniki": r"наручник|фиксатор|манжет|наножник|оков",
        "kliapy": r"кляп|роторасшир",
        "maski": r"маск|повязк на глаз|шлем|капюшон",
        "plietki": r"плет|плёт|стек\b|флоггер|хлыст|шлёпалк|шлепалк|паддл|розг",
        "oshieiniki-i-povodki": r"ошейник|поводок",
        "zazhimy-dlia-soskov": r"зажим|прищеп|на соск",
        "vieriovki-dlia-sviazyvaniia": r"верёвк|веревк|шибари|бондажн|лента для|канат",
        "sviechi": r"свеч|воск",
        "poiasa-viernosti": r"пояс верност|клетк|целомудр",
        "bdsm-kostiumy": r"костюм|комбинезон",
        "bdsm-nabory": r"набор|комплект",
        "stimuliatory-bol-iu": r"игл|колес|вартенберг|щипц",
    },
    "ero-biel-io": {
        "bodi": r"\bбоди\b",
        "kolghotki": r"колготк",
        "kombiniezony": r"комбинезон|катсьют|бодистокинг|комбидресс",
        "kompliekty-biel-ia": r"комплект|набор",
        "muzhskoie-biel-ie": r"мужск",
        "obodki-s-ushkami": r"ободок|ушк|рожк",
        "pien-iuary": r"пеньюар|сорочк|халат|неглиже|бэбидолл|беби-долл",
        "pierchatki": r"перчатк|митенк",
        "rolievyie-kostiumy": r"костюм|наряд",
        "trusiki-stringhi": r"стринг|танга",
        "chulki-i-poiasa-k-nim": r"чулк|подвязк|гартер|гольф",
        "trusiki-s-dostupom": r"доступ|открыт|разрез|crotchless|без ластовиц",
    },
    "strapony": {
        "biezriemnievyie": r"безремнев|без ремн|strapless",
        "dvoinyie-strapony": r"двойн|двусторон|двухсторон",
        "s-riemniami": r"ремн|трусик|harness|креплен",
        "strapony-na-chlien": r"на член|полый|полая|насадк",
    },
    "vozbuditieli": {
        "poppiersy": r"поппер|popper",
        "dlia-zhienshchin": r"для женщин|женск",
        "dlia-muzhchin": r"для мужчин|мужск",
    },
    "uvielichieniie-chliena": {
        "kriema-i-ghieli": r"крем|гель|мазь|бальзам|спрей",
        "pompy-dlia-chliena": r"помп|вакуум",
        "ekstiendiery": r"экстендер|extender",
    },
}

alien, missing = [], []
for parent, sigs in GROUPS.items():
    rx = {k: re.compile(v, re.I) for k, v in sigs.items()}
    for p in in_col.get(parent, []):
        t = p["title"]
        says = {k for k, r in rx.items() if r.search(t)}
        has = {k for k in sigs if k in p["cols"]}
        for c in has:
            others = says - {c}
            if c not in says and others:
                alien.append((parent, c, sorted(others), p))
        for s in says - has:
            missing.append((parent, s, p))

what = sys.argv[1] if len(sys.argv) > 1 else "all"
if what in ("all", "alien"):
    print("#" * 70)
    print("# ЧУЖОЙ В КАТЕГОРИИ: лежит в A, а название говорит про B")
    print("#" * 70)
    g = defaultdict(list)
    for parent, c, others, p in alien:
        g[(parent, c)].append((others, p))
    for (parent, c), rows in sorted(g.items()):
        print(f"\n— [{parent} > {c}] {len(rows)}")
        for others, p in rows:
            st = "" if p["status"] == "ACTIVE" else f" ({p['status']})"
            print(f"    {(p['sku'] or '—'):7s} {p['title'][:66]:66s} → {','.join(others)}{st}")

if what in ("all", "missing"):
    print("\n" + "#" * 70)
    print("# НЕ ПОЛОЖИЛИ: название говорит про B, товар в родителе, а в B его нет")
    print("#" * 70)
    g = defaultdict(list)
    for parent, s, p in missing:
        g[(parent, s)].append(p)
    for (parent, s), rows in sorted(g.items(), key=lambda x: -len(x[1])):
        print(f"\n— [{parent} → {s}] {len(rows)}")
        for p in rows:
            st = "" if p["status"] == "ACTIVE" else f" ({p['status']})"
            print(f"    {(p['sku'] or '—'):7s} {p['title'][:70]}{st}")
