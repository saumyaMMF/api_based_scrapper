import json
import pandas as pd

import os

import re

import logging

import sys

from datetime import datetime, timedelta

from pathlib import Path

from decimal import Decimal, getcontext, ROUND_HALF_UP

import numpy as np

from dotenv import load_dotenv

# Add project root to path so we can import utils

project_root = Path(__file__).resolve().parent

sys.path.append(str(project_root))

from utils.data_processing import DataProcessor

from utils.df_to_db_upload import get_mysql_type,create_mysql_connection,safe_convert_for_mysql

import utils.data_processing as dp_module

# Setup logging

# Force stdout to utf-8 for Windows consoles

if sys.platform == 'win32':

    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(

    level=logging.INFO,

    format='%(asctime)s - %(levelname)s - %(message)s',

    handlers=[

        logging.FileHandler("backfill.log", encoding='utf-8'),

        logging.StreamHandler(sys.stdout)

    ]

)

load_dotenv()

class HistoricalBackfiller(DataProcessor):

    def __init__(self):

        super().__init__()

        self.target_table = os.getenv('db_table_name') or 'all_products'

        # self.target_table = "demo_table"

    def process_all_files(self):

        data_dir = project_root / "data_base"

        json_files = list(data_dir.glob("db_*.json"))

        logging.info(f"Found {len(json_files)} JSON files to process.")

        for json_file in json_files:

            try:

                self.process_single_file(json_file)

            except Exception as e:

                logging.error(f"Failed to process {json_file.name}: {e}")

    def process_single_file(self, json_file: Path):

        logging.info(f"Processing {json_file.name}...")

        # Determine company name

        raw_key = json_file.stem.replace("db_", "").lower()

        company_name = self.company_name_mapping.get(raw_key)

        if not company_name:

             # Fallback name generation

             company_name = raw_key.title()

        with open(json_file, 'r', encoding='utf-8') as f:

            data = json.load(f)

        # Sort dates

        all_dates = sorted(data.keys())

        if not all_dates:

            logging.warning(f"No dates found in {json_file.name}")

            return

        # We will collect ALL generated rows for this company into one big list

        # then create a DF and upload. Or upload in batches if too large.

        company_accumulated_rows = []

        # Iterate through dates

        for i, date_str in enumerate(all_dates):

            current_date_dt = datetime.strptime(date_str, "%Y-%m-%d")

            # Logic for "Previous" date

            # If it's the very first date in the file, we treat it as having NO previous data (everything is Added)

            # OR strictly follow "yesterday" logic? 

            # The prompt implies: "do the same [as current script] ... for all previous data"

            # The current script compares Today vs Yesterday.

            # For backfill: Compare Date[i] vs Date[i-1].

            curr_products_map = self._get_products_map(data[date_str])

            if i > 0:

                prev_date_str = all_dates[i-1]

                prev_products_map = self._get_products_map(data[prev_date_str])

            else:

                prev_products_map = {} # First day, everything is new

            # Generate the 'raw' comparison rows (Added, Removed, Updated, No Change)

            # This replicates the loops in `compare_with_yesterday`

            raw_rows = self._generate_comparison_rows(

                company_name, 

                date_str, 

                curr_products_map, 

                prev_products_map,

                data,

                json_file.stem # Pass file stem/source

            )

            if not raw_rows:

                continue

            # Now apply the 'Transformation' logic (Units, Revenue, etc.)

            # This replicates the loop in `generate_flagged_xlsx`

            processed_rows = self._apply_second_pass_transformations(raw_rows)

            # Add 'date' column for the DB

            for row in processed_rows:

                row['date'] = date_str

            company_accumulated_rows.extend(processed_rows)

        if company_accumulated_rows:

            df = pd.DataFrame(company_accumulated_rows)

            logging.info(f"Generated {len(df)} rows for {company_name}. Splitting into sections...")

            # -------------------------

            # 1) MAIN (Sheet1 equivalent)

            # -------------------------

            df_main = df[df["Flag"] != "Removed"]  # Same logic as daily final_df

            main_table = f"{self.target_table}_main"

            logging.info(f"MAIN rows: {len(df_main)}")

            df_main = align_to_rhize_main_schema(df_main)

            # upload_dataframe(df_main, main_table)

            # -------------------------

            # 2) REMOVED (Removed tab equivalent)

            # -------------------------

            df_removed = df[df["Flag"] == "Removed"]

            removed_table = f"{self.target_table}_removed"

            logging.info(f"REMOVED rows: {len(df_removed)}")

            if len(df_removed) > 0: 

                df_removed = align_to_rhize_main_schema(df_removed)               

                # upload_dataframe(df_removed, removed_table)

            else:

                logging.info("No removed rows for this company/date.")

            # -------------------------

            # 3) STORE (store tab equivalent)

            # -------------------------

            # Restrict store columns to match daily flagged excel

            store_columns = [

                'date',

                'Product Name',

                'Category',

                'Product Type',

                'Company Name',

                'SKU'

            ]

            # Ensure missing columns are added as empty

            for col in store_columns:

                if col not in df.columns:

                    df[col] = ""

            df_store = df[store_columns]

            df_store = df_store.rename(columns={

                'Product Type': 'Type'

            })

            store_table = f"{self.target_table}_store"

            logging.info(f"STORE rows: {len(df_store)}")


            upload_dataframe(df_store, store_table)


        else:

            logging.info(f"  No rows generated for {company_name}")

    def _get_products_map(self, day_data_list):

        """Convert list of product dicts to dict keyed by SKU."""

        pmap = {}

        for item in day_data_list:

            sku = item.get("SKU")

            if sku:

                pmap[sku] = item

        return pmap

    def _generate_comparison_rows(self, company_name, today_date_str, curr_map, prev_map, full_data, file_stem):

        """

        Replicates the logic of comparing today vs yesterday to generate the initial 'excel_data'.

        returns: List[Dict] - the rows that would go into the intermediate Excel.

        """

        rows = []

        today_dt = datetime.strptime(today_date_str, "%Y-%m-%d")

        # 1. REMOVED

        for sku, prev_prod in prev_map.items():

            if sku not in curr_map:

                # Removed

                # Get history

                quantity_history = self.get_recent_quantity_snapshots(full_data, sku, today_date_str)

                row = {

                    "Company Name": company_name,

                    "SKU": sku,

                    "Product name": prev_prod.get('Product name'),

                    "THC": prev_prod.get("THC"),

                    "Details": prev_prod,

                    "Price": prev_prod.get("Price"),

                    "Discount Price": prev_prod.get("Discount Price", {}),

                    "Quantity Available": prev_prod.get("Quantity Available"),

                    "Quantity Per Option": prev_prod.get("Quantity Per Option"),

                    "1d": quantity_history["1d"],

                    "3 Days": quantity_history["3 Days"],

                    "7 Days": quantity_history["7 Days"],

                    "14+": quantity_history["14+"],

                    "Prev": quantity_history["Prev"],

                    "Internal Product Name": prev_prod.get("Internal Product Name"),

                    "Internal Product Type": prev_prod.get("Internal Product Type"),

                    "Days on Shelf": prev_prod.get("Days on Shelf",0),

                    "Flag": "Removed",

                    "Quantity History": quantity_history.get("Per Unit", {})

                }

                rows.append(row)

        # 2. ADDED & NO CHANGE

        for sku, curr_prod in curr_map.items():

            if sku not in prev_map:

                # Added

                quantity_history = self.get_recent_quantity_snapshots(full_data, sku, today_date_str, since_date=None) # mimicking logic, though daily script passes yesterday as limit

                row = {

                    "Company Name": company_name,

                    "SKU": sku,

                    "Product name": curr_prod.get('Product name'),

                    "THC": curr_prod.get("THC"),

                    "Details": curr_prod,

                    "Price": curr_prod.get("Price"),

                    "Discount Price": curr_prod.get("Discount Price", {}),

                    "Quantity Available": curr_prod.get("Quantity Available"),

                    "Quantity Per Option": curr_prod.get("Quantity Per Option"),

                    "1d": quantity_history["1d"],

                    "3 Days": quantity_history["3 Days"],

                    "7 Days": quantity_history["7 Days"],

                    "14+": quantity_history["14+"],

                    "Prev": quantity_history["Prev"],

                    "Internal Product Name": curr_prod.get("Internal Product Name"),

                    "Internal Product Type": curr_prod.get("Internal Product Type"),

                    "Days on Shelf": curr_prod.get("Days on Shelf",0),

                    "Flag": "Added",

                    "Quantity History": quantity_history.get("Per Unit", {})

                }

                rows.append(row)

            else:

                # Check for Update

                prev_prod = prev_map[sku]

                is_updated = False

                diff = {}

                # Simple price check for update flag (as per original logic)

                if prev_prod.get("Price") != curr_prod.get("Price"):

                    is_updated = True

                    # calc diff (abbreviated here for speed, mostly needed for 'Flag')

                    dict1 = prev_prod

                    dict2 = curr_prod

                    diff = {k: (dict1.get(k), dict2.get(k)) for k in set(dict1.keys()) | set(dict2.keys()) if dict1.get(k) != dict2.get(k)}

                quantity_history = self.get_recent_quantity_snapshots(full_data, sku, today_date_str)

                if is_updated:

                    row = {

                        "Company Name": company_name,

                        "SKU": sku,

                        "Product name": curr_prod.get('Product name'),

                        "THC": curr_prod.get("THC"),

                        "Details": diff,

                        "Price": curr_prod.get("Price"),

                        "Discount Price": curr_prod.get("Discount Price", {}), # Need this for transformation

                        "Quantity Available": curr_prod.get("Quantity Available"), # Need this

                        "Quantity Per Option": curr_prod.get("Quantity Per Option"), # Need this

                        "1d": quantity_history["1d"],

                        "3 Days": quantity_history["3 Days"],

                        "7 Days": quantity_history["7 Days"],

                        "14+": quantity_history["14+"],

                        "Prev": quantity_history["Prev"],

                         "Internal Product Name": curr_prod.get("Internal Product Name"),

                        "Internal Product Type": curr_prod.get("Internal Product Type"),

                        "Days on Shelf": curr_prod.get("Days on Shelf",0),

                        "Flag": "Updated"

                    }

                else:

                    row = {

                        "Company Name": company_name,

                        "SKU": sku,

                        "Product name": curr_prod.get('Product name'),

                        "THC": curr_prod.get("THC"),

                        "Details": curr_prod,

                        "Price": curr_prod.get("Price"),

                        "Discount Price": curr_prod.get("Discount Price", {}),

                        "Quantity Available": curr_prod.get("Quantity Available"),

                        "Quantity Per Option": curr_prod.get("Quantity Per Option"),

                        "1d": quantity_history["1d"],

                        "3 Days": quantity_history["3 Days"],

                        "7 Days": quantity_history["7 Days"],

                        "14+": quantity_history["14+"],

                        "Prev": quantity_history["Prev"],

                        "Internal Product Name": curr_prod.get("Internal Product Name"),

                        "Internal Product Type": curr_prod.get("Internal Product Type"),

                        "Days on Shelf": curr_prod.get("Days on Shelf",0),

                        "Flag": "No Change",

                        "Quantity History": quantity_history.get("Per Unit", {})

                    }

                rows.append(row)

        return rows

    def _apply_second_pass_transformations(self, temp_rows):

        """

        Replicates the logic inside `generate_flagged_xlsx` loop.

        Explodes the rows based on units, calculates revenue, formats columns.

        """

        expanded_rows = []

        # Helper helpers

        def _parse_dict_inline(v):

            if isinstance(v, dict): return v

            if isinstance(v, str):

                v_strip = v.strip()

                if not v_strip: return {}

                try: 

                    return json.loads(v_strip.replace("'", '"')) 

                except: 

                    pass

                try: 

                    import ast

                    parsed = ast.literal_eval(v_strip)

                    return parsed if isinstance(parsed, dict) else {}

                except: 

                    return {}

            return {}

        for product in temp_rows:

            # Re-implement the loop body from generate_flagged_xlsx

            price_data = product.get("Price", {})

            thc_value = product.get('THC', '')

            # Normalize Price

            if isinstance(price_data, str):

                price_data = _parse_dict_inline(price_data)

            # Normalize Discount

            discount_data = product.get("Discount Price", {})

            if isinstance(discount_data, str):

                discount_data = _parse_dict_inline(discount_data)

            normalized_discount = {}

            for unit_raw, val in discount_data.items():

                normalized_unit = self.normalize_unit_string(unit_raw)

                normalized_discount[normalized_unit] = val

            # Transform price data

            price_entries = self.transform_unit_data(price_data, value_key="Price Value")

            qpo_dict = _parse_dict_inline(product.get("Quantity Per Option", {}))

            normalized_qpo = {}

            for unit_raw, qty in qpo_dict.items():

                normalized_unit = self.normalize_unit_string(unit_raw)

                normalized_qpo[normalized_unit] = qty

            qpo_dict = normalized_qpo

            quantity_entries = self.transform_unit_data(qpo_dict, value_key="Quantity")

            # Normalize units in entries

            for e in price_entries:

                e["Unit"] = self.normalize_unit_string(e["Unit"])

            for e in quantity_entries:

                e["Unit"] = self.normalize_unit_string(e["Unit"])

            # Filter preferred units

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

            quantity_lookup = {entry['Unit']: entry['Quantity'] for entry in quantity_entries}

            # History maps

            d1_map = _parse_dict_inline(product.get("1d", 0))

            d3_map = _parse_dict_inline(product.get("3 Days", 0))

            d7_map = _parse_dict_inline(product.get("7 Days", 0))

            d14_map = _parse_dict_inline(product.get("14+", 0))

            prev_map = _parse_dict_inline(product.get("Prev", 0))

            for entry in filtered_entries:

                unit = entry['Unit']

                quantity_for_unit = quantity_lookup.get(unit, product.get("Quantity Available", 0))

                # Inner helpers

                def _to_int_safe(x, default=0):

                    try:

                        if x is None: return default

                        if isinstance(x, float) and np.isnan(x): return default

                        return int(float(x))

                    except: return default

                def _pick(v_map, fallback):

                    if isinstance(fallback, dict):

                        fallback = next(iter(fallback.values()), 0)

                    if isinstance(v_map, dict):

                        val = v_map.get(unit)

                        if val is None:

                            val = v_map.get('each', next(iter(v_map.values()), fallback))

                        try: return int(val)

                        except: 

                            try: return int(float(val))

                            except: return fallback if isinstance(fallback, (int, float)) else 0

                    return fallback if isinstance(fallback, (int, float)) else 0

                quantity_history = {

                    "1d":   _pick(d1_map, quantity_for_unit),

                    "3 Days": _pick(d3_map, product.get("3 Days", 0)),

                    "7 Days": _pick(d7_map, product.get("7 Days", 0)),

                    "14+":   _pick(d14_map, product.get("14+", 0)),

                }

                prev_for_unit = _pick(prev_map, product.get("Quantity Available", 0))

                current_qty = _to_int_safe(quantity_history["1d"], 0)

                prev_qty    = _to_int_safe(prev_for_unit, 0)

                change_qty = float(current_qty - prev_qty)

                name_col_val = (product.get("Product name") or product.get("Product Name") or "")

                if re.search(r"(deli|bulk)", str(name_col_val), flags=re.IGNORECASE):

                    change_qty = change_qty / 3.5

                def _to_number(x, default=0.0):

                    if isinstance(x, (int, float, np.number)): return float(x)

                    if isinstance(x, str):

                        s = re.sub(r'[^0-9.\-]', '', x)

                        try: return float(s)

                        except: return default

                    return default

                unit_price = _to_number(entry.get('Price Value', 0), 0.0)

                revenue = (-change_qty * unit_price) if (change_qty < 0) else (-change_qty * unit_price * 0.40)

                change_qty = round(change_qty, 3)

                revenue = round(revenue, 2)

                ptype = str(product.get("Internal Product Type", "")).strip().lower()

                is_flower_total = ptype in ("flower jar", "flower bulk")

                if (not quantity_lookup) or is_flower_total:

                    try: total_qty_all_units = int(product.get("Quantity Available", 0) or 0)

                    except: 

                        try: total_qty_all_units = int(float(product.get("Quantity Available", 0) or 0))

                        except: total_qty_all_units = 0

                else:

                    try: total_qty_all_units = int(sum(int(v) for v in quantity_lookup.values()))

                    except: 

                        try: total_qty_all_units = int(sum(float(v) for v in quantity_lookup.values()))

                        except: total_qty_all_units = 0

                new_row = {

                    'Company Name': product.get("Company Name", ""),

                    'Product name': product.get("Product name", ""),

                    'Brand': product.get("Brand", ""),

                    # 'Category': product.get("Category", ""), # Will be set by get_category later or here

                    'Category': self.get_category(product.get("Internal Product Type", "")),

                    'Price Data': str(price_data),

                    'Discount Price Data': str(normalized_discount),

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

                    # 'Original Price Data': str(price_data),

                    'Unit': entry['Unit'],

                    'Price': unit_price,

                    # 'Details': product.get("Details", "")

                }

                # Align naming with upload requirements (Final Clean)

                new_row['Product Name'] = str(product.get("Internal Product Name", "")).strip()

                new_row['Product name'] = str(product.get("Product name", "")).strip()

                new_row['Product Type'] = str(product.get("Internal Product Type", "")).strip()

                # Type renaming

                pt_map = {

                    'Rosin Jar': 'Jar', 'Flower Jar': 'Jar', 

                    'Flower Bulk': 'Bulk', 'Flower Bulk(Shake)': 'Bulk Shake'

                }

                new_row['Type'] = pt_map.get(new_row['Product Type'], new_row['Product Type'])

                expanded_rows.append(new_row)

        # --- Filter columns to match the official schema ---

        if expanded_rows:

            desired_column_order = [

                'Company Name', 'Product Name', 'Category', 'Product Type',

                'Days on Shelf', 'Flag', 'Unit', 'Price', 'Discount Price Data', "Today's Quantity Total",'1d', '3d', '7d', '14d',

                'THC','SKU','Change','Revenue',

            ]

            # Create DF first to easily select columns

            df_temp = pd.DataFrame(expanded_rows)

            # Ensure all desired columns exist

            for col in desired_column_order:

                if col not in df_temp.columns:

                    df_temp[col] = ''

            # Select and reorder

            # Drop columns not in desired list (like 'Product name', 'Details', etc.)

            df_temp = df_temp[desired_column_order]

            # Convert back to list of dicts or just return list of dicts if I was returning that? 

            # The calling method expects a list of dicts actually? 

            # Wait, process_single_file: "company_accumulated_rows.extend(processed_rows)"

            # Then "df = pd.DataFrame(company_accumulated_rows)"

            # So I should return a list of dicts that ONLY has these keys.

            return df_temp.to_dict('records')

        return expanded_rows

