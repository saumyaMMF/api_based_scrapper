"""Gramcentral scraper - adapted from your existing code"""

import json
import time
import math
import requests
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from utils.common import (
    validate_product, filter_by_categories, PRODUCT_TEMPLATE, format_price, apply_tax
)

EXPECTED_BRANDS = [
    "RHIZE CANNABIS COMPANY", "RHIZE CANNABIS COMPANY LLC", "RHZIE", "RHIZE"
]

def scrape_gramcentral(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scrape Gramcentral dispensary
    
    Args:
        store_config: Store configuration dict
        
    Returns:
        List of product dictionaries
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    
    try:
        logging.info(f" Starting Gramcentral scrape for {company_name}")
        
        # Check required fields
        required_fields = ["Company ID", "Store ID", "Session ID"]
        for field in required_fields:
            if not store_config.get(field):
                raise ValueError(f"Missing required field: {field}")
        
        company_id = store_config["Company ID"]
        store_id = store_config["Store ID"]
        session_id = store_config["Session ID"]
        categories = store_config.get("Category Names", [])
        
        # Normalize categories
        category_names = set(_normalize_category(c) for c in categories)
        
        # Setup session
        headers = _make_gramcentral_headers(company_id, store_id, session_id)
        api_url = f"https://api.mosaic.green/v1.0/cms/{company_id}/{store_id}/product-list"
        
        # Fetch all products
        products = _fetch_all_gramcentral_products(api_url, headers, store_id, company_id, category_names)
        
        # ⬇️ NEW: force every product's Price to be after-tax using website_list.json flags
        for p in products:
            p["Price"] = apply_tax(p.get("Price") or {}, store_config)
            
        # Validate products
        valid_products = []
        for product in products:
            if validate_product(product) and filter_by_categories(product["Category"], categories):
                valid_products.append(product)
        
        duration = time.time() - start_time
        logging.info(f" {company_name}: {len(valid_products)} products in {duration:.2f}s")
        
        return valid_products
        
    except Exception as e:
        logging.error(f" {company_name}: {e}")
        return []

def _normalize_category(category: str) -> str:
    """Normalize category name"""
    return (category or "").replace(" ", "").replace("-", "").lower()

def _make_gramcentral_headers(company_id: str, store_id: str, session_id: str) -> Dict[str, str]:
    """Create headers for Gramcentral API"""
    mp_meta_dict = {
        "browser": "Chrome 138.0.0.0",
        "platform": "undefined",
        "os": "Windows 10",
        "engine": "Blink 138.0.0.0",
        "brand": "undefined",
        "vendor": "undefined",
        "local_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://shop.gramcentral.com",
        "referer": "https://shop.gramcentral.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "mp-meta": f"{company_id},{store_id},{session_id},WEB,Asia/Calcutta,{json.dumps(mp_meta_dict)}"
    }

def _fetch_all_gramcentral_products(api_url: str, headers: Dict[str, str], 
                                   store_id: str, company_id: str, 
                                   category_names: set) -> List[Dict[str, Any]]:
    """Fetch all products from Gramcentral"""
    all_products = []
    page = 1
    limit = 12
    total_pages = None
    
    while True:
        logging.debug(f"Fetching Gramcentral page {page}...")
        
        payload = {
            "store_id": store_id,
            "company_id": company_id,
            "category_type": "POS_CATEGORY",
            "current_page": page,
            "limit": limit,
            "offset": None,
            "filter_data": {"brand": EXPECTED_BRANDS},
            "has_promo_products": False,
            "patient_type": "RECREATIONAL",
            "search": "",
            "sort_type": "NAME_ASC"
        }
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            # print(response)
            response.raise_for_status()
            data = response.json()
            
            if total_pages is None:
                total_records = data.get("total_records", 0)
                total_pages = math.ceil(total_records / limit)
                logging.info(f"Gramcentral total products: {total_records}, pages: {total_pages}")
            
            products = data.get("products", [])
            if not products:
                break
            print(products)
            # Parse products
            for product_data in products:
                try:
                    parsed = _parse_gramcentral_product(product_data)
                    if parsed:
                        all_products.append(parsed)
                except Exception as e:
                    logging.error(f"Error parsing Gramcentral product: {e}")
            
            if page >= total_pages:
                break
            page += 1
            
        except Exception as e:
            logging.error(f"Error fetching Gramcentral page {page}: {e}")
            break
    
    return all_products

def _parse_gramcentral_product(product_data: Dict) -> Dict[str, Any]:
    """Parse Gramcentral product data"""
    product = PRODUCT_TEMPLATE.copy()
    product["Product name"] = (product_data.get("name") or "").strip()
    product["Brand"] = (product_data.get("brand_name") or "").strip()
    product["Category"] = (product_data.get("category_slug") or "").strip()
    
    # Get variant info (price and quantity)
    variants = product_data.get("product_variants", [])
    if variants:
        variant = variants[0]
        unit_label = (variant.get("label") or variant.get("product_name") or "").strip()

        # Price with $ sign
        price_val = variant.get("price", 0.0)
        product["Price"] = {unit_label: f"${price_val:.2f}"}

        # Discount Price (after-tax / discount)
        discounted_val = variant.get("discounted_price") or variant.get("price", 0.0)
        product["Discount Price"] = {unit_label: f"${discounted_val:.2f}"}

        # Try to fetch 'quantity' from inventory_batches
        inventory_batches = variant.get("inventory_batches", [])
        if inventory_batches:
            # Get quantity from the first inventory batch
            product["Quantity Available"] = inventory_batches[0].get("quantity")
    
    # Get THC info
    thc_percent = ""
    thc_unit = ""
    for attr in product_data.get("attributes", []):
        if attr.get("type") == "THC_PERCENTAGE":
            thc_percent = attr.get("value", "").replace("%", "")
            thc_unit = "%"
            break
        elif attr.get("type") == "THC" and not thc_percent:
            thc_percent = attr.get("value", "").replace("MG", "").strip()
            thc_unit = "MG"
    
    if thc_percent:
        product["THC"] = f"{thc_percent}{thc_unit}"
    
    return product