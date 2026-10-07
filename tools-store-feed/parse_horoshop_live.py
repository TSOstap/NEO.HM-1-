#!/usr/bin/env python3
import csv, os, re, requests
import xml.etree.ElementTree as ET
from collections import Counter

URL = "https://tools-store.com.ua/content/export/23537d44bee70bc30b50e6bc763e3a60.xml"
OUT = "tools-store-feed/horoshop-live.csv"
DIAG = "tools-store-feed/horoshop-live-diagnostic.txt"

def local(tag):
    return tag.split("}")[-1] if "}" in tag else tag

def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())

def status_from_value(v):
    t = norm(v).lower()
    if not t:
        return ""
    if t in {"1","true","yes","y","так","available","in stock","instock","в наявності","есть","є"}:
        return "В наявності"
    if t in {"0","false","no","n","ні","not available","out of stock","outofstock","немає в наявності","нет","немає"}:
        return "Немає в наявності"
    if "немає" in t or "нет в наличии" in t or "out of stock" in t:
        return "Немає в наявності"
    if "в наявності" in t or "в наличии" in t or "in stock" in t:
        return "В наявності"
    try:
        return "В наявності" if float(t.replace(",", ".")) > 0 else "Немає в наявності"
    except:
        return ""

def first_text(elem, names):
    wanted={n.lower() for n in names}
    for ch in elem.iter():
        if local(ch.tag).lower() in wanted:
            txt=norm(ch.text)
            if txt:
                return txt
    return ""

def find_vendor_code(elem):
    return first_text(elem, ["vendorCode","article","sku","code","articul","article_for_display"])

def find_name(elem):
    return first_text(elem, ["name","title","model"])

def find_brand(elem):
    return first_text(elem, ["vendor","brand","manufacturer"])

def find_status(elem):
    for k in ["available","availability","presence","in_stock","stock"]:
        if k in elem.attrib:
            s=status_from_value(elem.attrib.get(k))
            if s:
                return s
    for nm in ["presence","availability","available","status","in_stock","stock_status"]:
        v=first_text(elem,[nm])
        s=status_from_value(v)
        if s:
            return s
    for nm in ["quantity","stock_quantity","qty","stock","amount","count"]:
        v=first_text(elem,[nm])
        s=status_from_value(v)
        if s:
            return s
    if local(elem.tag).lower() == "offer":
        return "Немає в наявності"
    return ""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
r=requests.get(URL, timeout=180)
r.raise_for_status()
data=r.content

root=ET.fromstring(data)
counts=Counter(local(e.tag) for e in root.iter())

candidates=[]
for e in root.iter():
    if local(e.tag).lower() == "offer":
        candidates.append(e)

rows=[]
missing_vendor=0
missing_status=0
missing_offer_id=0

for e in candidates:
    vendor_code=find_vendor_code(e)
    name=find_name(e)
    brand=find_brand(e)
    status=find_status(e)
    offer_id=norm(e.attrib.get("id",""))

    if not vendor_code:
        missing_vendor += 1
        continue
    if not status:
        missing_status += 1
        continue
    if not offer_id:
        missing_offer_id += 1

    rows.append((vendor_code,status,name,offer_id,brand))

# dedupe by vendor code, last occurrence wins
d={}
for vendor_code,status,name,offer_id,brand in rows:
    d[vendor_code]=(status,name,offer_id,brand)

rows=[(a,v[0],v[1],v[2],v[3]) for a,v in d.items()]
rows.sort(key=lambda x:x[0])

with open(OUT,"w",encoding="utf-8-sig",newline="") as f:
    w=csv.writer(f)
    w.writerow([
        "Артикул",
        "Наявність",
        "Назва",
        "offer_id",
        "Бренд"
    ])
    w.writerows(rows)

with open(DIAG,"w",encoding="utf-8") as f:
    f.write(f"HTTP: {r.status_code}\n")
    f.write(f"Bytes: {len(data)}\n")
    f.write(f"Root: {local(root.tag)}\n")
    f.write(f"Candidates: {len(candidates)}\n")
    f.write(f"Rows written: {len(rows)}\n")
    f.write(f"Missing vendor code: {missing_vendor}\n")
    f.write(f"Missing status: {missing_status}\n")
    f.write(f"Missing offer id: {missing_offer_id}\n")
    f.write("Top tags:\n")
    for tag,c in counts.most_common(40):
        f.write(f"{tag}: {c}\n")
    f.write("\nFirst candidate preview:\n")
    if candidates:
        txt=ET.tostring(candidates[0],encoding="unicode")
        f.write(txt[:8000])

if len(rows) < 100:
    print(open(DIAG,encoding="utf-8").read())
    raise SystemExit("Too few parsed rows; refusing to publish feed")

print(f"Wrote {len(rows)} rows")
