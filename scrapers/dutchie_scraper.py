"""Dutchie scraper - adapted from your existing code"""

import json
import time
import copy
import logging
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils.common import (
    validate_product, filter_by_categories, PRODUCT_TEMPLATE, format_price, apply_tax
)

def scrape_dutchie(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scrape Dutchie dispensary using Selenium
    
    Args:
        store_config: Store configuration dict
        
    Returns:
        List of product dictionaries
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    driver = None
    
    try:
        logging.info(f" Starting Dutchie scrape for {company_name}")
        
        # Check required fields
        dispensary_id = store_config.get("Dispensary ID")
        if not dispensary_id:
            raise ValueError("Dispensary ID is required for Dutchie scraper")
        
        # Setup driver
        driver = _setup_chrome_driver()
        
        # Navigate and handle age verification
        driver.get(store_config["Store url"])
        time.sleep(5)
        _handle_age_verification(driver)
        # time.sleep(5)
        
        # Get categories
        categories = store_config.get("Category Names", [])
        brand_id = store_config.get("Brand Id", [])

        
        # Fetch all products
        products = _fetch_all_dutchie_products(driver, dispensary_id, categories, brand_id,store_config)
        
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
    finally:
        if driver:
            driver.quit()

def _setup_chrome_driver():
    """Setup Chrome WebDriver with options"""
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

# def _setup_chrome_driver():
#     """Setup Chrome WebDriver with options - Task Scheduler compatible"""
#     options = Options()
    
#     # Use MINIMAL options - matching your working test script
#     options.add_argument('--no-sandbox')
#     options.add_argument('--disable-dev-shm-usage')
#     options.add_argument('--start-maximized')
    
#     # Optional: Add headless if needed (but test without first)
#     # options.add_argument('--headless=new')
    
#     try:
#         # Simple initialization - exactly like your test script
#         driver = webdriver.Chrome(options=options)
        
#         logging.info("Chrome driver initialized successfully")
#         return driver
        
#     except Exception as e:
#         logging.error(f"Failed to initialize Chrome driver: {e}", exc_info=True)
#         raise

def _handle_age_verification(driver):
    """Handle age verification popup"""
    wait = WebDriverWait(driver, 15)
    selectors = [
        "//button[contains(text(), 'YES')]",
        "//button[contains(text(), 'Yes')]",
        "//button[contains(text(), 'ENTER')]",
        "//button[contains(text(), 'Enter')]",
        "//button[@data-testid='age-restriction-yes']",
        "//button[contains(@class, 'age') and contains(text(), 'Yes')]",
        "//div[contains(@class, 'age')]//button[1]",
    ]
    
    for selector in selectors:
        try:
            element = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
            driver.execute_script("arguments[0].click();", element)
            logging.info("Age verification handled")
            return
        except:
            continue
    
    logging.warning("Could not handle age verification")

def _fetch_all_dutchie_products(driver, dispensary_id: str, categories: List[str], brand_id: List[str], store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch all products using GraphQL API"""
    all_products = []
    page = 0
    per_page = 50
    
    # Get initial products
    products_data, query_info = _fetch_dutchie_page(driver, dispensary_id, page, per_page, brand_id)
    if not products_data:
        return []
    
    total_pages = query_info.get("totalPages", 1)
    logging.info(f"Dutchie total pages: {total_pages}")
    
    # Process all pages
    while page < total_pages:
        if page > 0:  # Already have first page
            products_data, _ = _fetch_dutchie_page(driver, dispensary_id, page, per_page, brand_id)
        
        if products_data:
            parsed_products = _process_dutchie_products(products_data, categories,store_config)
            all_products.extend(parsed_products)
            logging.debug(f"Dutchie page {page + 1}: {len(parsed_products)} products")
        
        page += 1
        time.sleep(2)
    
    return all_products

def _fetch_dutchie_page(driver, dispensary_id: str, page: int, per_page: int, brand_id: str) -> tuple:
    """Fetch a single page using GraphQL API"""
    payload = {
        "operationName": "FilteredProducts",
        "variables": {
            "includeEnterpriseSpecials": False,
            "includeCannabinoids": True,
            "productsFilter": {
                "dispensaryId": dispensary_id,
                # "brandIds": [brand_id],
                "brandIds": brand_id if isinstance(brand_id, list) else [brand_id],
                "pricingType": "rec",
                "Status": "Active",
                "useCache": False,
                "sortBy": "relevance",
                "sortDirection": 1,
                "removeProductsBelowOptionThresholds": True
            },
            "page": page,
            "perPage": per_page
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "4bfbf7d757b39f1bed921eab15fc7328dab55a30ad47ff8d5cc499f810ff2aee"
            }
        }
    }
    
    script = f"""
        var callback = arguments[arguments.length - 1];
        fetch("https://dutchie.com/api-3/graphql?operationName=FilteredProducts", {{
            method: "POST",
            headers: {{
                "accept": "*/*",
                "content-type": "application/json",
                "x-apollo-operation-name": "FilteredProducts",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }},
            body: JSON.stringify({json.dumps(payload)})
        }})
        .then(response => response.json())
        .then(data => callback(data))
        .catch(error => callback({{"error": error.toString()}}));
    """
    
    driver.set_script_timeout(45)
    result = driver.execute_async_script(script)
    
    if result and "data" in result:
        filtered_products = result.get("data", {}).get("filteredProducts", {})
        products = filtered_products.get("products", [])
        query_info = filtered_products.get("queryInfo", {})
        return products, query_info
    
    return [], {}

def _process_dutchie_products(products_data: List[dict], categories: List[str],store_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Process raw product data into standardized format"""
    processed_products = []
    
    for product_data in products_data:
        try:
            product = _parse_dutchie_product(product_data,store_cfg)
            if product and validate_product(product):
                    processed_products.append(product)
        except Exception as e:
            logging.error(f"Error processing Dutchie product: {e}")
            continue
    
    return processed_products

def _parse_dutchie_product(product_data: dict,store_cfg: dict) -> Optional[Dict[str, Any]]:
    """Parse Dutchie product data"""
    product = PRODUCT_TEMPLATE.copy()
    
    # Basic info
    name = product_data.get("Name", "").strip()
    if not name:
        return None
    
    product["Product name"] = name
    product["Category"] = product_data.get("type", "Unknown").lower()
    
    # Brand
    brand = product_data.get("brandName") or ""
    if not brand:
        brand_obj = product_data.get("brand", {})
        if isinstance(brand_obj, dict):
            brand = brand_obj.get("name", "")
    product["Brand"] = brand
    
    # THC content
    thc_content = product_data.get("THCContent", {})
    thc = ""
    if thc_content:
        thc_range = thc_content.get("range", [])
        if thc_range and len(thc_range) > 0 and thc_range[0] is not None:
            thc = f"{thc_range[0]}%"
    product["THC"] = thc
    
    # Pricing and quantity per option
    price_dict = {}
    quantity_dict = {}  # NEW: Dictionary to store quantity per option
    total_quantity = 0
    
    # Check children for options, prices, and quantities
    children = product_data.get("POSMetaData", {}).get("children", [])
    if children:
        for child in children:
            option = child.get("option")
            price = child.get("recPrice") or child.get("price")
            quantity = child.get("quantity", 0)
            
            if option and price is not None:
                price_dict[option] = format_price(price)
                quantity_dict[option] = quantity  # NEW: Store quantity per option
                total_quantity += quantity
    
    # Fallback to direct options/prices (without per-option quantities)
    if not price_dict:
        options = product_data.get("Options") or product_data.get("rawOptions") or []
        prices = product_data.get("recPrices") or product_data.get("Prices") or []
        
        if len(options) == len(prices):
            for opt, price in zip(options, prices):
                if price is not None:
                    price_dict[opt] = format_price(price)
                    # For fallback, we don't have per-option quantities
                    quantity_dict[opt] = 0
    
    # Final fallback
    if not price_dict:
        fallback_price = product_data.get("recPrice") or product_data.get("price")
        if fallback_price is not None:
            price_dict["each"] = format_price(fallback_price)
            quantity_dict["each"] = product_data.get("quantity", 0)
    
    # --- Apply discount first, then tax ---
    discount_percent = product_data.get("discountAmount", 0) or 0

    discounted_price_dict = {}
    formatted_price_dict = {}
    for option, price in price_dict.items():
        try:
            # Ensure numeric conversion
            price_clean = float(str(price).replace("$", "").strip())
            
            # Apply discount
            discounted = price_clean * (1 - (discount_percent / 100))
            discounted_price_dict[option] = f"${discounted:.2f}"  # Store as string with $

            # Apply tax (or any other adjustments) for final Price
            taxed_price = apply_tax(discounted, store_cfg)
            formatted_price_dict[option] = f"${taxed_price:.2f}"  # Store as string with $
        
        except Exception as e:
            logging.error(f"Error applying discount for {option}: {e}")
            discounted_price_dict[option] = format_price(price)
            taxed = apply_tax(price, store_cfg)
            formatted_price_dict[option] = format_price(taxed)

    # Add discounted price before tax
    product["Discount Price"] = discounted_price_dict

    # Final price after tax
    product["Price"] = formatted_price_dict

    product["Quantity Per Option"] = quantity_dict  # NEW: Add quantity per option
    
    if total_quantity == 0:
        total_quantity = product_data.get("quantity", 0)
    
    product["Quantity Available"] = total_quantity
    
    return product