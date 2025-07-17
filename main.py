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

# --- Налаштування спільних артикулів для групування за (product_id, колір) ---
BASE_ARTICLE_MAP = {
    # Приклад:
    # (123, "Чорний"): "ZN-507",
    # (123, "Бежевий меланж"): "ZN-508",
    # Додайте свої комбінації тут...
}


def fetch_all_offers():
    offers, page = [], 1
    while True:
        res = requests.get(
            f"{API_URL}/offers",
            headers=HEADERS,
            params={'page': page, 'limit': 50, 'include': 'product'}
        )
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
        res = requests.get(
            f"{API_URL}/offers/stocks",
            headers=HEADERS,
            params={'page': page, 'limit': 50}
        )
        if res.status_code != 200:
            break
        data = res.json().get('data', [])
        for entry in data:
            oid = entry.get('offer_id')
            qty = entry.get('quantity', 0)
            if oid is not None:
                stocks[oid] = qty
        if len(data) < 50:
            break
        page += 1
        time.sleep(0.1)
    return stocks


def fetch_categories():
    cats, page = {}, 1
    while True:
        res = requests.get(
            f"{API_URL}/products/categories",
            headers=HEADERS,
            params={'page': page, 'limit': 50}
        )
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

        # Оригінальний CRM-артикул (повний, із розміром)
        crm_sku = (
            offer.get("sku")
            or offer.get("article")
            or offer.get("vendor_code")
            or offer.get("code")
            or str(oid)
        )

        # Властивості (properties) з KeyCRM
        props = {p["name"]: p["value"] for p in offer.get("properties", [])}
        color = props.get("Колір", "Не вказано")
        size  = props.get("Розмір", "-")

        # Визначаємо групуючий артикул <article>:
        # 1) якщо є у BASE_ARTICLE_MAP → беремо його
        # 2) інакше обрізаємо суфікс "-<розмір>" з crm_sku
        key = (prod.get("id"), color)
        if key in BASE_ARTICLE_MAP:
            grouped_article = BASE_ARTICLE_MAP[key]
        else:
            grouped_article = crm_sku.rsplit("-", 1)[0] if "-" in crm_sku else crm_sku

        # Початкові теги offer
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

        # Вставляємо артикули
        ET.SubElement(offer_el, "article").text    = grouped_article  # однаковий для всіх розмірів одного кольору
        ET.SubElement(offer_el, "vendorCode").text = crm_sku          # реальний арт. з CRM

        # Додаємо параметри без дублів
        seen = set()
        for pname, pvalue in props.items():
            if pname == "Розмір" or pname in seen:
                continue
            ET.SubElement(offer_el, "param", name=pname).text = pvalue
            seen.add(pname)
        # Додаємо параметр Розмір лише один раз
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
