"""Common utilities for all scrapers - Minimal changes to work with your old functions"""
import os
import json
import time
import logging
import requests
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pickle
import mimetypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from utils.product_name_mapping import load_auto_mappings, save_auto_mapping
from utils.mapping_history import log_mapping_event
from utils.internal_name_orchestrator import ensure_internal_product_name

AUTO_PATTERNS = load_auto_mappings()

# Google Drive scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Enhanced product template with SKU fields
PRODUCT_TEMPLATE = {
    "Product name": "",
    "Category": "",
    "Brand": "",
    "Price": {},
    "Discount Price": {},
    "THC": "",
    "Quantity Available": 0,
    "Quantity Per Option": {},
    "Internal Product Name": "",
    "Internal Product Type": "",
    "SKU": "",
    "Days on Shelf": 0,

}

def setup_session(headers: Optional[Dict[str, str]] = None) -> requests.Session:
    """Setup HTTP session with default headers"""
    session = requests.Session()
    
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    if headers:
        default_headers.update(headers)
    
    session.headers.update(default_headers)
    return session

def retry_request(func, max_retries: int = 3, delay: float = 1.0):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            wait_time = delay * (2 ** attempt)
            logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

import re  # Still needed for SKU unit extraction
from typing import Dict, List, Tuple, Optional, Any

# Optimized product name patterns - organized by category
PRODUCT_NAME_PATTERNS = {
    # === FLOWER PRODUCTS ===
    "donkey butter": "Donkey Butter",
    "papaya juice": "Papaya Juice", 
    "melted strawberries": "Melted Strawberries",
    "melted strawberry": "Melted Strawberries", 
    "melted strawberrys": "Melted Strawberries",
    "melted stawberries": "Melted Strawberries",
    "black maple": "Black Maple",
    "honey banana": "Honey Banana",
    "strawberry guava": "Strawberry Guava",
    "sherb cream pie": "Sherb Cream Pie",
    "sherbet cream pie": "Sherb Cream Pie", 
    "ice cream cake": "Ice Cream Cake",
    "grape pie": "Grape Pie",
    "bop gun": "Bop Gun",
    "sour diesel": "Sour Diesel",
    "g13 skunk": "G13 Skunk",
    "berry fizz":"Berry Fizz",

    # === DULCE DE UVA VARIANTS ===
    "dulce de uva": "Dulce de Uva",
    "duce de uva": "Dulce de Uva",  # typo variant
    
    # === CONCENTRATES & CARTS ===
    "moroccan peaches": "Moroccan Peaches",
    "animal face": "Animal Face", 
    "eastside og": "Eastside OG",
    "eastsise og": "Eastside OG",  # typo variant
    "blackout truffle": "Blackout Truffle",
    "forbidden fruit": "Forbidden Fruit",
    "gmo": "GMO",
    
    # === PREROLLS & PACKS ===
    "deathstar": "Deathstar",
    "death star": "Deathstar",
    "tropical summer": "Tropical Summer",
    "variety pack": "Multipack",
    "multi pack": "Multipack", 
    "multipack": "Multipack",
    "pack": "Multipack",
    "7-pack": "Multipack",
    "7pk": "Multipack",
    
    # === SHAKE ===
    "shake": "Shake",
    "shacke": "Shake",  # typo variant
    
    # === ACCESSORIES ===
    "battery": "Battery",
    "vape pen": "Battery",
    
    # === EDIBLES ===
    "raspberry": "Raspberry",

    "candied oranges": "Candied Oranges",
    "candied orange": "Candied Oranges",

    "lavender piff": "Lavender Piff",
    "the hive": "The Hive",
}

# Additional aliases for common products (easy to add new ones)
PRODUCT_ALIASES = {
    "Melted Strawberries": ["melted strawberry", "melted strawberrys","melted straberries", "melted stawberries"],
    "Sherb Cream Pie": ["sherbet cream pie"],
    "Dulce de Uva": ["duce de uva"],  # typos
    "Eastside OG": ["eastsise og"],  # typos
    "Deathstar": ["death star"],
    "Tropical Summer": ["tropical summer variety pack", "tropical summer pack"],
    "Multipack": ["variety pack", "multi pack", "pack","7-pack ea"],
    "Shake": ["shacke"],  # typos
    "Battery": ["vape pen"],
    "G13 Skunk":["g-13 skunk","g13 skunk"],
}

# Products that have fixed types (base type always wins over patterns)
# These are specific products, not strain names that can be different types
FIXED_TYPE_PRODUCTS = {
    "Battery", "Raspberry", "Multipack", "Shake", "Tropical Summer"
}

# Base product type mappings
BASE_PRODUCT_TYPES = {
    "Donkey Butter": "Flower Jar",
    "Papaya Juice": "Flower Bulk", 
    "Melted Strawberries": "Flower Jar",
    "Black Maple": "Flower Bulk",
    "Honey Banana": "Flower Bulk",
    "Dulce de Uva": "Flower Bulk",
    "Strawberry Guava": "Flower Jar",
    "Sherb Cream Pie": "Flower Jar",
    "Ice Cream Cake": "Flower Bulk",
    "Grape Pie": "Flower Bulk",
    "Bop Gun": "Flower Jar",
    "Moroccan Peaches": "Rosin Jar",
    "Animal Face": "Cart",
    "Eastside OG": "Cart", 
    "Blackout Truffle": "Cart",
    "Forbidden Fruit": "Flower Jar",  # Default, can be overridden
    "Deathstar": "Preroll",
    "GMO": "Flower Bulk",
    "Tropical Summer": "Preroll",
    "Multipack": "Preroll",
    "Shake": "Flower Bulk(Shake)",
    "Battery": "Accessory",
    "Raspberry": "Edibles",
    "Berry Fizz": "Flower Bulk",
    "G13 Skunk": "Flower Bulk",
    "Sour Diesel": "Flower Bulk",
    "The Hive": "Flower Jar",
}

