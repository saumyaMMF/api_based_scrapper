import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from utils.data_processing import DataProcessor

def backfill_removed_products(start_date_str="2024-07-01", end_date_str=None):
    processor = DataProcessor()
    data_dir = Path(__file__).resolve().parent / "data_base"

    if end_date_str is None:
        end_date_str = datetime.now().strftime("%Y-%m-%d")

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    json_files = list(data_dir.glob("db_*.json"))
    all_backfilled = []

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        company_key = json_file.stem.replace("db_", "").lower()
        company_name = processor.company_name_mapping.get(company_key, company_key.title())

        available_dates = sorted(data.keys())
        for i in range(1, len(available_dates)):
            today = available_dates[i]
            yesterday = available_dates[i - 1]

            today_dt = datetime.strptime(today, "%Y-%m-%d")
            if not (start_date <= today_dt <= end_date):
                continue

            today_products = {item.get("SKU"): item for item in data[today] if item.get("SKU")}
            yesterday_products = {item.get("SKU"): item for item in data[yesterday] if item.get("SKU")}

            removed_keys = set(yesterday_products.keys()) - set(today_products.keys())

            for sku in removed_keys:
                item = yesterday_products[sku]
                row = {
                    "Product name": item.get("Product name"),
                    "Price": item.get("Price"),
                    "Days on Shelf": item.get("Days on Shelf", 0),
                    "THC": item.get("THC", ""),
                    "SKU": sku,
                    "Quantity Available": item.get("Quantity Available", 0),
                    "Quantity Per Option": item.get("Quantity Per Option", {}),
                    "Internal Product Name": item.get("Internal Product Name", ""),
                    "Internal Product Type": item.get("Internal Product Type", ""),
                    "Company Name": company_name,
                    "Removed Date": today
                }
                all_backfilled.append(row)

    if all_backfilled:
        print(f" Found {len(all_backfilled)} backfill rows. Appending...")
        processor.append_removed_products_log(all_backfilled, "__BACKFILL__")
    else:
        print("No backfill rows found.")

if __name__ == "__main__":
    backfill_removed_products(start_date_str="2024-07-01")
