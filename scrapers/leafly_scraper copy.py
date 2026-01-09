"""Leafly scraper - cleaned up version"""

import re
import time
import logging
from typing import List, Dict, Any
from utils.common import (
    setup_session, retry_request, validate_product, 
    filter_by_categories, PRODUCT_TEMPLATE, format_price
)

BRAND_LIST = ["Rhize","RHIZE"]

def scrape_leafly(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scrape Leafly dispensary
    
    Args:
        store_config: Store configuration dict
        
    Returns:
        List of product dictionaries
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    
    try:
        logging.info(f" Starting Leafly scrape for {company_name}")
        
        # Extract slug
        slug = store_config.get("Slug")
        if not slug:
            slug = _extract_slug_from_url(store_config["Store url"])
        
        if not slug:
            raise ValueError("Could not extract slug from Leafly URL")
        
        # Setup session
        session = setup_session()
        
        # Get categories
        categories = store_config.get("Category Names", [])
        categories_normalized = set(c.lower().replace(" ", "").replace("-", "") for c in categories)
        
        # Fetch all products
        products = _fetch_all_leafly_products(session, slug, categories_normalized)
        
        # Validate and filter
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

def _extract_slug_from_url(url: str) -> str:
    """Extract slug from Leafly URL"""
    url_parts = url.split('/')
    if 'e-menu' in url_parts:
        idx = url_parts.index('e-menu')
        if idx + 1 < len(url_parts):
            return url_parts[idx + 1].split('?')[0]
    return ""

def _fetch_all_leafly_products(session, slug: str, categories: set) -> List[Dict[str, Any]]:
    """Fetch all products from Leafly with pagination"""
    products = []
    take, skip = 30, 0
    seen_ids = set()
    
    while True:
        page_products = _fetch_leafly_page(session, slug, take, skip)
        if not page_products:
            break
        
        new_products = []
        for product_data in page_products:
            # Check if seen
            prod_id = str(product_data.get("id") or product_data.get("menuItemId") or "")
            if prod_id in seen_ids:
                continue
            seen_ids.add(prod_id)
            
            # Parse product
            product = _parse_leafly_product(product_data)
            if product:
                new_products.append(product)
        
        products.extend(new_products)
        logging.debug(f"Leafly page {skip//take + 1}: {len(new_products)} new products")
        
        if len(page_products) < take:
            break
        
        skip += take
        time.sleep(0.5)
    
    return products

def _fetch_leafly_page(session, slug: str, take: int, skip: int) -> List[Dict]:
    """Fetch a single page from Leafly API"""
    def fetch():
        url = f"https://consumer-api.leafly.com/api/dispensaries/v2/{slug}/menu_items"
        params = {"take": take, "skip": skip, "filter[brand_name][]": BRAND_LIST, "filter[medical]": "false"}
        
        response = session.get(url, params=params, timeout=20)
        response.raise_for_status()
        
        data = response.json()
        return data.get("menuItems") or data.get("data") or []
    
    return retry_request(fetch)

def _parse_leafly_product(product_data: Dict) -> Dict[str, Any]:
    """Parse Leafly product data"""
    try:
        product = PRODUCT_TEMPLATE.copy()
        
        product["Product name"] = product_data.get("name", "N/A")
        product["Category"] = product_data.get("productCategory", "")
        product["Brand"] = _extract_leafly_brand(product_data)
        product["Price"] = _extract_leafly_price(product_data)
        product["THC"] = _extract_leafly_thc(product_data)
        product["Quantity Available"] = _extract_leafly_quantity(product_data)
        
        return product
        
    except Exception as e:
        logging.error(f"Failed to parse Leafly product: {e}")
        return None

def _extract_leafly_brand(product_data: Dict) -> str:
    """Extract brand from Leafly product"""
    brand = product_data.get("brand", {})
    if isinstance(brand, dict):
        return brand.get("name", "")
    return product_data.get("brandName", "")

def _extract_leafly_price(product_data: Dict) -> Dict[str, str]:
    """Extract price from Leafly product"""
    price = product_data.get("price")
    if price is not None:
        return {"each": format_price(price)}
    return {}

def _extract_leafly_thc(product_data: Dict) -> str:
    """Extract THC from Leafly product"""
    thc = product_data.get("thcContent") or ""
    if thc:
        return f"{thc}%" if not str(thc).endswith('%') else str(thc)
    
    # Try thcContentLabel
    thc_label = product_data.get("thcContentLabel", "")
    if thc_label:
        match = re.match(r"([\d\.]+)\s*([a-zA-Z%]+)", thc_label)
        if match:
            return f"{match.group(1)}{match.group(2)}"
    
    return ""

def _extract_leafly_quantity(product_data: Dict) -> int:
    """Extract quantity from Leafly product"""
    quantity = product_data.get("quantity") or product_data.get("displayQuantity")
    
    if not quantity:
        variants = product_data.get("variants")
        if variants and isinstance(variants, list) and variants:
            quantity = variants[0].get("quantity") or variants[0].get("displayQuantity")
    
    if not quantity:
        # Try to extract from product name
        match = re.search(r"\b(\d+)\s*(?:ct|pk|count|pcs?|each)\b", 
                         product_data.get("name", ""), re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
    
    return int(quantity) if quantity else 0