# Weight-based type overrides (weight -> {product_name: type})
WEIGHT_TYPE_OVERRIDES = {
    "0.5g": {
        "Dulce de Uva": "Cart",
        "Deathstar": "Cart", 
        "GMO": "Cart",
        "Papaya Juice": "Cart",
        "Melted Strawberries": "Cart",
    },
    ".5g": {
        "Dulce de Uva": "Cart",
        "Deathstar": "Cart",
        "GMO": "Cart", 
        "Papaya Juice": "Cart",
        "Melted Strawberries": "Cart",
    },
    "½ gram": {
        "Dulce de Uva": "Cart",
        "Deathstar": "Cart",
        "GMO": "Cart",
        "Papaya Juice": "Cart", 
        "Melted Strawberries": "Cart",
    },
    "1g": {
        "Deathstar": "Preroll",
        "Honey Banana": "Rosin Jar",
        "Strawberry Guava": "Rosin Jar",
    },
    "3.5g": {
        "Deathstar": "Flower Bulk",
        "Donkey Butter": "Flower Jar",
        "Papaya Juice": "Flower Jar",
        "Melted Strawberries": "Flower Jar",
        "Dulce de Uva": "Flower Jar",
        "Multipack": "Preroll",
    },
    "1/8 oz": {
        "Dulce de Uva": "Flower Jar",
        "Donkey Butter": "Flower Jar", 
        "Melted Strawberries": "Flower Jar",
        "Multipack": "Preroll",
    },
    "each": {
        "Dulce de Uva": "Cart",
        "Melted Strawberries": "Cart",
        "Papaya Juice": "Cart",
    },
    "5x0.7g": {
        "Multipack": "Preroll",
    },
}

# Store-specific type overrides (store -> {product_name: type})
STORE_TYPE_OVERRIDES = {
    "forbinsfinest": {
        "Honey Banana": "Flower Jar",
        "Papaya Juice": "Flower Jar",
    },
    "garciascannabis": {
        "Sherb Cream Pie": "Flower Bulk",
        "Strawberry Guava": "Flower Bulk", 
        "Melted Strawberries": "Rosin Jar",
    },
    "thebudstop": {
        "Donkey Butter": "Flower Jar",  # Fixed typo from original
        "Dulce de Uva": "Cart",
        "Strawberry Guava": "Flower Jar",
    },
    "sweetspot": {
        "Sherb Cream Pie":"Flower Bulk"
    },
    "greenmountaincannabisworks": {
        "Donkey Butter": "Flower Jar",
    },
    "mothaplant": {
        "Strawberry Guava": "Flower Bulk",
        "Papaya Juice": "Cart", 
    },
    "gramcentral": {
        "Donkey Butter": "Flower Jar",
    },
    # "rimeline": {
    #     "Melted Strawberries": "Flower Bulk",
    # },
}

