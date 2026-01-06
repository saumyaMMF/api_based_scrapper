"""Data processing and comparison utilities - Fixed with email notifications"""

import json
import pandas as pd
import csv
import re
import numpy as np
import os
import ssl
import platform
import certifi
import smtplib
import mimetypes
import pickle
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
from email.message import EmailMessage
from io import BytesIO
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from glob import glob
import re
from decimal import Decimal, getcontext, ROUND_HALF_UP
from utils.df_to_db_upload import upload_dataframe,align_to_rhize_main_schema
# import sys
# from pathlib import Path
# # Add project root (parent folder of utils/) to import path
# ROOT_DIR = Path(__file__).resolve().parent.parent
# sys.path.append(str(ROOT_DIR))

# Add your email configuration import here
import mail_cfg
print(f"mail_cfg loaded: {mail_cfg.user}")

# Google Drive scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class DataProcessor:
    def __init__(self):
        self.excel_buffer = None
        self.message = None
        self.context = None
        self.sender_user = None
        self.sender_pw = None
        self.sender_name = "Menu Scraping"
        self.company_name_mapping = {
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
            "pinegroveorganics.org":"Pine Grove Organics",
            "teahousevt":"The Tea House",
            "rollingtwenties": "Rolling Twenties",
            "mountaingirlcannabis": "Mountain Girl",
            "higherelevation":"Higher Elevation",
        }
        
    def load_all_company_data(self, data_dir: str = "data_base") -> Dict[str, Dict[str, List[Dict]]]:
        """Load all company data organized by company and date"""
        project_root = Path(__file__).resolve().parent.parent  # go up one level
        data_path = project_root / data_dir
        # data_path = Path(data_dir)
        all_data = {}
                    
        for json_file in data_path.glob("db_*.json"):
            # Extract company name from filename
            raw_name = json_file.stem.replace("db_", "").lower()
            company_name = self.company_name_mapping.get(raw_name)
            if not company_name:
                name_with_spaces = re.sub(r'(\d+)([a-zA-Z])', r'\1 \2', raw_name)
                name_with_spaces = re.sub(r'([a-z])([A-Z])', r'\1 \2', name_with_spaces)
                company_name = name_with_spaces.title()
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    company_data = json.load(f)
                # print(f"Loaded keys for {company_name}: {list(company_data.keys())}")
                all_data[company_name] = company_data
            except Exception as e:
                logging.error(f"Error loading {json_file}: {e}")
        print(f"Total companies loaded: {len(all_data)}")
        return all_data

    def get_latest_products(self, data_dir: str = "data_base") -> Dict[str, List[Dict]]:
        """Get latest products for all companies"""
        today = datetime.now().strftime("%Y-%m-%d")
        all_data = self.load_all_company_data(data_dir)
        
        latest_products = {}
        for company, dates_data in all_data.items():
            if today in dates_data:
                latest_products[company] = dates_data[today]
        print(f"Looking for date: {today}")
        return latest_products

    def compare_with_yesterday(self, data_dir: str = "data_base") -> Dict[str, Any]:
        """Compare today's data with yesterday's using SKU-based comparison with shelf life tracking and flag updates."""
        today_date = datetime.now()
        yesterday_date = today_date - timedelta(days=1)
        today = today_date.strftime("%Y-%m-%d")
        yesterday = yesterday_date.strftime("%Y-%m-%d")

        project_root = Path(__file__).resolve().parent.parent
        data_path = project_root / data_dir
        comparison_results = {}
        ret = []
        removed_products_all = []

        for json_file in data_path.glob("db_*.json"):
            raw_key = json_file.stem.replace("db_", "").lower()
            company_name = self.company_name_mapping.get(raw_key, raw_key.title())

            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                yesterday_products = {}
                today_products = {}
                excel_data = []
                company_logs = []  # logs specific to this company

                keys = list(data.keys())

                if len(keys) >= 2:
                    y_date = keys[-2]
                    if y_date in data:
                        for item in data[y_date]:
                            sku = item.get("SKU", "")
                            if sku:
                                yesterday_products[sku] = {
                                    "Product name": item["Product name"],
                                    "Price": item["Price"],
                                    "Discount Price": item.get("Discount Price", {}),
                                    "Days on Shelf": item.get("Days on Shelf", 0),
                                    "THC": item.get("THC", "N/A"),
                                    "SKU": sku,
                                    "Quantity Available": item.get("Quantity Available", 0),
                                    "Quantity Per Option": item.get("Quantity Per Option", {}),
                                    "Internal Product Name": item.get("Internal Product Name", ""),
                                    "Internal Product Type": item.get("Internal Product Type", "")
                                }

                if today in data:
                    for item in data[today]:
                        sku = item.get("SKU", "")
                        if sku:
                            today_products[sku] = {
                                "Product name": item["Product name"],
                                "Price": item["Price"],
                                "Discount Price": item.get("Discount Price", {}),
                                "Days on Shelf": item.get("Days on Shelf", 0),
                                "THC": item.get("THC", "N/A"),
                                "SKU": sku,
                                "Quantity Available": item.get("Quantity Available", 0),
                                "Quantity Per Option": item.get("Quantity Per Option", {}),
                                "Internal Product Name": item.get("Internal Product Name", ""),
                                "Internal Product Type": item.get("Internal Product Type", "")
                            }
                else:
                    continue

                for sku in today_products:
                    if sku in yesterday_products:
                        shelf_life_days = (today_date - datetime.strptime(y_date, '%Y-%m-%d')).days
                        today_products[sku]["Days on Shelf"] = shelf_life_days + yesterday_products[sku]["Days on Shelf"]

                for sku in today_products:
                    for entry in data[today]:
                        if entry.get("SKU", "") == sku:
                            entry["Days on Shelf"] = today_products[sku]["Days on Shelf"]
                            break

                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f" Updated 'Days on Shelf' values saved back to: {json_file}")
                logging.info(f"Updated JSON file with new Days on Shelf values: {json_file}")

                added_products = []
                removed_products = []
                updated_products = []

                added_keys = set(today_products.keys()) - set(yesterday_products.keys())
                removed_keys = set(yesterday_products.keys()) - set(today_products.keys())

                # REMOVED
                for sku in yesterday_products:
                    if sku not in today_products:
                        print(f"-->Removed SKU: {sku}, Product: {yesterday_products[sku]['Product name']}, Details: {yesterday_products[sku]}")
                        company_logs.append(f"--><b>Removed</b> SKU: {sku}, Product: {yesterday_products[sku]['Product name']}, <b>Details</b>: {yesterday_products[sku]}")
                        product = yesterday_products[sku]
                        removed_products.append({
                            "key": sku,
                            "sku": sku,
                            "product_name": product.get("Product name", ""),
                            "price": product.get("Price", {}),
                            "quantity": product.get("Quantity Available", 0)
                        })
                        quantity_history = self.get_recent_quantity_snapshots(data, sku, today)  # unchanged
                        product["Company Name"] = company_name
                        product["Removed Date"] = today
                        removed_products_all.append(product)

                        excel_data.append({
                            "Company Name": company_name,
                            "SKU": sku,
                            "Product name": product['Product name'],
                            "THC": product["THC"],
                            "Details": product,
                            "Price": product["Price"],
                            "Discount Price": product.get("Discount Price", {}),
                            "Quantity Available": product["Quantity Available"],
                            "Quantity Per Option": product["Quantity Per Option"],
                            "1d": quantity_history["1d"],                 # NEW
                            "3 Days": quantity_history["3 Days"],
                            "7 Days": quantity_history["7 Days"],
                            "14+": quantity_history["14+"],
                            "Prev": quantity_history["Prev"],   # 👈 NEW
                            "Internal Product Name": product["Internal Product Name"],
                            "Internal Product Type": product["Internal Product Type"],
                            "Days on Shelf": product["Days on Shelf"],
                            "Flag": "Removed",
                            "Quantity History": quantity_history.get("Per Unit", {})
                        })

                # ADDED
                for sku in today_products:
                    if sku not in yesterday_products:
                        print(f"-->Added SKU: {sku}, Product: {today_products[sku]['Product name']}, Details: {today_products[sku]}")
                        company_logs.append(f"--><b>Added</b> SKU: {sku}, Product: {today_products[sku]['Product name']}, <b>Details</b>: {today_products[sku]}")
                        product = today_products[sku]
                        added_products.append({
                            "key": sku,
                            "sku": sku,
                            "product_name": product.get("Product name", ""),
                            "price": product.get("Price", {}),
                            "quantity": product.get("Quantity Available", 0)
                        })
                        # NEW: clip history at 'yesterday' for brand-new SKUs so 3d/7d/14+ are 0
                        quantity_history = self.get_recent_quantity_snapshots(data, sku, today, since_date=yesterday)

                        excel_data.append({
                            "Company Name": company_name,
                            "SKU": sku,
                            "Product name": product['Product name'],
                            "THC": product["THC"],
                            "Details": product,
                            "Price": product["Price"],
                            "Discount Price": product.get("Discount Price", {}),
                            "Quantity Available": product["Quantity Available"],
                            "Quantity Per Option": product["Quantity Per Option"],
                            "1d": quantity_history["1d"],                 # NEW
                            "3 Days": quantity_history["3 Days"],
                            "7 Days": quantity_history["7 Days"],
                            "14+": quantity_history["14+"],
                            "Prev": quantity_history["Prev"],   # 👈 NEW
                            "Internal Product Name": product["Internal Product Name"],
                            "Internal Product Type": product["Internal Product Type"],
                            "Days on Shelf": product["Days on Shelf"],
                            "Flag": "Added",
                            "Quantity History": quantity_history.get("Per Unit", {})
                        })
                    else:
                        # Only add "No Change" row if price hasn't changed
                        if sku not in yesterday_products or yesterday_products[sku]["Price"] == today_products[sku]["Price"]:
                            quantity_history = self.get_recent_quantity_snapshots(data, sku, today)
                            excel_data.append({
                                "Company Name": company_name,
                                "SKU": sku,
                                "Product name": today_products[sku]['Product name'],
                                "THC": today_products[sku]["THC"],
                                "Details": today_products[sku],
                                "Price": today_products[sku]["Price"],
                                "Discount Price": today_products[sku].get("Discount Price", {}),
                                "Quantity Available": today_products[sku]["Quantity Available"],
                                "Quantity Per Option": today_products[sku]["Quantity Per Option"],
                                "1d": quantity_history["1d"],                 # NEW
                                "3 Days": quantity_history["3 Days"],
                                "7 Days": quantity_history["7 Days"],
                                "14+": quantity_history["14+"],
                                "Prev": quantity_history["Prev"],   # 👈 NEW
                                "Internal Product Name": today_products[sku]["Internal Product Name"],
                                "Internal Product Type": today_products[sku]["Internal Product Type"],
                                "Days on Shelf": today_products[sku]["Days on Shelf"],
                                "Flag": "No Change",
                                "Quantity History": quantity_history.get("Per Unit", {})
                            })

                # UPDATED
                for sku in yesterday_products:
                    if sku in today_products:
                        if yesterday_products[sku]["Price"] != today_products[sku]["Price"]:
                            dict1 = yesterday_products[sku]
                            dict2 = today_products[sku]
                            diff = {key: (dict1.get(key), dict2.get(key)) for key in set(dict1.keys()) | set(dict2.keys()) if dict1.get(key) != dict2.get(key)}
                            print(f"-->Updated SKU: {sku}, Product: {today_products[sku]['Product name']}, <b>Details</b>: {diff}")
                            company_logs.append(f"--><b>Updated</b> SKU: {sku}, Product: {today_products[sku]['Product name']}, <b>Details</b>: {diff}")
                            updated_products.append({
                                "key": sku,
                                "sku": sku,
                                "product_name": dict2.get("Product name", ""),
                                "changes": diff
                            })

                            quantity_history = self.get_recent_quantity_snapshots(data, sku, today)
                            excel_data.append({
                                "Company Name": company_name,
                                "SKU": sku,
                                "Product name": today_products[sku]['Product name'],
                                "THC": today_products[sku]["THC"],
                                "Details": diff,
                                "Price": today_products[sku]["Price"],
                                "Discount Price": today_products[sku].get("Discount Price", {}),
                                "Quantity Available": today_products[sku]["Quantity Available"],
                                "Quantity Per Option": today_products[sku]["Quantity Per Option"],
                                "1d": quantity_history["1d"],
                                "3 Days": quantity_history["3 Days"],
                                "7 Days": quantity_history["7 Days"],
                                "14+": quantity_history["14+"],
                                "Prev": quantity_history["Prev"],
                                "Internal Product Name": today_products[sku]["Internal Product Name"],
                                "Internal Product Type": today_products[sku]["Internal Product Type"],
                                "Days on Shelf": today_products[sku]["Days on Shelf"],
                                "Flag": "Updated",
                                "Quantity History": quantity_history.get("Per Unit", {})
                            })

                if excel_data:
                    df = pd.DataFrame(excel_data)
                    comparison_dir = Path("notification_excel")
                    comparison_dir.mkdir(exist_ok=True)
                    base_name = json_file.stem
                    excel_file_path = comparison_dir / f"{base_name}_product_comparison.xlsx"
                    df.to_excel(excel_file_path, index=False)
                    logging.info(f"Created comparison Excel for {company_name}: {excel_file_path}")

                if company_logs:
                    company_log_text = "<br>".join(company_logs)
                    ret.append(f"<b>Website: {company_name}</b><br>Date: {today}<br>{company_log_text}<br><br>")

                comparison_results[company_name] = {
                    "added": len(added_keys),
                    "removed": len(removed_keys),
                    "updated": len(updated_products),
                    "total_today": len(today_products),
                    "total_yesterday": len(yesterday_products),
                    "changes": {
                        "added_products": added_products,
                        "removed_products": removed_products,
                        "updated_products": updated_products
                    }
                }

            except Exception as e:
                logging.error(f"Error processing {json_file}: {e}")
                continue

        if ret:
            tmp = "<br>".join(ret)
            return tmp, comparison_results, removed_products_all
        else:
            return None, comparison_results, removed_products_all
      
    def append_removed_products_log(self, removed_rows: List[Dict[str, Any]], date_str: str, filename: str = "removed_products_log.xlsx"):
        if not removed_rows:
            print("No removed products to log.")
            return

        # Add today's date to each row
        for row in removed_rows:
            if "Removed Date" not in row or not row["Removed Date"]:
                row["Removed Date"] = date_str

        new_df = pd.DataFrame(removed_rows)

        # Create folder if not exists
        project_root = Path(__file__).resolve().parent.parent
        log_folder = project_root / "removed_logs"
        log_folder.mkdir(parents=True, exist_ok=True)

        output_file = log_folder / filename

        if output_file.exists():
            existing_df = pd.read_excel(output_file)

            # Drop any rows for today's date
            cleaned_df = existing_df[existing_df["Removed Date"] != date_str]

            # Append today's fresh data
            final_df = pd.concat([cleaned_df, new_df], ignore_index=True)
        else:
            final_df = new_df

        # Ensure Removed Date is the first column
        columns = ["Removed Date"] + [col for col in final_df.columns if col != "Removed Date"]
        final_df = final_df[columns]
        final_df.sort_values(by="Removed Date", ascending=False, inplace=True)

        final_df.to_excel(output_file, index=False)

    def transform_unit_data(self, input_data, value_key="Value"):
        """Generic transformation for unit-based dicts (e.g., price, quantity) to list of {Unit, Value} dicts."""
        if isinstance(input_data, str):
            try:
                data_dict = json.loads(input_data.replace("'", '"'))
            except:
                try:
                    data_dict = eval(input_data)
                except:
                    return [{"Unit": "each", value_key: input_data}]
        elif isinstance(input_data, dict):
            data_dict = input_data
        else:
            return [{"Unit": "each", value_key: str(input_data)}]

        entries = []
        for unit, val in data_dict.items():
            entries.append({
                "Unit": unit,
                value_key: val
            })

        return entries

    def get_category(self, product_type):
        """Get category based on product type"""
        pt = str(product_type).strip().lower()
        if pt in ['cart', 'cartridge']:
            return 'Rosin'
        elif 'rosin' in pt:
            return 'Rosin'
        elif 'preroll' in pt:
            return 'Flower'
        elif 'flower' in pt or pt in ['jar', 'bulk', 'preroll']:
            return 'Flower'
        elif 'edible' in pt:
            return 'Edibles'
        elif 'accessory' in pt:
            return 'Accessory'
        else:
            return 'Unknown'

    def product_name_and_company_grouping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Group products by internal name and type, generate SKUs"""
        # Use Internal Product Type if available, otherwise fall back to Product Type
        type_column = 'Internal Product Type' if 'Internal Product Type' in df.columns else 'Product Type'
        name_column = 'Internal Product Name' if 'Internal Product Name' in df.columns else 'Product Name'
        
        # Normalize Product Type for comparison
        df['Normalized Product Type'] = df[type_column].str.strip().str.lower()

        # Split the dataframe
        rosin_jar_df = df[df['Normalized Product Type'] == 'rosin jar'].copy()
        others_df = df[df['Normalized Product Type'] != 'rosin jar'].copy()

        # Group based on availability of data
        grouped_dfs = []
        
        # Handle Rosin Jar with unit grouping
        if not rosin_jar_df.empty:
            rosin_jar_df['Normalized Unit'] = rosin_jar_df['Unit'].astype(str).str.strip().str.lower().str.replace(" ", "").str.replace("-", "")
            rosin_grouped = rosin_jar_df.groupby([name_column, type_column, 'Normalized Unit'])['Company Name'].unique().reset_index()
            rosin_grouped.columns = [name_column, type_column, 'Unit', 'Company Name']
            grouped_dfs.append(rosin_grouped)

        # Handle others without unit grouping
        if not others_df.empty:
            others_grouped = others_df.groupby([name_column, type_column])['Company Name'].unique().reset_index()
            others_grouped['Unit'] = None  # Placeholder for compatibility
            others_grouped = others_grouped[[name_column, type_column, 'Company Name', 'Unit']]
            grouped_dfs.append(others_grouped)

        # Combine both groupings
        if grouped_dfs:
            grouped_store = pd.concat(grouped_dfs, ignore_index=True)
            grouped_store['Normalized Product Type'] = grouped_store[type_column].str.strip().str.lower()

            # Format Company Names as comma-separated string
            grouped_store['Company Name'] = grouped_store['Company Name'].apply(
                lambda x: ', '.join(sorted(set(x))) if isinstance(x, (list, set, np.ndarray)) else x
            )

            # Generate SKUs
            skus = []
            for _, row in grouped_store.iterrows():
                name = str(row[name_column]).strip().lower().replace(" ", "").replace("-", "")
                ptype = str(row[type_column]).strip().lower().replace(" ", "").replace("-", "")
                raw_unit = str(row['Unit']).strip().lower().replace(" ", "").replace("-", "") if row['Unit'] else ""

                # Normalize type
                if ptype == "preroll":
                    type_part = "flower-preroll"
                elif ptype in ["cart", "cartridge"]:
                    type_part = "rosin-cart"
                elif ptype.endswith("jar"):
                    base = ptype[:-3]
                    type_part = f"{base}-jar"
                elif ptype.endswith("bulk"):
                    base = ptype[:-4]
                    type_part = f"{base}-bulk"
                else:
                    type_part = ptype

                # Normalize unit only for Rosin Jar
                if row['Normalized Product Type'] == "rosin jar":
                    numeric_part = re.findall(r"[\d/\.]+", raw_unit)
                    if numeric_part:
                        unit_str = numeric_part[0]
                        if "/" in unit_str:
                            unit_final = unit_str
                        else:
                            try:
                                val = float(unit_str)
                                if val == 0.5:
                                    unit_final = ".5"
                                elif val == 3.5:
                                    unit_final = "3"
                                else:
                                    unit_final = str(int(val)) if val.is_integer() else str(val)
                            except:
                                unit_final = unit_str
                    else:
                        unit_final = raw_unit
                    sku = f"{name}-{type_part}-{unit_final}"
                else:
                    sku = f"{name}-{type_part}"
                skus.append(sku)

            grouped_store['SKU'] = skus
            grouped_store['Company Name'] = grouped_store['Company Name'].apply(lambda x: str(x))
            grouped_store = (
                grouped_store
                .groupby('SKU', as_index=False)
                .agg({
                    name_column: 'first',            # keep first display name
                    type_column: 'first',            # keep first display type
                    'Company Name': lambda s: ', '.join(sorted(set(sum([v.split(', ') for v in s], []))))
                })
            )
            # grouped_store = grouped_store.drop(columns=['Unit', 'Normalized Product Type'])
            grouped_store = grouped_store.drop(columns=['Unit', 'Normalized Product Type'], errors='ignore')
            grouped_store['Category'] = grouped_store[type_column].apply(self.get_category)
            grouped_store['Type'] = grouped_store[type_column].apply(
                lambda t: (
                    'Cart'      if str(t).strip().lower() in ('cart', 'cartridge') else
                    'Preroll'   if 'preroll'   in str(t).lower() else
                    'Jar'       if 'jar'       in str(t).lower() else
                    'Bulk'      if 'bulk'      in str(t).lower() else
                    'Edible'    if 'edible'    in str(t).lower() else
                    'Accessory' if 'accessory' in str(t).lower() else
                    str(t).strip().title()
                )
            )
            grouped_store = grouped_store[[name_column, type_column,'Category', 'Type', 'Company Name', 'SKU']]

            return grouped_store
        else:
            return pd.DataFrame(columns=[name_column, type_column,'Category', 'Type', 'Company Name', 'SKU'])
        
    def get_recent_quantity_snapshots(
        self,
        company_data: Dict[str, List[Dict]],
        sku: str,
        reference_date: str,
        since_date: str = None  # optional lower bound to clip history (used for "Added" rows)
    ) -> Dict[str, Any]:
        """
        Calendar-anchored history (per unit):
        - 1d     = value on reference_date (or latest <= that date)
        - 3 Days = value on (reference_date - 3 days) (or latest <= that date)
        - 7 Days = value on (reference_date - 7 days)
        - 14+    = value on (reference_date - 14 days)

        Flower Jar/Bulk are treated as total-mode and stored under unit 'each'.
        If since_date is provided, entries before since_date are ignored.
        """
        def _to_int(x, default=0):
            try:
                return int(x)
            except Exception:
                try:
                    return int(float(x))
                except Exception:
                    return default

        def _pick_on_or_before(day_map: Dict[datetime, int], target_dt: datetime) -> int:
            # return the value at the latest date <= target_dt, else 0
            keys = [d for d in day_map.keys() if d <= target_dt]
            if not keys:
                return 0
            return day_map[max(keys)]

        ref_date = datetime.strptime(reference_date, "%Y-%m-%d")
        since_dt = datetime.strptime(since_date, "%Y-%m-%d") if since_date else None

        # target dates for buckets
        targets = {
            "1d": ref_date,
            "Prev": ref_date - timedelta(days=1),
            "3 Days": ref_date - timedelta(days=3),
            "7 Days": ref_date - timedelta(days=7),
            "14+": ref_date - timedelta(days=14),
        }

        # unit -> { date: qty }  (dates are datetime objects)
        per_unit_day_map: Dict[str, Dict[datetime, int]] = {}

        # collect & sort parseable dates
        all_dates: List[datetime] = []
        for ds in company_data.keys():
            try:
                all_dates.append(datetime.strptime(ds, "%Y-%m-%d"))
            except ValueError:
                continue
        all_dates.sort()

        # build daily maps per unit
        for d in all_dates:
            if d > ref_date:
                continue  # ignore future
            if since_dt and d < since_dt:
                continue  # clip older history when requested

            entries = company_data.get(d.strftime("%Y-%m-%d"), [])
            for entry in entries:
                if entry.get("SKU") != sku:
                    continue

                product_type = str(entry.get("Internal Product Type", "")).strip().lower()
                is_flower_total = product_type in ("flower jar", "flower bulk")

                if is_flower_total:
                    total_q = _to_int(entry.get("Quantity Available", 0), 0)
                    per_unit_day_map.setdefault("each", {})[d] = total_q
                    continue

                qpo = entry.get("Quantity Per Option", {})
                if isinstance(qpo, dict) and qpo:
                    for unit_raw, qty in qpo.items():
                        unit = str(unit_raw).strip()
                        qv = _to_int(qty, 0)
                        per_unit_day_map.setdefault(unit, {})[d] = qv
                else:
                    total_q = _to_int(entry.get("Quantity Available", 0), 0)
                    per_unit_day_map.setdefault("each", {})[d] = total_q

        # produce calendar-anchored buckets
        result = {"1d": {}, "Prev": {},"3 Days": {}, "7 Days": {}, "14+": {}}
        for unit, day_map in per_unit_day_map.items():
            result["1d"][unit]     = _pick_on_or_before(day_map, targets["1d"])
            result["Prev"][unit]   = _pick_on_or_before(day_map, targets["Prev"])
            result["3 Days"][unit] = _pick_on_or_before(day_map, targets["3 Days"])
            result["7 Days"][unit] = _pick_on_or_before(day_map, targets["7 Days"])
            result["14+"][unit]    = _pick_on_or_before(day_map, targets["14+"])

        # ensure keys exist for units we might expect even if empty
        if not per_unit_day_map:
            # no data at all for this sku
            return {"1d": {}, "3 Days": {}, "7 Days": {}, "14+": {}}

        return result

    @staticmethod
    def normalize_unit_string(unit: str) -> str:
        getcontext().prec = 12  # safe precision
        OZ_TO_G = Decimal("28.3495")
        FLOZ_TO_G = Decimal("29.5735")   # fluid ounce (water density)
        if not unit:
            return ""
        u = re.sub(r'[\s-]', '', str(unit).lower())

        # strip suffixes
        # u = re.sub(r'(cartridge|cart)$', '', u)
        # u = re.sub(r'[\s-]', '', str(unit).lower())
        # strip common non-unit suffixes
        u = re.sub(r'(cartridge|cart|distillate|preroll|bucket|concentrate|ofediblethc|vape|prepack|infusedpreroll|blunt)$', '', u)

        # mg normalization
        m = re.match(r'^(\d+(?:\.\d+)?)(mg|milligram|milligrams)$', u)
        if m:
            val = Decimal(m.group(1))
            return f"{val.normalize()}mg"

        # g normalization (numeric only)
        m = re.match(r'^(\d+(?:\.\d+)?)(g|gram|grams)?$', u)
        if m:
            val = Decimal(m.group(1))
            s = str(val.normalize())
            if s.startswith("0."):
                s = s[1:]  # keep your .x style for plain grams
            return f"{s}g"
        
        def _plain_decimal_str(d: Decimal) -> str:
            """
            Format a Decimal without scientific notation, trimming trailing zeros.
            Examples:
            Decimal('100.0') -> '100'
            Decimal('0.50')  -> '0.5'
            Decimal('3.000') -> '3'
            """
            s = format(d, "f")                  # never scientific notation
            if "." in s:
                s = s.rstrip("0").rstrip(".")   # trim trailing zeros and dot
            return s
        
        #  Handle pack-multiplier grams like "5x0.7g", "6x0.5g"
        m = re.match(r'^(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)g$', u)
        if m:
            count = Decimal(m.group(1))
            per_unit = Decimal(m.group(2))
            total_g = count * per_unit
            s = _plain_decimal_str(total_g)
            return f"{s}g"
        
        # Handle word-numbers like "twograms" → "2g"
        word_to_num = {
            "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "half": "0.5", "quarter": "0.25",
        }

        for word, num in word_to_num.items():
            # Match things like "twogram", "twograms", "two-grams"
            if re.match(rf'^{word}s?(g|gram|grams)?$', u):
                return f"{num}g"

        # fraction/decimal ounces → grams (with special rounding rule)
        m = re.match(r'^(\d+(?:\.\d+)?|\d+/\d+)(oz|ounce|ounces)$', u)
        if m:
            part = m.group(1)
            qty = (Decimal(part.split('/')[0]) / Decimal(part.split('/')[1])
                   if '/' in part else Decimal(part))
            grams = qty * OZ_TO_G

            # special case only 1/8 oz exact value
            if grams == Decimal("3.5436875"):
                return "3.5g"

            # otherwise: keep to 2 decimal places
            grams_2dp = grams.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            s = f"{grams_2dp:.4f}"
            return f"{s}g"
        # --- fluid ounces (floz / fl.oz / fluidounce / fluidounces) ---
        m = re.match(r'^(\d+(?:\.\d+)?)(floz|fl\.?oz|fluidounce|fluidounces)$', u)
        if m:
            qty = Decimal(m.group(1))
            grams = qty * FLOZ_TO_G
            grams_4dp = grams.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            return f"{grams_4dp:.4f}g"

        return u

    def generate_flagged_xlsx(self, folder_path: str, today_date: str, mail_to_prod: bool = True):
        """Generate comprehensive Excel file using data from previously generated Excel files in notification_excel/"""
        try:
            project_root = Path(__file__).resolve().parent.parent  # go up TWO levels
            comparison_dir = (Path(folder_path) if Path(folder_path).is_absolute() else project_root / folder_path).resolve()
 
            all_files = list(comparison_dir.glob("*.*"))
            excel_files = [f for f in all_files if f.name.startswith("db_") and f.name.endswith("_product_comparison.xlsx")]
            print(f"Excel files being processed............")
            if not excel_files:
                print("No .xlsx files found.")
                return None
 
            expanded_rows = []
 
            for file in excel_files:
                try:
                    df = pd.read_excel(file)
                    for _, product in df.iterrows():
                        def _parse_dict_inline(v):
                            if isinstance(v, dict):
                                return v
                            if isinstance(v, str):
                                v_strip = v.strip()
                                if not v_strip:
                                    return {}
                                # try JSON
                                try:
                                    return json.loads(v_strip)
                                except Exception:
                                    pass
                                # try python literal
                                try:
                                    import ast
                                    parsed = ast.literal_eval(v_strip)
                                    return parsed if isinstance(parsed, dict) else {}
                                except Exception:
                                    return {}
                            return {}
                        
                        price_data = product.get("Price", {})
                        thc_value = product.get('THC', '')

                        # Transform price data
                        price_entries = self.transform_unit_data(price_data, value_key="Price Value")
                        qpo_dict = _parse_dict_inline(product.get("Quantity Per Option", {}))
                        quantity_entries = self.transform_unit_data(qpo_dict, value_key="Quantity")

                        # Filter for preferred units if multiple exist
                        preferred_units = ['1/8oz', '3.5g']
                        if len(price_entries) > 1:
                            units_present = {e['Unit'] for e in price_entries}
                            filtered_entries = [e for e in price_entries if e['Unit'] in preferred_units]
                            if not filtered_entries:
                                if '1g' in units_present:
                                    filtered_entries = [e for e in price_entries if e['Unit'] == '1g']
                                else:
                                    filtered_entries = price_entries
                        else:
                            filtered_entries = price_entries

                        # Create quantity lookup for preferred units
                        quantity_lookup = {entry['Unit']: entry['Quantity'] for entry in quantity_entries}

                        d1_map = _parse_dict_inline(product.get("1d", 0))
                        d3_map = _parse_dict_inline(product.get("3 Days", 0))
                        d7_map = _parse_dict_inline(product.get("7 Days", 0))
                        d14_map = _parse_dict_inline(product.get("14+", 0))
                        prev_map = _parse_dict_inline(product.get("Prev", 0))

                        def _to_number(x, default=0.0):
                            if isinstance(x, (int, float, np.number)):
                                return float(x)
                            if isinstance(x, str):
                                s = re.sub(r'[^0-9.\-]', '', x)  # strips $, commas, etc.
                                try:
                                    return float(s)
                                except Exception:
                                    return default
                            return default

                        for entry in filtered_entries:
                            unit = entry['Unit']
                            quantity_for_unit = quantity_lookup.get(unit, product.get("Quantity Available", 0))
 
                            # --- keep this helper near the top of the loop (or define once above) ---
                            def _to_int_safe(x, default=0):
                                try:
                                    if x is None:
                                        return default
                                    # numpy/pandas NaN check
                                    if isinstance(x, float) and np.isnan(x):
                                        return default
                                    return int(float(x))
                                except Exception:
                                    return default
 
                        # unit-specific values with fallback to numeric/scalar if the cell wasn't a dict
                            def _pick(v_map, fallback):
                                # make fallback a number if it's a dict like {'each': 23}
                                if isinstance(fallback, dict):
                                    fallback = next(iter(fallback.values()), 0)
 
                                if isinstance(v_map, dict):
                                    # prefer the row's unit; else fall back to 'each' or first value
                                    val = v_map.get(unit)
                                    if val is None:
                                        val = v_map.get('each', next(iter(v_map.values()), fallback))
                                    try:
                                        return int(val)
                                    except Exception:
                                        try:
                                            return int(float(val))
                                        except Exception:
                                            return fallback if isinstance(fallback, (int, float)) else 0
 
                                # if not a dict, return numeric fallback or 0
                                return fallback if isinstance(fallback, (int, float)) else 0
                           
                            quantity_history = {
                                "1d":   _pick(d1_map,  quantity_for_unit),  # NEW
                                "3 Days": _pick(d3_map,    product.get("3 Days", 0)),
                                "7 Days": _pick(d7_map,    product.get("7 Days", 0)),
                                "14+":   _pick(d14_map,    product.get("14+", 0)),
                               
                            }
                            prev_for_unit = _pick(prev_map, product.get("Quantity Available", 0))
                            # then do safe math (with deli/bulk rule + revenue logic)
                            current_qty = _to_int_safe(quantity_history["1d"], 0)
                            prev_qty    = _to_int_safe(prev_for_unit, 0)
 
                            # raw change (today - yesterday)
                            change_qty = float(current_qty - prev_qty)
 
                            # deli/bulk normalization: look at product name (fallback to Product Name)
                            name_col_val = (product.get("Product name") or product.get("Product Name") or "")
                            if re.search(r"(deli|bulk)", str(name_col_val), flags=re.IGNORECASE):
                                change_qty = change_qty / 3.5
 
                            # price may be a string like "$35"; coerce safely
                            def _to_number(x, default=0.0):
                                if isinstance(x, (int, float, np.number)):
                                    return float(x)
                                if isinstance(x, str):
                                    s = re.sub(r'[^0-9.\-]', '', x)
                                    try:
                                        return float(s)
                                    except Exception:
                                        return default
                                return default
 
                            unit_price = _to_number(entry.get('Price Value', 0), 0.0)
 
                            # Revenue: if Change < 0 -> units sold -> -Change * Price
                            #          else (restock/positive change) -> -Change * Price * 0.40
                            revenue = (-change_qty * unit_price) if (change_qty < 0) else (-change_qty * unit_price * 0.40)
 
                            # rounding
                            change_qty = round(change_qty, 3)   # keep 3 dp for 1/8 conversions
                            revenue    = round(revenue, 2)
 
                            # treat Flower Jar / Flower Bulk as total-based items OR when QPO is empty
                            ptype = str(product.get("Internal Product Type", "")).strip().lower()
                            is_flower_total = ptype in ("flower jar", "flower bulk")
 
                            if (not quantity_lookup) or is_flower_total:
                                try:
                                    total_qty_all_units = int(product.get("Quantity Available", 0) or 0)
                                except Exception:
                                    try:
                                        total_qty_all_units = int(float(product.get("Quantity Available", 0) or 0))
                                    except Exception:
                                        total_qty_all_units = 0
                            else:
                                def _sum_qty(d):
                                    try:
                                        return int(sum(int(v) for v in d.values()))
                                    except Exception:
                                        try:
                                            return int(sum(float(v) for v in d.values()))
                                        except Exception:
                                            return 0
                                total_qty_all_units = _sum_qty(quantity_lookup)
 
                            new_row = {
                                'Company Name': product.get("Company Name", ""),
                                'Product name': product.get("Product name", ""),
                                'Brand': product.get("Brand", ""),
                                'Category': product.get("Category", ""),
                                'Price Data': price_data,
                                'Discount Price Data': product.get("Discount Price", {}),
                                'THC': thc_value,
                                'Qty Available for Weight': quantity_for_unit,
                                'SKU': product.get("SKU", ""),
                                'Days on Shelf': product.get("Days on Shelf", 0),
                                'Flag': product.get("Flag", ""),
                                "1d": quantity_history["1d"],  
                                "3d": quantity_history["3 Days"],
                                "7d": quantity_history["7 Days"],
                                "14d": quantity_history["14+"],
                                "Previous Quantity": prev_for_unit,
                                "Change": change_qty,
                                "Revenue": revenue,
                                "Today's Quantity Total": total_qty_all_units,
                                'Internal Product Name': product.get("Internal Product Name", ""),
                                'Internal Product Type': product.get("Internal Product Type", ""),
                                'Original Price Data': str(price_data),
                                'Unit': entry['Unit'],
                                'Price': entry['Price Value'],
                                'Details': product.get("Details", "")
                            }
 
                            # Assign fixed naming logic (no json_match used anymore)
                            new_row['Product Name'] = str(product.get("Internal Product Name", "")).strip()
                            new_row['Product name'] = str(product.get("Product name", "")).strip()
                            new_row['Product Type'] = str(product.get("Internal Product Type", "")).strip()
 
                            expanded_rows.append(new_row)
 
                except Exception as e:
                    logging.warning(f"Skipping file {file.name}: {e}")
 
            if not expanded_rows:
                print("No valid rows found")
                return None
 
            # Create DataFrame
            final_df = pd.DataFrame(expanded_rows)
 
            # Insert Category column based on Product Type
            final_df['Category'] = final_df['Product Type'].apply(self.get_category)
 
            # Reorder columns
            desired_column_order = [
                'Company Name', 'Product Name', 'Category', 'Product Type',
                'Days on Shelf', 'Flag', 'Unit', 'Price', 'Discount Price Data', "Today's Quantity Total",'1d', '3d', '7d', '14d',
                'THC','SKU','Change','Revenue',
            ]
 
            for col in desired_column_order:
                if col not in final_df.columns:
                    final_df[col] = ''
 
            final_df = final_df[desired_column_order]
            # final_df['Unit'] = final_df['Unit'].replace('each', '1g')
            final_df['Unit'] = final_df['Unit'].apply(self.normalize_unit_string)
 
            # Group by product name and company
            grouped_df = self.product_name_and_company_grouping(final_df)
 
            # Replace product type names
            final_df['Product Type'] = final_df['Product Type'].replace({
                'Rosin Jar': 'Jar',
                'Flower Jar': 'Jar',
                'Flower Bulk': 'Bulk',
                'Flower Bulk(Shake)': 'Bulk Shake'
            })
 
            # Rename columns
            final_df.rename(columns={
                'Product Type': 'Type',
                'Days on Shelf': 'Days',
                'Price Value': 'Price',
                # 'Price': 'Price Value'
                'Price': 'Price'
            }, inplace=True)
 
            if 'Normalized Product Type' in final_df.columns:
                final_df.drop(columns=['Normalized Product Type'], inplace=True)
            # Remove Details and Price Value
            cols_to_drop = ['Details', 'Price Data']
            final_df.drop(columns=[c for c in cols_to_drop if c in final_df.columns], inplace=True)
 
            # ---- Row sorting (Type alphabetical) ----
            # Ensure data types & null-safe strings
            final_df['Days'] = pd.to_numeric(final_df.get('Days'), errors='coerce').fillna(0).astype(int)
            for col in ['Company Name', 'Category', 'Type', 'Product Name', 'SKU']:
                if col in final_df.columns:
                    final_df[col] = final_df[col].fillna('')
 
            # Sheet1 sort: Company, Category, Type (alphabetical), Days (desc), ties by Product Name, SKU
            final_df = final_df.sort_values(
                by=['Company Name', 'Category', 'Type', 'Days', 'Product Name', 'SKU'],
                ascending=[True, True, True, False, True, True],
                kind='mergesort'  # stable
            )
 
            # store sheet sort (no Days): Company, Category, Type (alphabetical), Product Name
            for col in ['Company Name', 'Category', 'Type', 'Product Name']:
                if col in grouped_df.columns:
                    grouped_df[col] = grouped_df[col].fillna('')
            grouped_df = grouped_df.sort_values(
                by=['Company Name', 'Category', 'Type', 'Product Name'],
                ascending=[True, True, True, True],
                kind='mergesort'
            )
 
            # removed sheet sort (same order as Sheet1)
            removed_df = final_df[final_df['Flag'] == 'Removed'].copy()
            removed_df = removed_df.sort_values(
                by=['Company Name', 'Category', 'Type', 'Days', 'Product Name', 'SKU'],
                ascending=[True, True, True, False, True, True],
                kind='mergesort'
            )
 
            # Create current_inventory directory
            project_root = Path(__file__).resolve().parent.parent
            current_inventory_dir = project_root / "current_inventory"
            current_inventory_dir.mkdir(parents=True, exist_ok=True)
 
            # Save to Excel on disk
            current_inventory_path = current_inventory_dir / f'current_inventory_{today_date}.xlsx'
 
            # --- Remove raw Product Type column from store sheet ---
            # grouped_df currently has both the raw type (Product Type/Internal Product Type) and the pretty 'Type'
            to_drop = [c for c in ['Product Type', 'Internal Product Type'] if c in grouped_df.columns]
            if to_drop:
                grouped_df = grouped_df.drop(columns=to_drop)
 
            # (Optional) reorder columns for a cleaner store sheet
            preferred_order = ['Product Name', 'Category', 'Type', 'Company Name', 'SKU']
            existing_order = [c for c in preferred_order if c in grouped_df.columns]
            remaining = [c for c in grouped_df.columns if c not in existing_order]
            grouped_df = grouped_df[existing_order + remaining]
 
            # keep Revenue numeric for proper Excel currency formatting
            final_df['Revenue'] = pd.to_numeric(final_df['Revenue'], errors='coerce').fillna(0.0)
           
            # ============================
            # SANITIZE final_df FOR MYSQL
            # ============================
            final_df = final_df.astype(object)  # force all columns to object so NA becomes real Python None
 
            final_df = final_df.replace({
                pd.NA: None,
                np.nan: None,
                "<NA>": None,
                "nan": None,
                "NaN": None,
                "None": None
            })
 
            # Convert any leftover bad numeric strings
            for col in final_df.columns:
                final_df[col] = final_df[col].apply(
                    lambda x: None if (isinstance(x, str) and x.strip() in ["<NA>", "NaN", "nan", "None"]) else x
                )
 
            # Replace remaining NaN
            final_df = final_df.where(pd.notnull(final_df), None)
 
            print(f"final_df.columns :{final_df.columns}")
 
            with pd.ExcelWriter(current_inventory_path, engine='openpyxl') as writer:
                final_df.to_excel(writer, sheet_name='Sheet1', index=False)
                ws = writer.sheets['Sheet1']
                col_idx = final_df.columns.get_loc('Revenue') + 1  # Excel is 1-based
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
                    row[0].number_format = '$#,##0.00'
                grouped_df.to_excel(writer, sheet_name='store', index=False)
                if not removed_df.empty:
                    removed_df.to_excel(writer, sheet_name='Removed', index=False)
 
            # and mirror the same for the in-memory buffer:
            self.excel_buffer = BytesIO()
            with pd.ExcelWriter(self.excel_buffer, engine='openpyxl') as writer:
                final_df.to_excel(writer, sheet_name='Sheet1', index=False)
                ws = writer.sheets['Sheet1']
                col_idx = final_df.columns.get_loc('Revenue') + 1
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
                    row[0].number_format = '$#,##0.00'
                grouped_df.to_excel(writer, sheet_name='store', index=False)
                if not removed_df.empty:
                    removed_df.to_excel(writer, sheet_name='Removed', index=False)
            self.excel_buffer.seek(0)

           
            # Upload final_df (Sheet1)
            if mail_to_prod:
                print('DB insert begin')
                table_name = os.getenv('db_table_name')
                main_table = f"{table_name}_main"
                print(f"table name :{main_table}")
                final_df['date'] = today_date
                df_upload = align_to_rhize_main_schema(final_df)
                upload_dataframe(df=df_upload, table_name=main_table)

                # Upload grouped_df (store)
                store_table = f"{table_name}_store"
                print(f"table name :{store_table}")
                grouped_df['date'] = today_date
                upload_dataframe(df=grouped_df, table_name=store_table)
                 
           
                # Upload removed_table_df (only removed sheet)
                removed_table = f"{table_name}_removed"
                print(f"table name :{removed_table}")
                print(removed_df.head())
                df_upload = align_to_rhize_main_schema(removed_df)
                upload_dataframe(df=df_upload, table_name=removed_table)

                print("db insert end")
 
                # Upload to Google Drive
                try:
                    drive_resp = self.upload_to_drive(current_inventory_path, '1DutUCylz5t_Fx0vK63wJaAegfq61s-Af')
                    print(f"Uploaded to Google Drive: {drive_resp}")
                    logging.info(f"Uploaded to Google Drive: {drive_resp}")
                except Exception as e:
                    logging.error(f"Failed to upload to Google Drive: {e}")
 
            return current_inventory_path
 
        except Exception as e:
            logging.error(f"Error generating flagged XLSX: {e}")
            return None
     
 
    def get_google_drive_credentials(self):
        """Get valid user credentials from storage"""
        creds = None
        script_dir = os.path.dirname(os.path.abspath(__file__))      # this is utils/
        project_root = os.path.dirname(script_dir)                   # this is your base folder
        token_file = os.path.join(project_root, 'token.pickle')
        
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_file = os.path.join(script_dir, 'credentials.json')
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds

    def upload_to_drive(self, file_path: str, folder_id: str = None) -> str:
        """Upload a file to Google Drive"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            creds = self.get_google_drive_credentials()
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
            
            return file.get('id')
        
        except Exception as e:
            raise Exception(f"Error uploading file to Google Drive: {str(e)}")

    def send_notification(self, html, mail_to_prod=True):
        """Send email notification with changes and Excel attachment"""
        print("\n-->Start sending email notification")
        
        try:
            # Replace with your actual mail config
            self.sender_user = mail_cfg.user
            self.sender_pw = mail_cfg.pw
            sender_email = self.sender_user
            receiver = mail_cfg.receiver if mail_to_prod else mail_cfg.receiver_test
            subject = "Rhize Cannabis Company - Change"
            body = f"Hi<br><br>Please find below the changes to the product for Rhize Cannabis Company:<br>{html}<br><br>Menu Scraping Team"
        except Exception as e:
            logging.error(f"Error retrieving email configurations: {str(e)}")
            return
        
        self.message = EmailMessage()
        self.message["From"] = f"{self.sender_name}<{sender_email}>"
        self.message["To"] = receiver
        self.message["Subject"] = subject
        self.message.set_content(body, 'html')

        try:
            os_name = platform.system()
            if os_name == "Windows":
                self.context = ssl.create_default_context()
            elif os_name == "Darwin":
                self.context = ssl.create_default_context(cafile=certifi.where())
        except Exception as e:
            logging.error(f"Error creating SSL context: {str(e)}")
            return
       
        # Generate Excel files to attach
        today_date = datetime.now().strftime('%Y-%m-%d')
        project_root = Path(__file__).resolve().parent.parent.parent
        notification_excel_path = project_root / "notification_excel"
        try: 
            self.generate_flagged_xlsx(str(notification_excel_path), today_date)
        except Exception as e:
            logging.error(f"Error generating Excel files: {str(e)}")
            return
       
        # Attach the generated Excel file
        file_name = f"DataBase_Rhize_Cannabis_Company_{today_date}.xlsx"
        mime_type, _ = mimetypes.guess_type(file_name)
       
        if mime_type is None:
            mime_type = 'application'
            mime_subtype = 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            mime_type, mime_subtype = mime_type.split('/', 1)

        try:
            # Attach the current inventory file to the email
            file_name_only = f'current_inventory_{today_date}.xlsx'
            current_inventory_path = os.path.join(os.path.dirname(__file__), '..', 'current_inventory', file_name_only)
            current_inventory_path = os.path.abspath(current_inventory_path)
            
            with open(current_inventory_path, 'rb') as file:
                self.message.add_attachment(
                    file.read(),
                    maintype=mime_type,
                    subtype=mime_subtype,
                    filename=file_name_only)
                
            # Attach the removed products log file
            removed_log_path = os.path.join(os.path.dirname(__file__), '..', 'removed_logs', 'removed_products_log.xlsx')
            removed_log_path = os.path.abspath(removed_log_path)

            if os.path.exists(removed_log_path):
                with open(removed_log_path, 'rb') as file:
                    self.message.add_attachment(
                        file.read(),
                        maintype=mime_type,
                        subtype=mime_subtype,
                        filename='removed_products_log.xlsx'
                    )
            else:
                logging.warning(f"Removed products log not found: {removed_log_path}")
              
        except FileNotFoundError as e:
            logging.error(f"File not found while attaching: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error attaching files to email: {str(e)}")
            return

        # Send the email
        print("-->Sending Notification ...")
        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=self.context) as smtp:
                smtp.login(sender_email, self.sender_pw)
                smtp.sendmail(sender_email, receiver, self.message.as_string())
            print("-->Notification sent successfully!")
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
        print("-->End")

    def send_log_notification(self, log_file_name, mail_to_prod=True):
        """Send log file via email"""
        print("\n-->Start sending log email notification")
        
        try:
            self.sender_user = mail_cfg.user
            self.sender_pw = mail_cfg.pw
            sender_email = self.sender_user
            print(mail_cfg.receiver)
            receiver = mail_cfg.receiver if mail_to_prod else mail_cfg.receiver_test
            subject = "Rhize Cannabis Company - Scraping Log"
            body = f"Hi<br><br>Please find attached the scraping log for Rhize Cannabis Company.<br><br>Menu Scraping Team"
        except Exception as e:
            logging.error(f"Error retrieving email configurations: {str(e)}")
            return
        
        self.message = EmailMessage()
        self.message["From"] = f"{self.sender_name}<{sender_email}>"
        self.message["To"] = receiver
        self.message["Subject"] = subject
        self.message.set_content(body, 'html')

        try:
            os_name = platform.system()
            if os_name == "Windows":
                self.context = ssl.create_default_context()
            elif os_name == "Darwin":
                self.context = ssl.create_default_context(cafile=certifi.where())
        except Exception as e:
            logging.error(f"Error creating SSL context: {str(e)}")
            return

        # Attach the log file
        mime_type, _ = mimetypes.guess_type(log_file_name)
        
        if mime_type is None:
            mime_type = 'text'
            mime_subtype = 'plain'
        else:
            mime_type, mime_subtype = mime_type.split('/', 1)

        try:
            with open(log_file_name, 'rb') as file:
                self.message.add_attachment(
                    file.read(),
                    maintype=mime_type,
                    subtype=mime_subtype,
                    filename=os.path.basename(log_file_name)
                )
        except FileNotFoundError as e:
            logging.error(f"Log file not found while attaching: {str(e)}")
            return
        except Exception as e:
            logging.error(f"Error attaching log file to email: {str(e)}")
            return

        # Send the email
        print("-->Sending Log Notification ...")
        try:
            print(f"Sender: {sender_email}, Receiver: {receiver}")
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=self.context) as smtp:
                smtp.login(sender_email, self.sender_pw)
                smtp.sendmail(sender_email, receiver, self.message.as_string())
            print("-->Log notification sent successfully!")
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
        print("-->End")


