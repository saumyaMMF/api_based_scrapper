"""MothaPlant scraper - adapted from your existing code"""

import time
import requests
import logging
from typing import List, Dict, Any
from utils.common import (
    validate_product, filter_by_categories, PRODUCT_TEMPLATE, format_price, apply_tax  
)

def scrape_mothaplant(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scrape MothaPlant dispensary using Dispense API
    
    Args:
        store_config: Store configuration dict
        
    Returns:
        List of product dictionaries
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    
    try:
        logging.info(f" Starting MothaPlant scrape for {company_name}")
        
        venue_id = store_config.get("venue_id", "a6b0c909cbf495bb")
        api_limit = store_config.get("api_limit", 20)
        search_term = store_config.get("search_term", "rhize")
        # Setup headers
        api_headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "api-key": "49dac8e0-7743-11e9-8e3f-a5601eb2e936",
            "Origin": "https://mothaplant.com",
            "Referer": "https://mothaplant.com/",
            "User-Agent": "Mozilla/5.0",
            "x-prospect-token": "0cd988bc-167b-403a-82b3-a4a0d4f04579"
        }
        

        products = _fetch_mothaplant_category(venue_id, api_headers, api_limit, search_term)
        # ⬇️ NEW: make every product's Price after-tax using website_list.json flags
        for p in products:
            p["Price"] = apply_tax(p.get("Price") or {}, store_config)

        # Validate products
        valid_products = []
        for product in products:
            if validate_product(product):
                valid_products.append(product)
        
        duration = time.time() - start_time
        logging.info(f" {company_name}: {len(valid_products)} products in {duration:.2f}s")
        
        return valid_products
        
    except Exception as e:
        logging.error(f" {company_name}: {e}")
        return []

def _fetch_mothaplant_category(venue_id: str,
                             headers: Dict[str, str], api_limit: int, search_term: str) -> List[Dict[str, Any]]:
    """Fetch products for a specific category"""
    all_products = []
    seen_ids = set()
    skip = 0
    
    while True:
        params = {
            "limit": api_limit,
            "skip": skip,
            "search": search_term,
            "active": "true",
            "quantityMin": 1,
            "group": "true",
            "enable": "true",
            "orderPickUpType": "IN_STORE",
            "trackSearch": "true"
        }
        
        url = f"https://api.dispenseapp.com/v1/venues/{venue_id}/products"

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            response.raise_for_status()
            
            page = response.json()
            products = page.get("data", [])
            
            if not products:
                break
            
            new_products = 0

            for product_data in products:
                product_id = product_data.get("id")
                if product_id not in seen_ids:
                    seen_ids.add(product_id)
                    
                    product = _parse_mothaplant_product(product_data)
                    if product:
                        all_products.append(product)
                        new_products += 1
            
            logging.debug(f"MothaPlant skip={skip}: {new_products} new products")
            
            if new_products == 0 or len(products) < api_limit:
                break
            
            skip += api_limit
            time.sleep(0.5)
            
        except Exception as e:
            logging.error(f"Error fetching MothaPlant: {e}")
            break
    
    return all_products

def _parse_mothaplant_product(product_data: Dict) -> Dict[str, Any]:
    """Parse MothaPlant product data"""
    product = PRODUCT_TEMPLATE.copy()
    
    product["Product name"] = product_data.get("name", "")
    product["Brand"] = product_data.get("brand", {}).get("name", "")
    product["Category"] = product_data.get("productCategoryName", "")
    product["Quantity Available"] = product_data.get("quantityTotal", "")
    
    # Weight and price
    weight = product_data.get("weightFormatted", "")
    price = product_data.get("price")
    
    if weight and price:
        product["Price"] = {weight: format_price(price)}
    elif price:
        product["Price"] = {"each": format_price(price)}
    
    # THC content
    labs = product_data.get("labs", {})
    thc = labs.get("thc", "")
    thc_unit = labs.get("thcContentUnit", "")
    
    if thc:
        product["THC"] = f"{thc}{thc_unit}" if thc_unit else str(thc)
    
    return product