def align_to_rhize_main_schema(df: pd.DataFrame) -> pd.DataFrame:

    """

    Force the dataframe to match rhize_dataset_main schema

    (same as historical uploader output).

    """

    schema_cols = [

        'Company Name', 'Product Name', 'Category', 'Type',

        'Days', 'Flag', 'Unit', 'Price', 'Discount Price Data',

        "Today's Quantity Total",'1d', '3d', '7d', '14d',

        'THC','SKU','Change','Revenue','date'

    ]

    # Rename known columns

    rename_map = {

        'product_name': 'Product Name',

        'Product name': 'Product Name',

        'category': 'Category',

        'Category': 'Category',

        'type': 'Type',

        #  Product Type (ALL real variants)

        'Product Type': 'Type',

        'Product type': 'Type',

        'product type': 'Type',

        'product_type': 'Type',

        'type': 'Type',

        #  Days

        'Days on Shelf': 'Days',

        'days_on_shelf': 'Days',

        'Days': 'Days',

        'days': 'Days',

    }


    df = df.rename(columns=rename_map)

    # Add missing columns

    for col in schema_cols:

        if col not in df.columns:

            df[col] = None

    # Hard defaults (same as historical logic)

    df['Flag'] = df['Flag'].fillna('No Change')

    df['Change'] = df['Change'].fillna(0)

    df['Revenue'] = df['Revenue'].fillna(0)

    df['Type'] = df['Type'].fillna('')

    df['Unit'] = df['Unit'].fillna('')

    df['Discount Price Data'] = df['Discount Price Data'].fillna('{}')

    df["Today's Quantity Total"] = df["Today's Quantity Total"].fillna(0)

    # Enforce column order

    df = df[schema_cols]

    return df


