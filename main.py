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

# --- Налаштування базових артикулів для групування ---
# Ключ: (product_id, колір) → значення: базовий артикул для всіх розмірів
BASE_ARTICLE_MAP = {
    # наприклад:
    # (123, "Чорний"): "ZN-507",
    # (123, "Синій"):  "ZN-508",
    # (456, "Червоний"): "ZN-901",
    # додайте свої комбінації...
}


def fetch_all_offers():
    offers = []
    page = 1
    per_page = 50
    while True:
        res = requests.get(
            f"{API_URL}/offers",
            headers=HEADERS,
            params={'page': page, 'limit': per_page, 'include': 'product'}
        )
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        if not data:
            break
        offers.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return offers


def fetch_offer_stock():
    stocks = {}
    page = 1
    per_page = 50
    while True:
        res = requests.get(
            f"{API_URL}/offers/stocks",
            headers=HEADERS,
            params={'page': page, 'limit': per_page}
        )
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
        res = requests.get(
            f"{API_URL}/products/categories",
            headers=HEADERS,
            params={'page': page, 'limit': per_page}
        )
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        for cat in data:
            cid = cat.get('id')
            name = cat.get('name')
            if cid and name:
                categories[cid] = name
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

    # Валюти
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
        oid = offer.get("id")
        qty = stocks.get(oid, offer.get("quantity", 0))
        prod = offer.get("product", {})
        attrs = offer.get("attributes", {})

        # Збираємо властивості в словник
        props = {p["name"]: p["value"] for p in offer.get("properties", [])}

        # Визначаємо базовий артикул по мапі або fallback
        key = (prod.get("id"), props.get("Колір"))
        base_article = BASE_ARTICLE_MAP.get(key, f"ZNM-{prod.get('id')}")

        # Основні поля
        name = prod.get("name") or offer.get("name") or f"Offer {oid}"
        desc = prod.get("description") or offer.get("description") or "Опис відсутній"
        price = offer.get("price", 0)
        currency = attrs.get("currency_code", "UAH")
        vendor = prod.get("vendor") or prod.get("vendor_name") or "Znana Mama"
        cat_id = prod.get("category_id")

        # Формуємо елемент offer
        offer_el = ET.SubElement(
            offers_el,
            "offer",
            id=str(oid),
            available="true" if qty > 0 else "false"
        )
        ET.SubElement(offer_el, "name").text = name
        ET.SubElement(offer_el, "price").text = str(price)
        ET.SubElement(offer_el, "currencyId").text = currency
        ET.SubElement(offer_el, "stock_quantity").text = str(qty)

        if cat_id and cat_id in categories:
            ET.SubElement(offer_el, "categoryId").text = str(cat_id)
        if thumb := offer.get("thumbnail_url"):
            ET.SubElement(offer_el, "picture").text = thumb

        ET.SubElement(offer_el, "description").text = desc
        ET.SubElement(offer_el, "vendor").text = vendor
        ET.SubElement(offer_el, "article").text = str(base_article)

        # Всі інші параметри
        for pname, pvalue in props.items():
            ET.SubElement(offer_el, "param", name=pname).text = pvalue

        # Окремо параметр "Розмір" для впевненості
        size = props.get("Розмір", "-")
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
