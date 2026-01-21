#!/usr/bin/env python3
"""
Backfill missing keys in historical JSON data files.

This script adds missing keys from 2024 data that are present in 2025 data:
- Discount Price (default: {})
- THC (default: "N/A")
- Quantity Available (default: 0)
- Quantity Per Option (default: {})
- Internal Product Name (regenerated using enhance_product_with_mapping)
- Internal Product Type (regenerated using enhance_product_with_mapping)
- SKU (regenerated using enhance_product_with_mapping)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add the utils directory to the path so we can import common
sys.path.insert(0, str(Path(__file__).resolve().parent / "utils"))

from common import enhance_product_with_mapping

# Define the keys that should have default values
DEFAULT_KEYS = {
    "Discount Price": {},
    "THC": "N/A",
    "Quantity Available": 0,
    "Quantity Per Option": {},
}

# Keys that will be regenerated (not defaulted)
REGENERATE_KEYS = ["Internal Product Name", "Internal Product Type", "SKU"]

# Company name mapping (from data_processing.py)
COMPANY_NAME_MAPPING = {
    "31northvt": "31 North",
    "forbinsfinest": "Forbin's Reserve",
    "freedomflower": "Freedom Flower, LLC",
    "garciascannabis": "Garcia's",
    "gasstationvt": "The Gas Station",
    "gramcentral": "Gram Central",
    "greenmountaincannabisworks": "GMCW",
    "kushies": "Kushies",
    "magicmann": "Magic Mann",
    "miltonremedies": "Milton Remedies",
    "mothaplant": "Mothaplant",
    "polestarvt": "Polestar",
    "rimeline": "Rimeline",
    "somethingwickedcannabis": "Something Wicked Cannabis",
    "somewhereonthemountain": "Somewhere on the Mountain",
    "sweetspotfarms": "Sweet Spot",
    "thebudstop": "The Bud Stop",
    "valleymeade": "Valleymeade",
    "vtsundaydrive": "Sunday Drive",
    "capitalcannabisvt": "Capital Cannabis",
    "floravt": "Flora",
    "cambridgecannabiscompany": "Cambridge",
    "cloud9vt": "Cloud9",
    "pinegroveorganics.org": "Pine Grove Organics",
    "teahousevt": "The Tea House",
    "rollingtwenties": "Rolling Twenties",
    "mountaingirlcannabis": "Mountain Girl",
    "higherelevation": "Higher Elevation",
    "poultneycannabissupplyvt": "Poultney Cannabis Supply"
}

def get_company_name_from_filename(filename: str) -> str:
    """Extract company name from filename"""
    raw_name = filename.replace("db_", "").replace(".json", "").lower()
    return COMPANY_NAME_MAPPING.get(raw_name, raw_name.title())

def backfill_product_entry(product: Dict[str, Any], company_name: str) -> tuple[Dict[str, Any], int]:
    """
    Add missing keys to a product entry.
    
    Args:
        product: Product dictionary
        company_name: Name of the company/store
        
    Returns:
        Tuple of (updated product dictionary, number of keys added)
    """
    keys_added = 0
    
    # Add default values for simple keys
    for key, default_value in DEFAULT_KEYS.items():
        if key not in product:
            product[key] = default_value
            keys_added += 1
    
    # Check if regeneration is needed
    needs_regeneration = any(key not in product or not product.get(key) for key in REGENERATE_KEYS)
    
    if needs_regeneration:
        # Use the enhance_product_with_mapping function to regenerate these fields
        try:
            enhanced = enhance_product_with_mapping(product, company_name)
            
            # Update the product with regenerated fields
            for key in REGENERATE_KEYS:
                if key not in product or not product.get(key):
                    product[key] = enhanced.get(key, "")
                    keys_added += 1
        except Exception as e:
            print(f"  ⚠️  Warning: Could not regenerate fields for product '{product.get('Product name', 'Unknown')}': {e}")
            # Fallback to empty strings
            for key in REGENERATE_KEYS:
                if key not in product:
                    product[key] = ""
                    keys_added += 1
    
    return product, keys_added

def backfill_json_file(file_path: Path, dry_run: bool = False) -> Dict[str, int]:
    """
    Backfill missing keys in a single JSON file.
    
    Args:
        file_path: Path to the JSON file
        dry_run: If True, don't save changes, just report what would be done
        
    Returns:
        Dictionary with statistics about the backfill operation
    """
    stats = {
        "total_dates": 0,
        "total_products": 0,
        "products_updated": 0,
        "keys_added": 0
    }
    
    company_name = get_company_name_from_filename(file_path.name)
    
    try:
        # Load the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stats["total_dates"] = len(data)
        
        # Iterate through each date
        for date_key, products in data.items():
            if not isinstance(products, list):
                continue
                
            # Iterate through each product
            for product in products:
                stats["total_products"] += 1
                
                # Backfill the product
                _, keys_added = backfill_product_entry(product, company_name)
                
                if keys_added > 0:
                    stats["products_updated"] += 1
                    stats["keys_added"] += keys_added
        
        # Save the updated data if not a dry run
        if not dry_run and stats["products_updated"] > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f" Updated: {file_path.name}")
        elif dry_run and stats["products_updated"] > 0:
            print(f"🔍 Would update: {file_path.name}")
        else:
            print(f"⏭️  No changes needed: {file_path.name}")
            
    except Exception as e:
        print(f" Error processing {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    return stats

def backfill_all_files(data_dir: str = "data_base", dry_run: bool = False):
    """
    Backfill missing keys in all JSON files in the data directory.
    
    Args:
        data_dir: Directory containing the JSON files
        dry_run: If True, don't save changes, just report what would be done
    """
    # Get the project root directory
    script_dir = Path(__file__).resolve().parent
    data_path = script_dir / data_dir
    
    if not data_path.exists():
        print(f" Data directory not found: {data_path}")
        return
    
    # Find all JSON files
    json_files = list(data_path.glob("db_*.json"))
    
    if not json_files:
        print(f" No JSON files found in {data_path}")
        return
    
    print(f"Found {len(json_files)} JSON files to process")
    print(f"Mode: {'DRY RUN (no changes will be saved)' if dry_run else 'LIVE (files will be updated)'}")
    print(f"\nDefault keys: {list(DEFAULT_KEYS.keys())}")
    print(f"Regenerated keys: {REGENERATE_KEYS}")
    print("=" * 80)
    
    # Process each file
    total_stats = {
        "files_processed": 0,
        "files_updated": 0,
        "total_dates": 0,
        "total_products": 0,
        "products_updated": 0,
        "keys_added": 0
    }
    
    for json_file in sorted(json_files):
        stats = backfill_json_file(json_file, dry_run=dry_run)
        
        if stats:
            total_stats["files_processed"] += 1
            if stats["products_updated"] > 0:
                total_stats["files_updated"] += 1
            total_stats["total_dates"] += stats["total_dates"]
            total_stats["total_products"] += stats["total_products"]
            total_stats["products_updated"] += stats["products_updated"]
            total_stats["keys_added"] += stats["keys_added"]
            
            # Print detailed stats for this file
            if stats["products_updated"] > 0:
                print(f"  📊 Dates: {stats['total_dates']}, "
                      f"Products: {stats['total_products']}, "
                      f"Updated: {stats['products_updated']}, "
                      f"Keys added: {stats['keys_added']}")
    
    # Print summary
    print("=" * 80)
    print("\n📈 SUMMARY:")
    print(f"  Files processed: {total_stats['files_processed']}")
    print(f"  Files updated: {total_stats['files_updated']}")
    print(f"  Total dates: {total_stats['total_dates']}")
    print(f"  Total products: {total_stats['total_products']}")
    print(f"  Products updated: {total_stats['products_updated']}")
    print(f"  Keys added: {total_stats['keys_added']}")
    
    if dry_run:
        print("\n⚠️  This was a DRY RUN. No files were modified.")
        print("   Run with --live to apply changes.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill missing keys in JSON database files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode (default, don't save changes)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live mode (actually save changes)"
    )
    parser.add_argument(
        "--data-dir",
        default="data_base",
        help="Directory containing JSON files (default: data_base)"
    )
    
    args = parser.parse_args()
    
    # If --live is specified, turn off dry-run
    dry_run = not args.live
    
    # Run the backfill
    backfill_all_files(data_dir=args.data_dir, dry_run=dry_run)