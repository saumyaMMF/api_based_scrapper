"""Universal dispensary.shop scraper (Tea House / Rolling Twenties) using embedded remixContext JSON
- Pagination identical to your original structure
- Brand filter is dynamic via config (no hardcoding)
- No category filtering
"""

import time
import requests
import logging
import re
import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from bs4 import BeautifulSoup
from utils.common import (
    validate_product, PRODUCT_TEMPLATE, format_price, apply_tax
)


def _merge_query_params(base_url: str, extra: Dict[str, Optional[str]]) -> str:
    """Safely add/override query params (skips None values)."""
    parsed = urlparse(base_url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for k, v in extra.items():
        if v is None:
            q.pop(k, None)
        else:
            q[k] = v
    new_query = urlencode(q, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def scrape_teahouse(store_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generic scraper for dispensary.shop sites using embedded Remix context.
    - No category filtering
    - Brand filter comes from config (optional)
    """
    start_time = time.time()
    company_name = store_config["Company name"]
    all_products: List[Dict[str, Any]] = []
    page = 1
    per_page_expected = int(store_config.get("per_page_expected", 20))

    remix_path = store_config.get("Remix Path", "routes/catalog.search")
    store_url = store_config.get("Store url")
    if not store_url:
        raise ValueError("Store url missing in config")

    brand = (store_config.get("Brand") or "").strip() or None  # dynamic brand
    medrec = (store_config.get("medrec") or "rec").strip()     # default rec
    run_validate = bool(store_config.get("validate", True))     # allow disabling validate if needed

    try:
        logging.info(f" Starting scrape for {company_name}")

        while True:
            logging.info(f"Fetching page {page}")
            products = _fetch_teahouse_products(
                page=page,
                store_url=store_url,
                remix_path=remix_path,
                brand=brand,
                medrec=medrec,
            )

            if not products:
                break  # No more data or error

            logging.info(f" Pulled {len(products)} raw products from page {page}")
            all_products.extend(products)

            if len(products) < per_page_expected:
                logging.info(f"Final page reached: {page} with {len(products)} products")
                break

            page += 1

        logging.info(f" Skipping category filter; keeping all {len(all_products)} products")
        # ⬇️ NEW: convert every product's Price to after-tax using website_list.json flags
        for p in all_products:
            p["Price"] = apply_tax(p.get("Price") or {}, store_config)

        if run_validate:
            deduped_products = [p for p in all_products if validate_product(p)]
            logging.info(f" After validate_product(): {len(deduped_products)} / {len(all_products)}")
        else:
            deduped_products = all_products
            logging.info(" validate_product() disabled via config; keeping all products")

        duration = time.time() - start_time
        logging.info(f" {company_name}: {len(deduped_products)} products in {duration:.2f}s")
        return deduped_products

    except Exception as e:
        logging.error(f" {company_name}: {e}")
        return []


def _fetch_teahouse_products(
        page: int,
        store_url: str,
        remix_path: str,
        brand: Optional[str] = None,
        medrec: str = "rec",
    ) -> List[Dict[str, Any]]:
        all_products: List[Dict[str, Any]] = []
        headers = {"User-Agent": "Mozilla/5.0"}

        url_with_params = _merge_query_params(store_url, {
            "page": str(page),
            "medrec": medrec,
            "brand": brand if brand else None
        })

        try:
            resp = requests.get(url_with_params, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logging.warning(f"Request failed for page {page}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Be robust: .get_text() works even if .string is None
        script_tag = soup.find("script", string=lambda s: s and "window.__remixContext" in s) \
                    or soup.find("script", text=lambda s: s and "window.__remixContext" in s)
        if not script_tag:
            logging.warning(f"No remixContext <script> found on page {page}")
            return []

        script_text = script_tag.get_text() or ""
        # Non-greedy with DOTALL so we capture the full JSON across lines
        m = re.search(r"window\.__remixContext\s*=\s*(\{.*?\});", script_text, flags=re.DOTALL)
        if not m:
            logging.warning(f"remixContext JSON not matched on page {page}")
            return []

        try:
            remix_data = json.loads(m.group(1))
        except Exception as e:
            logging.warning(f"Failed to parse remixContext JSON on page {page}: {e}")
            return []

        # Locate loaderData node. If configured key missing, fall back to any node with "products"
        try:
            loader_data_all = remix_data["state"]["loaderData"]
            loader_data = loader_data_all.get(remix_path)
            if not loader_data:
                # Fallback: pick the first loader with a "products" key
                for k, v in loader_data_all.items():
                    if isinstance(v, dict) and "products" in v:
                        loader_data = v
                        logging.info(f"Fallback loaderData key used: {k}")
                        break
            if not loader_data:
                logging.warning(f"Missing loaderData entry for '{remix_path}' and no fallback found (page {page})")
                return []
        except Exception as e:
            logging.warning(f"loaderData not found/invalid on page {page}: {e}")
            return []

        # Normalize products block safely:
        # - Some sites: "products": [...]
        # - Others:     "products": { "products": [...] } or null
        products_block = loader_data.get("products", [])
        product_entries: List[dict] = []

        if isinstance(products_block, list):
            product_entries = products_block
        elif isinstance(products_block, dict):
            inner = products_block.get("products")
            if isinstance(inner, list):
                product_entries = inner
            else:
                # Handle present-but-null / wrong-type gracefully
                product_entries = []
        else:
            product_entries = []

        # Brand filter normalization: brand can be a string or an object with "name"
        brand_norm = (brand or "").strip().lower()
        for p in product_entries or []:  # coalesce None→[]
            p_brand = p.get("brand", "")
            if isinstance(p_brand, dict):
                p_brand_val = (p_brand.get("name") or "").lower()
            else:
                p_brand_val = (p_brand or "").lower()

            if brand_norm and p_brand_val != brand_norm:
                continue

            parsed = _parse_teahouse_product_safe(p)  # see below
            if parsed:
                all_products.append(parsed)

        return all_products

def _parse_teahouse_product_safe(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper that normalizes common fields before calling your original parser."""
    # Make brand a string
    brand = product_data.get("brand", "")
    if isinstance(brand, dict):
        product_data = {**product_data, "brand": brand.get("name", "")}

    # potencies may be None or dict; normalize to list of dicts
    pots = product_data.get("potencies")
    if pots is None:
        product_data = {**product_data, "potencies": []}
    elif isinstance(pots, dict):
        # Some sites put {"% THC": value,...}; convert to expected list shape
        product_data = {
            **product_data,
            "potencies": [{"name": k, "value": v} for k, v in pots.items()]
        }

    return _parse_teahouse_product(product_data)

def _parse_teahouse_product(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse product object from remixContext into standardized format
    """
    product = PRODUCT_TEMPLATE.copy()

    product["Product name"] = product_data.get("name", "") or product_data.get("product_name", "")
    product["Brand"] = product_data.get("brand", "") or ""
    product["Category"] = product_data.get("category", "") or ""
    product["Quantity Available"] = product_data.get("quantity", 0) or 0

    # Price and weight
    weight_volume = product_data.get("weight_volume")
    weight_uom = product_data.get("weight_volume_uom")
    if weight_volume and weight_uom:
        weight = f"{weight_volume}{str(weight_uom).replace('Grams','g').replace('grams','g')}"
    else:
        weight = ""

    # ---------------- NEW LOGIC BELOW ----------------
    pre_tax_price = product_data.get("pre_tax_price")
    pre_tax_discounted_price = product_data.get("pre_tax_discounted_price")
    post_tax_price = product_data.get("post_tax_price")
    post_tax_discounted_price = product_data.get("post_tax_discounted_price")

    # Primary price (pre-tax)
    if pre_tax_price is not None:
        product["Price"] = {weight: format_price(pre_tax_price / 100)} if weight else {"each": format_price(pre_tax_price / 100)}
    elif post_tax_price is not None:
        product["Price"] = {weight: format_price(post_tax_price / 100)} if weight else {"each": format_price(post_tax_price / 100)}
    else:
        product["Price"] = {}

    # Discount Price (same structure as Dutchie)
    if pre_tax_discounted_price and pre_tax_discounted_price != pre_tax_price:
        product["Discount Price"] = {weight: format_price(pre_tax_discounted_price / 100)} if weight else {"each": format_price(pre_tax_discounted_price / 100)}
    elif post_tax_discounted_price and post_tax_discounted_price != post_tax_price:
        product["Discount Price"] = {weight: format_price(post_tax_discounted_price / 100)} if weight else {"each": format_price(post_tax_discounted_price / 100)}
    else:
        product["Discount Price"] = {}

    # THC
    for pt in product_data.get("potencies", []):
        if pt.get("name") == "% THC":
            product["THC"] = f"{pt.get('value')}%"
            break

    return product
