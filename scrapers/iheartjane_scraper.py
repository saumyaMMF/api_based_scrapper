"""iHeartJane scraper - adapted from your existing code"""

import json
import time
import uuid
import requests
import browser_cookie3
import logging
from typing import List, Dict, Any
from utils.common import (
    validate_product, filter_by_categories, PRODUCT_TEMPLATE, format_price, apply_tax
)

BRAND_LIST = ["Rhize","Rhize Cannabis", "Rhize Cannabis Company", "Rhize Cannabis Company LLC"]

def scrape_iheartjane(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scrape iHeartJane dispensary
    
    Args:
        store_config: Store configuration dict
        
    Returns:
        List of product dictionaries
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    
    try:
        logging.info(f" Starting iHeartJane scrape for {company_name}")
        
        # Extract store ID from URL
        try:
            store_id = store_config['Store ID']
        except Exception as e:
            raise ValueError(f"Failed to extract store ID from URL: {store_config['Store url']}")
        
        # Setup session and cookies
        session = requests.Session()
        
        # Try to load cookies for better success rate
        try:
            cookies = browser_cookie3.chrome(domain_name='iheartjane.com')
            session.cookies.update(cookies)
            logging.info(f"iHeartJane: Loaded {len(cookies)} cookies")
        except Exception as e:
            logging.warning(f"iHeartJane: Failed to load cookies: {e}")
            logging.info("iHeartJane: Continuing without cookies")

        # Fetch products for each category
        all_products = []
         
        products = _fetch_iheartjane_category(session, store_id)
        # ⬇️ Make every product's Price after-tax using website_list.json flags
        for p in products:
            p["Price"] = apply_tax(p.get("Price") or {}, store_config)

        # Filter out invalid products
        valid_products = []
        for product in products:
            if (product.get("Product name") != "Unnamed" and 
                product.get("Brand") != "Unknown Brand" and 
                product.get("Price", {}).get("each") != "N/A"):
                valid_products.append(product)
            else:
                logging.debug(f"Filtered out invalid product: {product.get('Product name')}")
        
        logging.info(f"iHeartJane: {len(valid_products)} valid products (filtered {len(products) - len(valid_products)} invalid)")
        all_products.extend(valid_products)
        
        # Validate products
        final_products = []
        for product in all_products:
            if validate_product(product):
                final_products.append(product)
        
        duration = time.time() - start_time
        logging.info(f" {company_name}: {len(final_products)} products in {duration:.2f}s")
        
        return final_products
        
    except Exception as e:
        logging.error(f" {company_name}: {e}")
        return []

def _fetch_iheartjane_category(session: requests.Session, store_id: int) -> List[Dict[str, Any]]:
    """Fetch products for a specific category with better API payload"""
    url = "https://dmerch.iheartjane.com/v2/smart"
    params = {
        "jdm_api_key": "ce5f15c9-3d09-441d-9bfd-26e87aff5925",
        "jdm_source": "monolith",
        "jdm_version": "2.5.0"
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://www.iheartjane.com",
        "referer": "https://www.iheartjane.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Create brand filter with proper escaping
    brand_filter_parts = []
    for brand in BRAND_LIST:
        # Properly escape quotes with backslashes for the search filter
        brand_filter_parts.append(f'brand:"{brand}"')
    
    # Join with OR operator
    brand_filter = f"({' OR '.join(brand_filter_parts)})"
    
    # Create complete search filter
    search_filter = f'store_id = {store_id} AND {brand_filter}'

    # Create a more complete payload that matches the website behavior
    payload = {
        "app_mode": "embedded",
        "distinct_id": f"$device:{uuid.uuid4()}",
        "jane_device_id": str(uuid.uuid4()),
        "search_attributes": [
            "name", "brand", "category", "kind", "price", "bucket_price", "percent_thc", 
            "percent_cbd", "available_weights", "aggregate_rating", "max_cart_quantity",
            "inventory_potencies", "special_offers", "product_id"
        ],
        "store_id": store_id,
        "disable_ads": False,
        "num_columns": 2,
        "page_size": 100,
        "page_index": 0,
        "placement": "menu_inline_table",
        "search_facets": [
            "activities", "aggregate_rating", "applicable_special_ids", "available_weights",
            "brand_subtype", "brand", "bucket_price", "category", "feelings", "has_brand_discount",
            "kind", "percent_cbd", "percent_thc", "root_types", "special_offers", "inventory_potencies"
        ],
        "search_filter": search_filter,
        "search_query": "",
        "search_sort": "recommendation",
        "session_id": str(uuid.uuid4()),
        "user_id": None,
        "is_authenticated": False,
        "location": {
            "latitude": None,
            "longitude": None
        }
    }
    
    return _fetch_all_iheartjane_products_paginated(payload, session, url, headers, params)

def _fetch_all_iheartjane_products_paginated(payload, session, url, headers, params):
    """Fetch all products with proper pagination and duplicate detection"""
    products = []
    seen_ids = set()
    page_index = 0
    max_attempts = 3
    page_size = payload.get("page_size", 60)
    consecutive_empty_pages = 0
    max_empty_pages = 2

    while True:
        payload["page_index"] = page_index
        
        # Generate new IDs for each page to avoid caching issues
        payload["distinct_id"] = f"$device:{uuid.uuid4()}"
        payload["jane_device_id"] = str(uuid.uuid4())
        payload["session_id"] = str(uuid.uuid4())
        
        # Retry logic for each page
        page_products = []
        for attempt in range(max_attempts):
            try:
                logging.debug(f"iHeartJane: Requesting page {page_index + 1}, attempt {attempt + 1}")
                
                response = session.post(url, params=params, headers=headers, 
                                      data=json.dumps(payload), timeout=30)
                
                if response.status_code != 200:
                    logging.warning(f"iHeartJane HTTP {response.status_code} on page {page_index + 1}")
                    if response.status_code == 429:  # Rate limited
                        time.sleep(5)
                        continue
                    return products
                
                data = response.json()
                page_products = data.get("products", [])

                # Debug: Log the first product to see what we're getting
                if page_products and page_index == 0:
                    first_product = page_products[0]
                    logging.debug(f"iHeartJane first product sample: {json.dumps(first_product, indent=2)[:500]}...")
                
                break
                
            except Exception as e:
                logging.error(f"iHeartJane retry {attempt + 1} for page {page_index + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2 * (attempt + 1))
        else:
            logging.error(f"iHeartJane: Failed all retries for page {page_index + 1}")
            return products

        if not page_products:
            consecutive_empty_pages += 1
            logging.info(f"iHeartJane: No products found on page {page_index + 1} (empty page {consecutive_empty_pages})")
            
            if consecutive_empty_pages >= max_empty_pages:
                logging.info(f"iHeartJane: Hit {max_empty_pages} consecutive empty pages, stopping")
                return products
            
            # Skip to next page in case this was a temporary issue
            page_index += 1
            continue
        else:
            consecutive_empty_pages = 0  # Reset counter

        # Check for new products (not seen before)
        new_products = []
        for p in page_products:
            product_id = p.get("product_id")
            if not product_id:
                # Create fallback ID from product data
                search_attrs = p.get("search_attributes", {})
                product_id = f"{search_attrs.get('name', 'unnamed')}_{search_attrs.get('brand', 'unknown')}_{search_attrs.get('bucket_price', 0)}"
            
            if product_id not in seen_ids:
                new_products.append(p)
                seen_ids.add(product_id)
        
        if not new_products:
            logging.info(f"iHeartJane: All {len(page_products)} products on page {page_index + 1} are duplicates. Stopping.")
            return products

        # Parse and add new products
        for product_data in new_products:
            parsed_product = _parse_iheartjane_product(product_data, payload["search_filter"])
            if parsed_product:
                products.append(parsed_product)

        logging.info(f"iHeartJane page {page_index + 1}: {len(new_products)} new items (total: {len(products)})")

        # Check if we should continue pagination
        if len(page_products) < page_size:
            logging.info(f"iHeartJane: Reached end of results (page {page_index + 1} had {len(page_products)} < {page_size})")
            break
            
        page_index += 1
        time.sleep(1)  # Rate limiting

    logging.info(f"iHeartJane: Finished pagination. Total products: {len(products)}")
    return products

def _parse_iheartjane_product(product_data: Dict, search_filter: str) -> Dict[str, Any]:
    """Parse iHeartJane product data with better error handling"""
    try:
        product = PRODUCT_TEMPLATE.copy()
        
        search_attrs = product_data.get("search_attributes", {})
        
        # Debug: Log product data if we're getting empty results
        if not search_attrs.get("name"):
            logging.debug(f"iHeartJane: Empty product data: {json.dumps(product_data, indent=2)[:300]}...")
        
        # Product name
        product_name = search_attrs.get("name") or product_data.get("name")
        if not product_name or product_name.strip() == "":
            logging.debug("iHeartJane: Skipping product with empty name")
            return None
        
        product["Product name"] = product_name.strip()
        
        # Extract category from search_filter or use product category
        category = ""
        if "kind:" in search_filter:
            # Extract category from search filter like: kind:"flower"
            import re
            match = re.search(r'kind:"([^"]+)"', search_filter)
            if match:
                category = match.group(1)
        
        if not category:
            category = search_attrs.get("kind") or search_attrs.get("kind", "Unknown")
        
        product["Category"] = category
        
        # Brand
        brand = search_attrs.get("brand")
        if not brand or brand.strip() == "":
            brand = product_data.get("brand", "Unknown Brand")
        product["Brand"] = brand.strip() if brand else "Unknown Brand"
        
        # THC content
        thc = search_attrs.get("percent_thc")
        if thc and isinstance(thc, (int, float)) and thc > 0:
            product["THC"] = f"{thc}%"
        else:
            # Try inventory potencies
            potencies = search_attrs.get("inventory_potencies", [])
            if potencies and isinstance(potencies, list):
                for pot in potencies:
                    if isinstance(pot, dict) and "thc_potency" in pot:
                        thc_val = pot["thc_potency"]
                        if thc_val and isinstance(thc_val, (int, float)) and thc_val > 0:
                            product["THC"] = f"{thc_val}%"
                            break
            
            # If still no THC, try other fields
            if not product["THC"] or product["THC"] == "":
                thc_content = search_attrs.get("thc_content") or search_attrs.get("thc")
                if thc_content and isinstance(thc_content, (int, float)) and thc_content > 0:
                    product["THC"] = f"{thc_content}%"
                else:
                    product["THC"] = "N/A"
        
        # Price
        price_found = False
        bucket_price = search_attrs.get("bucket_price")
        
        if bucket_price and isinstance(bucket_price, (int, float)) and bucket_price > 0:
            product["Price"] = {"each": format_price(bucket_price)}
            price_found = True
        else:
            # Try other price fields
            price_each = product_data.get("price_each")
            if price_each and isinstance(price_each, (int, float)) and price_each > 0:
                product["Price"] = {"each": format_price(price_each)}
                price_found = True
            else:
                # Try price in search attributes
                price_attr = search_attrs.get("price")
                if price_attr and isinstance(price_attr, (int, float)) and price_attr > 0:
                    product["Price"] = {"each": format_price(price_attr)}
                    price_found = True
        
        if not price_found:
            product["Price"] = {"each": "N/A"}
        
        # Quantity
        quantity = search_attrs.get("max_cart_quantity") or product_data.get("max_cart_quantity")
        if quantity and isinstance(quantity, (int, float)) and quantity > 0:
            product["Quantity Available"] = int(quantity)
        else:
            # Try other quantity fields
            inventory_quantity = search_attrs.get("inventory_quantity") or search_attrs.get("quantity")
            if inventory_quantity and isinstance(inventory_quantity, (int, float)) and inventory_quantity > 0:
                product["Quantity Available"] = int(inventory_quantity)
            else:
                product["Quantity Available"] = 0
        
        # Additional validation - skip if core data is missing
        if (product["Product name"] == "Unnamed" or 
            product["Brand"] == "Unknown Brand" or 
            product["Price"]["each"] == "N/A"):
            logging.debug(f"iHeartJane: Skipping invalid product: {product['Product name']}")
            return None
        
        return product
        
    except Exception as e:
        logging.error(f"Failed to parse iHeartJane product: {e}")
        logging.debug(f"Product data that failed: {json.dumps(product_data, indent=2)[:500]}...")
        return None