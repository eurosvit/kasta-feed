from flask import Flask, Response
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import time

app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Env config
API_URL = os.getenv('KEYCRM_API_URL', 'https://openapi.keycrm.app/v1')
API_KEY = os.getenv('KEYCRM_API_KEY')
HEADERS = {'Authorization': f'Bearer {API_KEY}'}

def fetch_all_offers():
    offers, page = [], 1
    while True:
        res = requests.get(f"{API_URL}/offers",
                           headers=HEADERS,
                           params={'page': page, 'limit': 50, 'include': 'product'})
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        if not data:
            break
        offers.extend(data)
        if len(data) < 50:
            break
        page += 1
        time.sleep(0.1)
    return offers

def fetch_offer_stock():
    stocks, page = {}, 1
    while True:
        res = requests.get(f"{API_URL}/offers/stocks",
                           headers=HEADERS,
                           params={'page': page, 'limit': 50})
        if res.status_code != 200:
            break
        entries = res.json().get('data', [])
        for e in entries:
            oid = e.get('offer_id')
            qty = e.get('quantity', 0)
            if oid is not None:
                stocks[oid] = qty
        if len(entries) < 50:
            break
        page += 1
        time.sleep(0.1)
    return stocks

def fetch_categories():
    cats, page = {}, 1
    while True:
        res = requests.get(f"{API_URL}/products/categories",
                           headers=HEADERS,
                           params={'page': page, 'limit': 50})
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        for c in data:
            cid, name = c.get('id'), c.get('name')
            if cid and name:
                cats[cid] = name
        if len(data) < 50:
            break
        page += 1
        time.sleep(0.1)
    return cats

def generate_xml():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    root = ET.Element("yml_catalog", date=now)
    shop = ET.SubElement(root, "shop")
    ET.SubElement(shop, "name").text = "Znana Mama"
    ET.SubElement(shop, "company").text = "Znana Mama"
    ET.SubElement(shop, "url").text = "https://yourshop.ua"

    ET.SubElement(ET.SubElement(shop, "currencies"), "currency", id="UAH", rate="1")

    # Категорії
    categories = fetch_categories()
    cats_el = ET.SubElement(shop, "categories")
    for cid, cname in categories.items():
        ET.SubElement(cats_el, "category", id=str(cid)).text = cname

    # Оферти
    offers_el = ET.SubElement(shop, "offers")
    offers = fetch_all_offers()
    stocks = fetch_offer_stock()

    for offer in offers:
        oid = offer["id"]
        qty = stocks.get(oid, offer.get("quantity", 0))
        prod = offer.get("product", {})
        attrs = offer.get("attributes", {})

        # Повний CRM-артикул (для vendorCode)
        crm_sku = (
            offer.get("sku")
            or offer.get("article")
            or offer.get("vendor_code")
            or offer.get("code")
            or str(oid)
        )

        # Збираємо властивості
        props = {p["name"]: p["value"] for p in offer.get("properties", [])}
        color = props.get("Колір", "Не вказано")
        size  = props.get("Розмір", "-")

        # Групуючий артикул: ZN-<product_id>
        grouped_article = f"ZN-{prod.get('id')}"

        # Формуємо offer
        offer_el = ET.SubElement(
            offers_el, "offer",
            id=str(oid),
            available="true" if qty > 0 else "false"
        )
        ET.SubElement(offer_el, "name").text        = prod.get("name") or offer.get("name") or f"Offer {oid}"
        ET.SubElement(offer_el, "price").text       = str(offer.get("price", 0))
        ET.SubElement(offer_el, "currencyId").text  = attrs.get("currency_code", "UAH")
        ET.SubElement(offer_el, "stock_quantity").text = str(qty)
        if cat_id := prod.get("category_id"):
            ET.SubElement(offer_el, "categoryId").text = str(cat_id)
        if thumb := offer.get("thumbnail_url"):
            ET.SubElement(offer_el, "picture").text = thumb
        ET.SubElement(offer_el, "description").text = prod.get("description") or offer.get("description") or "Опис відсутній"
        ET.SubElement(offer_el, "vendor").text      = prod.get("vendor") or prod.get("vendor_name") or "Znana Mama"

        # Артикул і vendorCode
        ET.SubElement(offer_el, "article").text    = grouped_article
        ET.SubElement(offer_el, "vendorCode").text = crm_sku

        # Параметри без дублів
        seen = set()
        for pname, pvalue in props.items():
            if pname == "Розмір" or pname in seen:
                continue
            ET.SubElement(offer_el, "param", name=pname).text = pvalue
            seen.add(pname)
        # І один параметр Розмір
        ET.SubElement(offer_el, "param", name="Розмір").text = size

    return ET.tostring(root, encoding="utf-8")

@app.route("/export/kasta.xml")
def kasta_feed():
    try:
        xml_data = generate_xml()
        return Response(xml_data, mimetype="application/xml")
    except Exception:
        logger.exception("Feed generation failed")
        return Response("Error generating feed", status=500)

if __name__ == "__main__":
    app.run(debug=True)