def upload_dataframe(df, table_name):

    """Insert dataframe into MySQL table with dynamic schema creation."""

    try:

        df = df.copy()

        df.drop(df.columns[df.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)

        df = safe_convert_for_mysql(df)

        df = df.replace({"<NA>": None, "nan": None, "None": None})

        df = df.where(pd.notnull(df), None)

        connection = create_mysql_connection()

        if not connection:

            return "Failed to connect to MySQL database"

        cursor = connection.cursor()

        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")

        table_exists = cursor.fetchone()

        if not table_exists:

            column_definitions = []

            for col in df.columns:

                mysql_type = get_mysql_type(df[col].dtype, df[col])

                col_name = col.replace(' ', '_').replace('-', '_').replace('.', '_')

                column_definitions.append(f"`{col_name}` {mysql_type}")

            create_table_sql = f"""

            CREATE TABLE `{table_name}` (

                `id` INT AUTO_INCREMENT PRIMARY KEY,

                {', '.join(column_definitions)},

                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            )

            """

            cursor.execute(create_table_sql)

            connection.commit()

            print(f"✓ Table '{table_name}' created successfully")

        else:

            cursor.execute(f"DESCRIBE `{table_name}`")

            existing_columns = {row[0] for row in cursor.fetchall()}

            new_columns_added = 0

            for col in df.columns:

                col_name = col.replace(' ', '_').replace('-', '_').replace('.', '_')

                if col_name not in existing_columns and col_name != 'id' and col_name != 'created_at':

                    mysql_type = get_mysql_type(df[col].dtype, df[col])

                    alter_table_sql = f"ALTER TABLE `{table_name}` ADD COLUMN `{col_name}` {mysql_type}"

                    cursor.execute(alter_table_sql)

                    connection.commit()

                    new_columns_added += 1

            if new_columns_added > 0:

                print(f"✓ Added {new_columns_added} new column(s) to table '{table_name}'")

        batch_size = 1000

        total_rows = len(df)

        for start_idx in range(0, total_rows, batch_size):

            end_idx = min(start_idx + batch_size, total_rows)

            batch_df = df.iloc[start_idx:end_idx]

            placeholders = ', '.join(['%s'] * len(batch_df.columns))

            columns = [col.replace(' ', '_').replace('-', '_').replace('.', '_') for col in batch_df.columns]

            columns_str = ', '.join([f'`{col}`' for col in columns])

            insert_sql = f"INSERT INTO `{table_name}` ({columns_str}) VALUES ({placeholders})"

            data_values = [tuple(row) for row in batch_df.values]

            cursor.executemany(insert_sql, data_values)

            connection.commit()

            print(f"  → Inserted batch {start_idx + 1}-{end_idx} of {total_rows} rows")

        cursor.close()

        connection.close()

        return f"✓ Successfully inserted {len(df)} rows into table '{table_name}'"

    except Exception as e:

        print(f"✗ Error: {str(e)}")

        return str(e)

if __name__ == "__main__":

    try:

        backfiller = HistoricalBackfiller()

        backfiller.process_all_files()

        print("Backfill process completed successfully.")

    except Exception as e:

        print(f"Backfill process failed: {e}")

        logging.error(f"Backfill process failed: {e}")

 