# Pattern-based type mappings (for when product name contains these terms)
# These take PRIORITY over base type mappings for strain names (but not fixed-type products)
PATTERN_TYPE_MAPPINGS = {
    "pre-roll": "Preroll",
    "pre roll": "Preroll",
    "preroll": "Preroll", 
    "dogwalkers": "Preroll",
    "pack": "Preroll",  # for multipacks
    "cartridge": "Cart",
    "cart": "Cart",
    "vape cartridge": "Cart",
    "live rosin": "Rosin Jar",
    "rosin": "Rosin Jar",
    "concentrate": "Rosin Jar",
    "flower": "Flower Jar",
    "bulk": "Flower Bulk",
    "deli-style": "Flower Bulk",
    "shake": "Flower Bulk(Shake)",
    "battery": "Accessory",
    "vape pen": "Accessory",
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def normalize_string(text: str) -> str:
    """Normalize string for consistent matching"""
    return str(text).lower().strip().replace("-", " ")

def normalize_weight(unit: str) -> str:
    """Normalize weight/unit for consistent matching"""
    return str(unit).strip().replace(" ", "")

def build_complete_patterns() -> Dict[str, str]:
    """Build complete patterns dictionary including aliases"""
    complete_patterns = PRODUCT_NAME_PATTERNS.copy()
    
    # Add aliases
    for main_name, aliases in PRODUCT_ALIASES.items():
        for alias in aliases:
            if alias.lower() not in complete_patterns:
                complete_patterns[alias.lower()] = main_name
    
    return complete_patterns

def extract_internal_name(product_name: str) -> str:
    """Extract internal product name using exact phrase matching"""
    normalized_name = normalize_string(product_name)
    complete_patterns = build_complete_patterns()
    
    if re.search(r"\btropical\s*(?:multi\s*pack|multipack)\b", normalized_name):
        return "Tropical Summer"
    
    # Step 1: Prioritize 'Tropical Summer' over generic multipack
    if "tropical summer" in normalized_name:
        return "Tropical Summer"
    
    if re.search(r"\b\d+\s*pack\b", normalized_name):
        return "Multipack"
    # Step 2: Handle generic multipack phrases
    multipack_indicators = ["multi pack", "multipack", "variety pack"]
    if any(keyword in normalized_name for keyword in multipack_indicators):
        return "Multipack"
        
    # Sort patterns by length (longest first) to match more specific patterns first
    sorted_patterns = sorted(complete_patterns.items(), key=lambda x: len(x[0]), reverse=True)
    
    # Try each pattern in order
    for pattern, internal_name in sorted_patterns:
        if pattern in normalized_name:
            return internal_name
    
    return ""  # No match found

def get_base_product_type(internal_name: str, product_name: str) -> str:
    """
    Get base product type for an internal name
    Priority logic:
    1. For fixed-type products (Battery, etc.) → always use base type
    2. For strain names → check patterns first, then base type
    """
    # For fixed-type products, always use the base type mapping
    if internal_name in FIXED_TYPE_PRODUCTS and internal_name in BASE_PRODUCT_TYPES:
        return BASE_PRODUCT_TYPES[internal_name]
    
    # For strain names, check patterns first (allows strain to be different product types)
    normalized_name = normalize_string(product_name)
    
    for pattern, product_type in PATTERN_TYPE_MAPPINGS.items():
        if pattern in normalized_name:
            return product_type
    
    # Fall back to base type if no patterns match
    if internal_name in BASE_PRODUCT_TYPES:
        return BASE_PRODUCT_TYPES[internal_name]
    
    return ""  # No type found

def apply_weight_override(internal_name: str, current_type: str, weight: str, product_name: str = "") -> str:
    """
    Apply weight-based type overrides
    But skip if product name contains explicit type indicators (bulk, cartridge, pre-roll, etc.)
    This ensures that explicit product descriptions override generic weight mappings
    """
    normalized_weight = normalize_weight(weight)
    
    # Check if product name contains explicit type indicators that should override weight mappings
    if product_name:
        normalized_product_name = normalize_string(product_name)
        explicit_type_indicators = ["bulk", "cartridge", "cart", "pre-roll", "pre roll", "preroll", "live rosin", "flower"]
        
        for indicator in explicit_type_indicators:
            if indicator in normalized_product_name:
                # Product name has explicit type indicator, don't apply weight override
                return current_type
    
    # Check if this weight has overrides
    if normalized_weight in WEIGHT_TYPE_OVERRIDES:
        weight_overrides = WEIGHT_TYPE_OVERRIDES[normalized_weight]
        if internal_name in weight_overrides:
            return weight_overrides[internal_name]
    
    return current_type

def apply_store_override(internal_name: str, current_type: str, store_name: str) -> str:
    """Apply store-specific type overrides"""
    normalized_store = normalize_string(store_name)
    
    # Check if this store has overrides  
    if normalized_store in STORE_TYPE_OVERRIDES:
        store_overrides = STORE_TYPE_OVERRIDES[normalized_store]
        if internal_name in store_overrides:
            return store_overrides[internal_name]
    
    return current_type

# ============================================================================
# MAIN MAPPING FUNCTIONS
# ============================================================================

def product_name_type_mapping(product_name: str, company_name: str, unit: str) -> Tuple[str, str]:
    """
    Extract internal product name and type with clear precedence:
    1. Extract internal name from product name
    2. Get base product type (pattern matching for explicit indicators, then base mapping)
    3. Apply weight-based overrides (unless product name has explicit type indicators like "bulk", "cartridge")
    4. Apply store-specific overrides if they exist
    """
    # Step 1: Extract internal product name
    internal_name = extract_internal_name(product_name)
    if not internal_name:
        return "", ""
    
    # Step 2: Get base product type
    internal_type = get_base_product_type(internal_name, product_name)
    if not internal_type:
        return internal_name, ""
    
    # Step 3: Apply weight override (if exists and no explicit type indicators)
    internal_type = apply_weight_override(internal_name, internal_type, unit, product_name)
    
    # Step 4: Apply store override (if exists) 
    internal_type = apply_store_override(internal_name, internal_type, company_name)
    
    return internal_name, internal_type

# def generate_sku(internal_name: str, internal_type: str, unit: str = "") -> str:
#     """Generate SKU based on internal name, type, and unit"""
#     if not internal_name or not internal_type:
#         return ""
    
#     # Normalize components
#     name_part = normalize_string(internal_name).replace(" ", "")
#     type_part = normalize_sku_type(internal_type)
#     unit_part = normalize_sku_unit(unit, internal_type)
    
#     # Build SKU
#     sku_parts = [name_part, type_part]
#     if unit_part:
#         sku_parts.append(unit_part)
    
#     return "-".join(sku_parts)


def map_internal_type(product: dict) -> dict:
    """Map internal product type based on existing internal name"""
    # If internal name exists, preserve the type from existing data
    if product.get("Internal Product Type"):
        return product
    
    # Otherwise, set a default type or derive from category
    category = product.get("Category", "").lower()
    if "vape" in category or "cart" in category:
        product["Internal Product Type"] = "Cart"
    elif "flower" in category:
        product["Internal Product Type"] = "Flower Jar"
    else:
        product["Internal Product Type"] = "Rosin Jar"
    
    return product

def generate_sku(internal_name: str, internal_type: str, unit: str = "") -> str:
    """Generate SKU based on internal name, type, and unit"""
    if not internal_name or not internal_type:
        return ""
    
    # Normalize components
    name_part = normalize_string(internal_name).replace(" ", "")
    type_part = normalize_sku_type(internal_type)
    unit_part = normalize_sku_unit(unit, internal_type)
    
    # Build base SKU
    sku_parts = [name_part, type_part]
    if unit_part:
        sku_parts.append(unit_part)
    sku = "-".join(sku_parts)

    # --- minimal fix: add '-multipack' for regular multipacks on prerolls ---
    if internal_name in ("Multipack", "Tropical Summer") and "preroll" in internal_type.lower():
        if not sku.endswith("-multipack"):
            sku += "-multipack"
    # -----------------------------------------------------------------------

    return sku

def normalize_sku_type(internal_type: str) -> str:
    """Normalize product type for SKU generation"""
    normalized = normalize_string(internal_type).replace(" ", "").replace("(", "").replace(")", "")
    
    type_mappings = {
        "preroll": "flower-preroll",
        "cart": "rosin-cart", 
        "cartridge": "rosin-cart",
        "flowerjar": "flower-jar",
        "flowerbulk": "flower-bulk",
        "flowerbulkshake": "flower-bulk-shake",
        "flowermultipack": "flower-multipack",
        "rosinjar": "rosin-jar",
        "accessory": "accessory",
        "edibles": "edibles",
        "multipack": "multipack",
    }
    
    return type_mappings.get(normalized, normalized)

def normalize_sku_unit(unit: str, internal_type: str) -> str:
    """Normalize unit for SKU generation (only for Rosin Jar products)"""
    if "rosin jar" not in internal_type.lower():
        return ""
    
    if not unit:
        return ""
    
    # Extract numeric part from unit
    numeric_match = re.search(r"[\d/\.]+", str(unit))
    if not numeric_match:
        return normalize_string(unit).replace(" ", "")
    
    unit_str = numeric_match.group()
    
    # Handle fractions
    if "/" in unit_str:
        return unit_str
    
    # Handle decimals  
    try:
        val = float(unit_str)
        if val == 0.5:
            return ".5"
        elif val == 3.5:
            return "3"
        else:
            return str(int(val)) if val.is_integer() else str(val)
    except ValueError:
        return unit_str
    
def _slug(s: str) -> str:
    """Lowercase alphanum, remove everything else."""
    return re.sub(r'[^a-z0-9]+', '', str(s).lower())

def _canon_unit(u: str) -> str:
    """Normalize unit keys so 'each'/'1' → '1g', '2' → '2g', etc."""
    u = str(u).strip().lower().replace(" ", "").replace("-", "")
    return {
        "each":"1g", "1":"1g", "1.0g":"1g", "1g":"1g", "1gram":"1g", "1grams":"1g",
        "2":"2g", "2.0g":"2g", "2g":"2g", "2gram":"2g", "2grams":"2g",
        "3":"3g", "3.0g":"3g", "3g":"3g", "3gram":"3g", "3grams":"3g",
    }.get(u, u)

def _is_rosin_jar(product: Dict[str, Any]) -> bool:
    """Detect Rosin Jar from existing fields only (no external mapping)."""
    t = (product.get("Internal Product Type")
         or product.get("Product Type")
         or product.get("Category") or "").lower()
    if "rosin" in t and "jar" in t:
        return True
    # Lightweight name fallback (kept simple):
    name = (product.get("Internal Product Name") or product.get("Product name") or "").lower()
    return "rosin" in name and "cart" not in name and "cartridge" not in name

def split_rosin_jar_separate(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generalized Rosin Jar splitter:
      - If Rosin Jar and has prices dict, emit distinct rows for each of {1g, 2g, 3g} that exists.
      - Each emitted row:
          * Price -> only that weight
          * Quantity Per Option -> only that weight
          * Quantity Available -> that weight's quantity
          * Days on Shelf -> preserved
          * SKU -> "<slug(name)>-rosin-jar-{1|2|3}"
      - Any *other* weights (not 1g/2g/3g) are aggregated into a single "others" row (kept for backward compatibility).
        If you don't want that extra row, just drop the "others" section below.
    """
    # Only act on Rosin Jar with a dict of prices
    if not _is_rosin_jar(product) or not isinstance(product.get("Price"), dict):
        return [product]

    price_dict = dict(product.get("Price") or {})
    qpo_dict   = dict(product.get("Quantity Per Option") or {})
    if not price_dict:
        return [product]

    # Targets we want as separate rows
    target_weights = ["1g", "2g", "3g"]

    # Map for SKU suffix
    sku_suffix = {"1g": "1", "2g": "2", "3g": "3"}

    # Helper to build a single-weight clone
    def build_weight_clone(weight_key_norm: str, raw_key: str) -> Dict[str, Any]:
        p = dict(product)
        # Price/QPO with only that weight
        p["Price"] = {weight_key_norm: price_dict[raw_key]}
        qty = qpo_dict.get(raw_key, qpo_dict.get(weight_key_norm, product.get("Quantity Available", 0)))
        p["Quantity Per Option"] = {weight_key_norm: qty}
        p["Quantity Available"]  = qty
        p["Days on Shelf"] = product.get("Days on Shelf", 0)

        name = (p.get("Internal Product Name") or p.get("Product name") or "")
        p["SKU"] = f"{_slug(name)}-rosin-jar-{sku_suffix[weight_key_norm]}"
        return p

    # Index price keys by their canonical unit (so "each" → "1g", etc.)
    by_norm = {}
    for k in price_dict:
        norm = _canon_unit(k)
        by_norm.setdefault(norm, []).append(k)

    out: List[Dict[str, Any]] = []

    # Emit rows for each of 1g, 2g, 3g (if present)
    for w in target_weights:
        if w in by_norm and by_norm[w]:
            raw_key = by_norm[w][0]  # If multiple keys normalize to same unit, use first
            out.append(build_weight_clone(w, raw_key))

    # ---- Aggregate "other" weights (optional) ----
    # Keep any weights that are NOT 1g/2g/3g together in a single row
    other_prices = {}
    other_qpo = {}
    for raw_k, v in price_dict.items():
        norm = _canon_unit(raw_k)
        if norm not in target_weights:
            other_prices[raw_k] = v
            if raw_k in qpo_dict:
                other_qpo[raw_k] = qpo_dict[raw_k]

    if other_prices:
        p_other = dict(product)
        p_other["Price"] = other_prices
        p_other["Quantity Per Option"] = other_qpo
        if other_qpo:
            try:
                p_other["Quantity Available"] = sum(int(v) for v in other_qpo.values())
            except Exception:
                p_other["Quantity Available"] = product.get("Quantity Available", 0)
        p_other["Days on Shelf"] = product.get("Days on Shelf", 0)

        # Build a sensible SKU for the "others" bucket
        name = (p_other.get("Internal Product Name") or p_other.get("Product name") or "")
        p_other["SKU"] = f"{_slug(name)}-rosin-jar"
        out.append(p_other)

    # If nothing was split (unlikely), return original
    return out or [product]


def enhance_product_with_mapping(product: dict, company_name: str) -> dict:
    raw_name = product.get("Product name", "")
    internal_name = product.get("Internal Product Name", "").strip()

    # 🤖 AI-FIRST: Direct AI extraction when internal name is missing
    if not internal_name:
        product = ensure_internal_product_name(product)
        internal_name = product.get("Internal Product Name", "").strip()
        
        # 🔧 RULE-BASED FALLBACK: If AI fails, try rule-based extraction
        if not internal_name:
            from utils.internal_name_resolver import extract_candidate_internal_name
            candidate = extract_candidate_internal_name(raw_name)
            if candidate:
                key = candidate.lower()
                if key not in AUTO_PATTERNS:
                    save_auto_mapping(key, candidate)
                    log_mapping_event(
                        raw_product_name=raw_name,
                        normalized_key=key,
                        internal_name=candidate,
                        source="rule_based_fallback"
                    )
                    AUTO_PATTERNS[key] = candidate
                product["Internal Product Name"] = candidate
                internal_name = candidate

    # Existing logic continues untouched
    product = map_internal_type(product)
    sku = generate_sku(internal_name, product.get("Internal Product Type", ""))
    if sku:
        product["SKU"] = sku

    return product
                    
# def enhance_product_with_mapping(product: Dict[str, Any], company_name: str) -> Dict[str, Any]:
#     """Enhance product with internal mapping and SKU generation"""
#     if not product:
#         return product

#     # Get the first unit for mapping (or 'each' if no specific unit)
#     price_data = product.get("Price", {})
#     unit = next(iter(price_data.keys())) if price_data else "each"

#     # Get internal mapping
#     internal_name, internal_type = product_name_type_mapping(
#         product.get("Product name", ""),
#         company_name,
#         unit
#     )
#     # name = product.get("Product name", "").lower()

#     # if (
#     #     "donkey butter" in name
#     #     and (
#     #     re.search(r"\b\d+\s*[x×]\s*\d+(\.\d+)?\s*g\b", name)   # matches "7x0.5g"
#     #     or re.search(r"\b\d+\s*(?:1/2|1\/2)\s*g\b", name)      # matches "7 1/2g"
#     #     )
#     #     # and re.search(r"\b\d+\s*[x×]\s*\d+(\.\d+)?\s*g\b", name)
#     #     and "pre-roll" in name
#     # ):
#     #     product["Internal Product Name"] = "Donkey Butter"
#     #     product["Internal Product Type"] = "Preroll Multipack"
#     #     product["SKU"] = "donkeybutter-flower-preroll-multipack"
#     #     return product  #  prevents later mappings from overwriting

#     product_name_lower = product.get("Product name", "").lower()
#     category = product.get("Category", "").lower()

#     # === CUSTOM FIX FOR "LIVE ROSIN" ===
#     if "live rosin" in product_name_lower:
#         if (
#             any(cat in category for cat in ["vapes", "vaporizers", "vape", "cartridge", "concentrates", "concentrate", "extracts"])
#             and unit in ["0.5g", ".5g", "½g", "each", "1g"]
#         ):
#             internal_type = "Cart" 
#         else:
#             internal_type = "Rosin Jar"

#     # === HANDLE VAPE CART CATEGORY ===
#     if "vape carts" in category.lower():
#         if "rosin" in product_name_lower or "cart" in product_name_lower or "vape" in product_name_lower  or "vape carts" in category.lower():
#             internal_type = "Cart"  # Force classification to "Rosin Cart"
#         else:
#             internal_type = "Rosin Jar"

#     if category in ["concentrate", "concentrates", "extracts"]:
#         if "cart" not in product_name_lower:
#             internal_type = "Rosin Jar"
#         else:
#             internal_type = "Cart"

#     if category in ["flower bar", "flower jar"]:
#         internal_type = "Flower Jar"

#     # === FIX FOR "FLOWER" CATEGORY ===
#     if category == "flower":
#         if "bulk" in product_name_lower:
#             internal_type = "Flower Bulk"
#         else:
#             internal_type = "Flower Jar"

#     # === FIX FOR PRE-ROLL PRODUCTS ===
#     if category in ["pre-rolls", "prerolls", "pre rolls"]:
#         internal_type = "Preroll"

#     # === SCOPED FIX FOR "DULCE DE UVA | 1g Pre-roll" ===
#     if (
#         ("dulce de uva" in product_name_lower or "black maple" in product_name_lower)
#         and (category in ["pre-rolls", "pre-roll"])
#         and internal_type.lower() == "cart"
#     ):
#         internal_type = "Preroll"

#     if "moroccan peaches" in product_name_lower:
#         if category == "vape":
#             internal_type = "Cart"
#         elif category == "pre-roll":
#             internal_type = "Preroll"

#     # if "dulce de uva" in product_name_lower:
#     if category == "extract":
#         internal_type = "Rosin Jar"
#     elif category == "pre-roll":
#         internal_type = "Preroll"

#     # === SCOPED FIX FOR "DONKEY BUTTER | 1g Pre-roll" ===
#     if (
#         "donkey butter" in product_name_lower
#         and "pre-roll" in product_name_lower
#         and category == "pre-rolls"
#         and unit == "1g"
#         and internal_type.lower() == "flower jar"
#     ):
#         internal_type = "Preroll"

#     # === FIX FOR Rosin Jar SKU to handle "each" as "1" ===
#     if internal_type.lower() == "rosin jar" and unit.lower() == "each":
#         unit = "1"  # Force unit to '1' for Rosin Jar products

#     # Define stores for which Flower Jar → Flower Bulk rule applies
#     flower_bulk_stores = {"garcia's", "mothaplant","rimeline","sweetspot"}

#     normalized_store = normalize_string(company_name)

#     # Apply rule only if store is in our special list
#     if normalized_store in flower_bulk_stores:
#         if category.lower() in {"flower", "flower jar", "flower bulk", "flower bar"}:
#             if internal_type.lower() == "flower jar" or internal_type.lower() == "preroll":
#                 internal_type = "Flower Bulk"

#     if (
#         "donkey butter" in product_name_lower
#         and "2 pack" in product_name_lower
#         and category == "pre-rolls"
#         and internal_type.lower() == "preroll"
#     ):
#         product["Internal Product Name"] = "Donkey Butter"
#         product["Internal Product Type"] = "Preroll"
#         product["SKU"] = "donkeybutter-flower-preroll"
#         return product  # Skip further processing

#     # # === FIX: All multipacks should be flower-multipack SKU ===
#     # normalized_product_name = normalize_string(product.get("Product name", ""))

#     # # Special rule: 3-Strain Multipack → Donkey Butter Flower Multipack
#     # if "3 strain" in normalized_product_name and (
#     #     "multipack" in normalized_product_name or "multi pack" in normalized_product_name
#     # ):
#     #     product["Internal Product Name"] = "Donkey Butter"
#     #     product["Internal Product Type"] = "Flower Multipack"
#     #     product["SKU"] = "donkeybutter-flower-multipack"
#     #     return product  # Skip further processing
    
#     if (
#         "donkey butter" in product_name_lower
#         and "6pk" in product_name_lower
#         and category == "pre-rolls"
#     ):
#         product["Internal Product Name"] = "Donkey Butter"
#         product["Internal Product Type"] = "Preroll Multipack"
#         product["SKU"] = "donkeybutter-preroll-multipack"
#         return product  # Skip further processing
    
#     # if (
#     #     "donkey butter" in product_name_lower 
#     #     and "dogwalkers" in product_name_lower
#     #     and "7-pack ea" in product_name_lower
#     #     and category == "pre-rolls"
#     # ):
#     #     product["Internal Product Name"] = "Donkey Butter"
#     #     product["Internal Product Type"] = "Flower Multipack"
#     #     product["SKU"] = "donkeybutter-flower-multipack"
#     #     return product  # Skip further processing
    
#     # if (
#     #     "donkey butter" in product_name_lower 
#     #     and "7 count" in product_name_lower
#     #     and category == "preroll"
#     # ):
#     #     product["Internal Product Name"] = "Donkey Butter"
#     #     product["Internal Product Type"] = "Flower Multipack"
#     #     product["SKU"] = "donkeybutter-flower-multipack"
#     #     return product  # Skip further processing
#         # === GENERAL FIX: Donkey Butter multipacks (any format) ===
#     # nl = product_name_lower
#     # nl_nospace = nl.replace(" ", "")

#     # # treat "3 strain multipack" as Donkey Butter too (keeps your old rule)
#     # donkey_by_3strain = ("3-strain" in nl) and (
#     #     "multi pack" in nl or re.search(r"\bmulti\s*pack\b", nl)
#     # )

#     # is_donkey = ("donkeybutter" in nl_nospace) or ("donkey butter" in nl) or donkey_by_3strain

#     # # multipack indicators: "multipack", "multi pack", "6pk", "2 pack", "(7)", "7x0.5g", "dogwalkers", etc.
#     # is_multipack = (
#     #     "multipack" in nl
#     #     or re.search(r"\bmulti\s*pack\b", nl)
#     #     or re.search(r"\b\d+\s*(?:pack|pk)\b", nl)   # "2 pack", "6pk"
#     #     or re.search(r"\(\s*\d+\s*\)", nl)           # "(7)"
#     #     or re.search(r"\b\d+\s*[x×]\s*\d*", nl)      # "7x", "7x0.5g"
#     #     or "dogwalkers" in nl
#     #     or "7-pack" in nl
#     #     or "7 count" in nl
#     # )

#     # if is_donkey and is_multipack:
#     #     product["Internal Product Name"] = "Donkey Butter"
#     #     product["Internal Product Type"] = "Preroll Multipack"
#     #     product["SKU"] = "donkeybutter-flower-preroll-multipack"
#     #     return product
#     # === GENERAL FIX: Donkey Butter multipacks (all formats, includes your 7x/.5g pre-roll case) ===
#     name_raw = product.get("Product name", "")
#     nl = name_raw.lower()
#     nl_nospace = nl.replace(" ", "")
#     category_lower = (product.get("Category") or "").lower()

#     # treat "3 strain"/"3-strain" multipack as Donkey Butter too
#     donkey_by_3strain = (("3 strain" in nl) or ("3-strain" in nl)) and (
#         "multipack" in nl or re.search(r"\bmulti\s*pack\b", nl)
#     )

#     is_donkey = ("donkeybutter" in nl_nospace) or ("donkey butter" in nl) or donkey_by_3strain

#     # pre-roll indicators (name or category)
#     is_prerollish = (
#         "pre-roll" in nl or "pre roll" in nl or "preroll" in nl
#         or "pre-rolls" in nl or "prerolls" in nl or "pre rolls" in nl
#         or category_lower in ("pre-roll", "pre-rolls", "preroll", "prerolls", "pre rolls")
#     )

#     # weight-pattern multipack like "7x0.5g" or "7 1/2g" (your earlier condition)
#     has_weighted_x = (
#         re.search(r"\b\d+\s*[x×]\s*\d+(\.\d+)?\s*g\b", nl) is not None  # e.g. "7x0.5g"
#         or re.search(r"\b\d+\s*(?:1/2|1\/2)\s*g\b", nl) is not None     # e.g. "7 1/2g"
#     )

#     # generic multipack indicators
#     is_generic_multipack = (
#         "multipack" in nl
#         or re.search(r"\bmulti\s*pack\b", nl)
#         # or re.search(r"\b\d+\s*(?:pack|pk)\b", nl)     # "2 pack", "6pk"
#         or re.search(r"\(\s*\d+\s*\)", nl)             # "(7)"
#         or re.search(r"\b\d+\s*[x×]\s*\d*", nl)        # "7x", "7x0.5g"
#         or "7-pack" in nl
#         or "7 count" in nl
#         or "dogwalkers" in nl
#     )

#     # final multipack decision:
#     # - any generic multipack signal, OR
#     # - (pre-roll-ish AND the weighted '7x/.5g' etc. pattern)
#     is_multipack = is_generic_multipack or (is_prerollish and has_weighted_x)

#     if is_donkey and is_multipack:
#         product["Internal Product Name"] = "Donkey Butter"
#         product["Internal Product Type"] = "Preroll Multipack"
#         product["SKU"] = "donkeybutter-flower-preroll-multipack"
#         return product 
    
#     # === GENERAL FIX: Deathstar multipacks (any format) ===
#     nl = product_name_lower
#     nl_nospace = nl.replace(" ", "")
#     is_deathstar = ("deathstar" in nl_nospace) or ("death star" in nl)

#     # multipack indicators: "multipack", "multi pack", "7x", "(7)", "2 pack", etc.
#     is_multipack = (
#         "multipack" in nl
#         or re.search(r"\bmulti\s*pack\b", nl)
#         or re.search(r"\b\d+\s*pack\b", nl)         # "2 pack", "5 pack"
#         or re.search(r"\(\s*\d+\s*\)", nl)          # "(7)"
#         or re.search(r"\b\d+\s*[x×]\s*\d*", nl)     # "7x", "7x0.5g"
#     )

#     # === Dulce de Uva: ONLY 7 pk preroll → multipack SKU ===
#     nl = (product.get("Product name") or "").lower()
#     if ("dulce de uva" in nl) and re.search(r"\b7\s*pk\b", nl):
#         product["Internal Product Name"] = "Dulce de Uva"
#         product["Internal Product Type"] = "Preroll Multipack"
#         product["SKU"] = "dulcedeuva-flower-preroll-multipack"
#         return product

#     if is_deathstar and is_multipack:
#         product["Internal Product Name"] = "Deathstar"
#         product["Internal Product Type"] = "Preroll Multipack"
#         product["SKU"] = "deathstar-flower-preroll-multipack"
#         return product  #  stop here so nothing overwrites it

#     # Generate SKU
#     sku = generate_sku(internal_name, internal_type, unit)

#     # Update product
#     enhanced_product = product.copy()
#     enhanced_product["Internal Product Name"] = internal_name
#     enhanced_product["Internal Product Type"] = internal_type
#     enhanced_product["SKU"] = sku

#     # Initialize new fields if not present
#     if "Days on Shelf" not in enhanced_product:
#         enhanced_product["Days on Shelf"] = 0

#     return enhanced_product

def validate_product(product: Dict[str, Any]) -> bool:
    """Validate product data"""
    if not product.get("Product name", "").strip():
        return False
    if not product.get("Category", "").strip():
        return False
    if not product.get("Price") or not any(product["Price"].values() if isinstance(product["Price"], dict) else []):
        return False
    return True

def filter_by_categories(product_category: str, allowed_categories: List[str]) -> bool:
    """Check if product category should be included"""
    if not allowed_categories or "all" in [cat.lower() for cat in allowed_categories]:
        return True
    
    product_cat_normalized = product_category.lower().replace("-", "").replace(" ", "")
    
    return any(
        cat.lower().replace("-", "").replace(" ", "").rstrip("s") in product_cat_normalized
        for cat in allowed_categories
    )

def format_price(price: Any) -> str:
    """Format price consistently"""
    if isinstance(price, (int, float)):
        return f"${price:.2f}"
    elif isinstance(price, str):
        # Remove $ if already present and reformat
        clean_price = price.replace('$', '').strip()
        try:
            return f"${float(clean_price):.2f}"
        except ValueError:
            return str(price)
    return str(price)

def apply_tax(price: Any, store_cfg: dict) -> Any:
    """
    Ensure all prices are final after-tax.
    - If store has_after_tax = True → return as-is.
    - If not, multiply each price by (1 + tax_rate).
    """
    if store_cfg.get("has_after_tax", False):
        return price

    tax_rate = float(store_cfg.get("tax_rate", 0.20))  # default 20%

    if isinstance(price, dict):
        updated = {}
        for unit, p in price.items():
            try:
                clean = float(str(p).replace("$", "").strip())
                val_with_tax = clean * (1 + tax_rate)
                updated[unit] = f"${val_with_tax:.2f}"
            except Exception:
                updated[unit] = p  # fallback
        return updated
    else:
        # Handle single value (float or str)
        try:
            clean = float(str(price).replace("$", "").strip())
            return clean * (1 + tax_rate)
        except Exception:
            return price  # fallback

def save_products_by_date(products: List[Dict[str, Any]], file_path: str, company_name: str = ""):
    """Save products with today's date as key, enhanced with SKUs"""
    today = datetime.now().strftime("%Y-%m-%d")
    base_dir = Path(__file__).resolve().parent.parent  # This gets to your project root
    path = base_dir / file_path

    # Create directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Enhance products with internal mapping and SKUs
    enhanced_products = []
    for product in products:
        enhanced_product = enhance_product_with_mapping(product, company_name)
        # enhanced_products.append(enhanced_product)
        # Split Rosin Jar into (non-2g) + (2g-only) if 2g is present; otherwise returns [enhanced_product]
        split_items = split_rosin_jar_separate(enhanced_product)
        enhanced_products.extend(split_items)
    
    # Load existing data
    data = {}
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {}
    
    # Add today's data
    data[today] = enhanced_products
    
    # Save back
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    
    logging.info(f"Saved {len(enhanced_products)} enhanced products with SKUs to {file_path}")

def setup_logging():
    """Setup logging for the application"""
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create log file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f"scraper_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("main")

def get_google_drive_credentials():
    """Gets valid user credentials from storage"""
    creds = None
    token_file = 'token.pickle'
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            credentials_file = 'credentials.json'
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(f"Google credentials file not found: {credentials_file}")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    return creds

def upload_to_drive(file_path: str, folder_id: str = None) -> str:
    """Upload a file to Google Drive"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        creds = get_google_drive_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': os.path.basename(file_path)
        }
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = 'application/octet-stream' 
        
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        logging.info(f"Successfully uploaded {os.path.basename(file_path)} to Google Drive (ID: {file.get('id')})")
        return file.get('id')
            
    except Exception as e:
        logging.error(f"Error uploading file to Google Drive: {str(e)}")
        raise Exception(f"Error uploading file to Google Drive: {str(e)}")

def load_config(config_file: str) -> List[Dict[str, Any]]:
    """Load store configurations from JSON file"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            stores = json.load(f)
        
        # Filter enabled stores
        enabled_stores = [store for store in stores if store.get("Scrape", False)]
        
        logging.info(f"Loaded {len(enabled_stores)} enabled stores from {len(stores)} total")
        return enabled_stores
        
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {config_file}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in configuration file: {e}")
        return []
    
# ----------------------
# OZ → GRAMS converter
# ----------------------
OZ_TO_GRAM = 28.3495

def convert_oz_to_grams(unit: str):
    if not unit:
        return None
    u = unit.lower().replace(" ", "")
    if not u.endswith("oz"):
        return None

    value = u.replace("oz", "")  # remove oz

    try:
        if "/" in value:
            n, d = value.split("/")
            oz_val = float(n) / float(d)
        else:
            oz_val = float(value)
    except:
        return None

    grams = round(oz_val * OZ_TO_GRAM, 2)
    return f"{grams}g"
