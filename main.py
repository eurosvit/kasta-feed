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
    offers = []
    page = 1
    per_page = 50
    while True:
        res = requests.get(f"{API_URL}/offers", headers=HEADERS, params={'page': page, 'limit': per_page, 'include': 'product'})
        if res.status_code != 200:
            break
        data = res.json()
        page_offers = data.get('data', [])
        if not page_offers:
            break
        offers.extend(page_offers)
        if len(page_offers) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return offers

def fetch_offer_stock():
    stocks = {}
    page = 1
    per_page = 50
    while True:
        res = requests.get(f"{API_URL}/offers/stocks", headers=HEADERS, params={'page': page, 'limit': per_page})
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        for entry in data:
            offer_id = entry.get('offer_id')
            quantity = entry.get('quantity', 0)
            if offer_id is not None:
                stocks[offer_id] = quantity
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return stocks

def fetch_categories():
    categories = {}
    page = 1
    per_page = 50
    while True:
        res = requests.get(f"{API_URL}/products/categories", headers=HEADERS, params={'page': page, 'limit': per_page})
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        for cat in data:
            cat_id = cat.get('id')
            name = cat.get('name')
            if cat_id and name:
                categories[cat_id] = name
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return categories

def generate_xml():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    root = ET.Element("yml_catalog", date=now)
    shop = ET.SubElement(root, "shop")
    ET.SubElement(shop, "name").text = "Znana Mama"
    ET.SubElement(shop, "company").text = "Znana Mama"
    ET.SubElement(shop, "url").text = "https://yourshop.ua"

    ET.SubElement(ET.SubElement(shop, "currencies"), "currency", id="UAH", rate="1")

    categories_dict = fetch_categories()
    categories_el = ET.SubElement(shop, "categories")
    for cat_id, name in categories_dict.items():
        ET.SubElement(categories_el, "category", id=str(cat_id)).text = name

    offers_el = ET.SubElement(shop, "offers")
    offers = fetch_all_offers()
    stocks = fetch_offer_stock()

    for offer in offers:
        offer_id = offer.get("id")
        quantity = stocks.get(offer_id, offer.get("quantity", 0))
        offer_attr = offer.get("attributes", {})
        product_data = offer.get("product", {})

        name = product_data.get("name") or offer.get("name") or f"Offer {offer_id}"
        description = product_data.get("description") or offer.get("description") or "Опис відсутній"
        price = offer.get("price", 0)
        currency = offer_attr.get("currency_code", "UAH")
        vendor = product_data.get("vendor") or product_data.get("vendor_name") or "Znana Mama"
        category_id = product_data.get("category_id")

        # Base article for the product card
        base_article = product_data.get("article") or offer.get("article") or f"ZNM-{offer_id}"

        offer_el = ET.SubElement(offers_el, "offer", id=str(offer_id), available="true" if quantity > 0 else "false")
        ET.SubElement(offer_el, "name").text = name
        ET.SubElement(offer_el, "price").text = str(price)
        ET.SubElement(offer_el, "currencyId").text = currency
        ET.SubElement(offer_el, "stock_quantity").text = str(quantity)

        if category_id and category_id in categories_dict:
            ET.SubElement(offer_el, "categoryId").text = str(category_id)

        if offer.get("thumbnail_url"):
            ET.SubElement(offer_el, "picture").text = offer.get("thumbnail_url")

        ET.SubElement(offer_el, "description").text = description
        ET.SubElement(offer_el, "vendor").text = vendor
        ET.SubElement(offer_el, "article").text = str(base_article)

        for prop in offer.get("properties", []):
            pname = prop.get("name")
            pvalue = prop.get("value")
            if pname and pvalue:
                ET.SubElement(offer_el, "param", name=pname).text = pvalue
                if pname.lower() == "розмір":
                    ET.SubElement(offer_el, "param", name="Розмір").text = pvalue

    return ET.tostring(root, encoding="utf-8")

@app.route("/export/kasta.xml")
def kasta_feed():
    try:
        xml_data = generate_xml()
        return Response(xml_data, mimetype="application/xml")
    except Exception as e:
        logger.exception("Feed generation failed")
        return Response("Error generating feed", status=500)

if __name__ == "__main__":
    app.run(debug=True)
