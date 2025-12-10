"""Leafly scraper - updated version with proper variant handling"""

import re
import time
import logging
from typing import List, Dict, Any
from utils.common import (
    setup_session, retry_request, validate_product, 
    filter_by_categories, PRODUCT_TEMPLATE, format_price, apply_tax
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
        
        # ⬇️ NEW: normalize every product's Price to after-tax using website_list.json flags
        for p in products:
            p["Price"] = apply_tax(p.get("Price") or {}, store_config)
        
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
    """Parse Leafly product data with proper variant handling"""
    try:
        product = PRODUCT_TEMPLATE.copy()
        
        product["Product name"] = product_data.get("name", "N/A")
        product["Category"] = product_data.get("productCategory", "")
        product["Brand"] = _extract_leafly_brand(product_data)
        product["THC"] = _extract_leafly_thc(product_data)
        product["Quantity Available"] = _extract_leafly_total_quantity(product_data)
        
        # Extract price and quantity per option based on variants
        price_data, discount_price_data, quantity_per_option = _extract_leafly_variants(product_data)
        product["Price"] = price_data
        product["Quantity Per Option"] = quantity_per_option
        product["Discount Price"] = discount_price_data
        
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

def _extract_leafly_variants(product_data: Dict) -> tuple[Dict[str, str], Dict[str, int]]:
    """Extract price and quantity data from variants"""
    price_data = {}
    discount_price_data = {}
    quantity_per_option = {}
    
    variants = product_data.get("variants", [])
    stock_quantity = product_data.get("stockQuantity", 0)
    
    if variants and isinstance(variants, list):
        for variant in variants:
            display_qty = (variant.get("displayQuantity") or "").strip()
            price = variant.get("price")

            # --- Smart unit normalization ---
            # If display_qty is blank or generic like "each", or doesn't contain units such as g/oz/ml/ct
            # then try to extract the real quantity from the product name.
            if not display_qty or display_qty.lower() == "each" or not re.search(r'(\d*\.\d+|\d+)\s*(g|oz|ml|mg|ct)', display_qty, re.IGNORECASE):
                # Extract quantity directly from product name using improved regex
                name = product_data.get("name", "")
                match = re.search(r'(?<!\d)(\d*\.\d+|\d+)\s*(g|oz|ml|mg|ct)\b', name, re.IGNORECASE)
                if match:
                    display_qty = match.group(0).replace(" ", "").lower()  # normalize spacing
                    if display_qty.startswith("."):  # optional: normalize .5g → 0.5g
                        display_qty = "0" + display_qty
                else:
                    display_qty = "each"

            # --- NEW: handle discount from Leafly's "deal" object ---
            deal = variant.get("deal", {}) or {}
            discounted_price_raw = deal.get("discountedPrice")
            discount_amount = deal.get("discountAmount")
            discount_type = deal.get("discountType")

            if display_qty and price is not None:
                qty_key = str(display_qty).strip()
                # Convert Leafly's cents → dollars
                price_value = float(price) / 100 if price > 100 else float(price)
                discounted_value = None

                if discounted_price_raw:  # direct discounted price in cents
                    discounted_value = float(discounted_price_raw) / 100 if discounted_price_raw > 100 else float(discounted_price_raw)
                elif discount_amount:  # fallback if only discount amount available
                    if discount_type == "cent":
                        discounted_value = price_value - (float(discount_amount) / 100)
                    else:
                        discounted_value = price_value - float(discount_amount)

                # Fallback — if no discount info
                if not discounted_value:
                    discounted_value = price_value

                # Apply tax on discounted price
                final_discounted = apply_tax(discounted_value, {"Company name": "Leafly"})

                # Store formatted values
                price_data[qty_key] = format_price(price_value)
                discount_price_data[qty_key] = format_price(final_discounted)

                quantity_per_option[qty_key] = int(stock_quantity) if stock_quantity else 0

        # Multiple variants scenario
        # for variant in variants:
        #     display_qty = variant.get("displayQuantity", "")
        #     price = variant.get("price")
            
        #     if display_qty and price is not None:
        #         # Format the quantity key (e.g., "1g", "3.5g", "7g")
        #         qty_key = str(display_qty).strip()
        #         price_data[qty_key] = format_price(price)
                
        #         # For quantity per option, we use the stock quantity from main product
        #         # since individual variant stock quantities are often not provided
        #         quantity_per_option[qty_key] = int(stock_quantity) if stock_quantity else 0
    
    else:
        # Single variant scenario - use main product data
        main_price = product_data.get("price")
        display_qty = product_data.get("displayQuantity") or product_data.get("normalizedQuantity", "")
        
        if main_price is not None:
            if display_qty:
                qty_key = str(display_qty).strip()
                price_data[qty_key] = format_price(main_price)
                quantity_per_option[qty_key] = int(stock_quantity) if stock_quantity else 0
            else:
                # Fallback to "each" if no display quantity
                price_data["each"] = format_price(main_price)
                quantity_per_option["each"] = int(stock_quantity) if stock_quantity else 0
    
    # Fallback: if no variants and no main price, try to extract from basic fields
    if not price_data:
        main_price = product_data.get("price")
        if main_price is not None:
            # Try to get quantity from product name or other fields
            qty_from_name = _extract_quantity_from_name(product_data.get("name", ""))
            if qty_from_name:
                price_data[qty_from_name] = format_price(main_price)
                quantity_per_option[qty_from_name] = int(stock_quantity) if stock_quantity else 0
            else:
                price_data["each"] = format_price(main_price)
                quantity_per_option["each"] = int(stock_quantity) if stock_quantity else 0
    
    return price_data, discount_price_data, quantity_per_option

def _extract_quantity_from_name(product_name: str) -> str:
    """Extract quantity information from product name"""
    if not product_name:
        return ""
    
    # Look for patterns like "1g", "3.5g", "7g", "1oz", "2ct", etc.
    patterns = [
        r'\b(\d+(?:\.\d+)?)\s*(g|gr|gram|grams)\b',
        r'\b(\d+(?:\.\d+)?)\s*(oz|ounce|ounces)\b', 
        r'\b(\d+)\s*(ct|count|pk|pack|pcs?|piece|pieces)\b',
        r'\b(\d+(?:\.\d+)?)\s*(ml|mg)\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, product_name, re.IGNORECASE)
        if match:
            number = match.group(1)
            unit = match.group(2).lower()
            
            # Normalize units
            if unit in ['gr', 'gram', 'grams']:
                unit = 'g'
            elif unit in ['ounce', 'ounces']:
                unit = 'oz'
            elif unit in ['ct', 'count', 'pk', 'pack', 'pcs', 'pc', 'piece', 'pieces']:
                unit = 'ct'
                
            return f"{number}{unit}"
    
    return ""

def _extract_leafly_thc(product_data: Dict) -> str:
    """Extract THC from Leafly product"""
    # Try thcContent first
    thc = product_data.get("thcContent")
    if thc is not None and thc != "":
        thc_str = str(thc).strip()
        if thc_str and thc_str != "0":
            return f"{thc_str}%" if not thc_str.endswith('%') else thc_str
    
    # Try thcContentLabel
    thc_label = product_data.get("thcContentLabel", "")
    if thc_label and thc_label.strip() and thc_label.strip() != "-":
        # Clean up the label and return as-is if it looks valid
        thc_clean = thc_label.strip()
        if re.match(r'[\d\.]+\s*%?', thc_clean):
            return thc_clean if thc_clean.endswith('%') else f"{thc_clean}%"
        return thc_clean
    
    return ""

def _extract_leafly_total_quantity(product_data: Dict) -> int:
    """Extract total available quantity from Leafly product"""
    # Primary: use stockQuantity from main product
    stock_qty = product_data.get("stockQuantity")
    if stock_qty is not None:
        return int(stock_qty)
    
    # Fallback: use quantity from main product
    main_qty = product_data.get("quantity")
    if main_qty is not None:
        return int(main_qty)
    
    # Fallback: check variants for quantity info
    variants = product_data.get("variants", [])
    if variants and isinstance(variants, list):
        for variant in variants:
            var_qty = variant.get("quantity")
            if var_qty is not None:
                return int(var_qty)
    
    # Last resort: try to extract from product name
    qty_from_name = _extract_count_from_name(product_data.get("name", ""))
    if qty_from_name:
        return qty_from_name
    
    return 0

def _extract_count_from_name(product_name: str) -> int:
    """Extract count/quantity number from product name"""
    if not product_name:
        return 0
    
    # Look for patterns indicating count/quantity
    patterns = [
        r'\b(\d+)\s*(?:ct|count|pk|pack|pcs?|piece|pieces|each)\b',
        r'\b(\d+)\s*x\s*',  # "5x" pattern
        r'(\d+)\s*-?\s*pack',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, product_name, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return 0