# Legacy functions for backward compatibility
def load_all_company_data(data_dir: str = "data_base") -> Dict[str, Dict[str, List[Dict]]]:
    processor = DataProcessor()
    return processor.load_all_company_data(data_dir)

def get_latest_products(data_dir: str = "data_base") -> Dict[str, List[Dict]]:
    processor = DataProcessor()
    return processor.get_latest_products(data_dir)

def compare_with_yesterday(data_dir: str = "data_base") -> Dict[str, Any]:
    processor = DataProcessor()
    return processor.compare_with_yesterday(data_dir)

def generate_comparison_excel(comparison_data: Dict[str, Any], output_dir: str = "reports"):
    """Generate comparison Excel report with SKU-based changes"""
    if not comparison_data:
        return None
        
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Summary data
    summary_rows = []
    for company, data in comparison_data.items():
        summary_rows.append({
            "Company": company,
            "Products Added": data["added"],
            "Products Removed": data["removed"],
            "Products Updated": data["updated"],
            "Total Products Today": data["total_today"],
            "Total Products Yesterday": data.get("total_yesterday", 0),
            "Net Change": data["total_today"] - data.get("total_yesterday", 0)
        })
    
    # Detailed changes
    detail_rows = []
    for company, data in comparison_data.items():
        changes = data["changes"]
        
        # Added products
        for product in changes["added_products"]:
            detail_rows.append({
                "Company": company,
                "SKU": product.get("sku", ""),
                "Product Name": product.get("product_name", ""),
                "Change Type": "Added",
                "Price": str(product.get("price", "")),
                "Quantity": product.get("quantity", ""),
                "Product Type": product.get("product_type", ""),
                "Category": product.get("category", ""),
                "Details": ""
            })
        
        # Removed products
        for product in changes["removed_products"]:
            detail_rows.append({
                "Company": company,
                "SKU": product.get("sku", ""),
                "Product Name": product.get("product_name", ""),
                "Change Type": "Removed",
                "Price": str(product.get("price", "")),
                "Quantity": product.get("quantity", ""),
                "Product Type": product.get("product_type", ""),
                "Category": product.get("category", ""),
                "Details": ""
            })
        
        # Updated products
        for update in changes["updated_products"]:
            change_details = []
            for change in update["changes"]:
                if change["type"] == "price":
                    change_details.append(f"Price: {change['old_value']} → {change['new_value']}")
            
            detail_rows.append({
                "Company": company,
                "SKU": update.get("sku", ""),
                "Product Name": update.get("product_name", ""),
                "Change Type": "Updated",
                "Price": "",
                "Quantity": "",
                "Product Type": product.get("product_type", ""),
                "Category": product.get("category", ""),
                "Details": "; ".join(change_details)
            })
    
    # Create Excel with multiple sheets
    output_file = output_path / f"comparison_{today}.xlsx"
    
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            if summary_rows:
                pd.DataFrame(summary_rows).to_excel(writer, sheet_name='Summary', index=False)
            if detail_rows:
                pd.DataFrame(detail_rows).to_excel(writer, sheet_name='Details', index=False)
        
        logging.info(f"Generated SKU-based comparison report: {output_file}")
        return output_file
    except Exception as e:
        logging.error(f"Error generating comparison Excel: {e}")
        return None

