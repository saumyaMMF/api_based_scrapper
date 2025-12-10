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

# Add your email configuration import here
# import mail_cfg

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
        
    def load_all_company_data(self, data_dir: str = "data_base") -> Dict[str, Dict[str, List[Dict]]]:
        """Load all company data organized by company and date"""
        data_path = Path(data_dir)
        all_data = {}
        
        for json_file in data_path.glob("db_*.json"):
            # Extract company name from filename
            company_name = json_file.stem.replace("db_", "").replace("_", " ").title()
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    company_data = json.load(f)
                all_data[company_name] = company_data
            except Exception as e:
                logging.error(f"Error loading {json_file}: {e}")
        
        return all_data

    def get_latest_products(self, data_dir: str = "data_base") -> Dict[str, List[Dict]]:
        """Get latest products for all companies"""
        today = datetime.now().strftime("%Y-%m-%d")
        all_data = self.load_all_company_data(data_dir)
        
        latest_products = {}
        for company, dates_data in all_data.items():
            if today in dates_data:
                latest_products[company] = dates_data[today]
        
        return latest_products

    def compare_with_yesterday(self, data_dir: str = "data_base") -> Dict[str, Any]:
        """Compare today's data with yesterday's using SKU-based comparison with shelf life tracking"""
        today_date = datetime.now()
        yesterday_date = today_date - timedelta(days=1)
        today = today_date.strftime("%Y-%m-%d")
        yesterday = yesterday_date.strftime("%Y-%m-%d")
        
        data_path = Path(data_dir)
        comparison_results = {}
        
        # Process each company's JSON file
        for json_file in data_path.glob("db_*.json"):
            company_name = json_file.stem.replace("db_", "").replace("_", " ").title()
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                yesterday_products = {}
                today_products = {}
                excel_data = []
                
                # Get available dates
                keys = list(data.keys())
                
                # Process yesterday's data
                if len(keys) >= 2:
                    y_date = keys[-2]  # Second last date
                    if y_date in data:
                        for item in data[y_date]:
                            sku = item.get("SKU", "")
                            if sku:
                                yesterday_products[sku] = {
                                    "Product name": item["Product name"],
                                    "Price": item["Price"],
                                    "Days on Shelf": item.get("Days on Shelf", 0),
                                    "THC": item.get("THC", "N/A"),
                                    "SKU": sku,
                                    "Quantity Available": item.get("Quantity Available", 0)
                                }
                
                # Process today's data
                if today in data:
                    for item in data[today]:
                        sku = item.get("SKU", "")
                        if sku:
                            today_products[sku] = {
                                "Product name": item["Product name"],
                                "Price": item["Price"],
                                "Days on Shelf": item.get("Days on Shelf", 0),
                                "THC": item.get("THC", "N/A"),
                                "SKU": sku,
                                "Quantity Available": item.get("Quantity Available", 0)
                            }
                
                # Calculate shelf life for products present in both days
                for sku in today_products:
                    if sku in yesterday_products:
                        shelf_life_days = 1 + yesterday_products[sku]["Days on Shelf"]
                        today_products[sku]["Days on Shelf"] = shelf_life_days
                
                # Update the original JSON data with shelf life values
                for sku in today_products:
                    for entry in data[today]:
                        if entry.get("SKU", "") == sku:
                            entry["Days on Shelf"] = today_products[sku]["Days on Shelf"]
                            break
                
                # Write updated data back to JSON file
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                
                # Prepare comparison data
                added_keys = set(today_products.keys()) - set(yesterday_products.keys())
                removed_keys = set(yesterday_products.keys()) - set(today_products.keys())
                
                # Track detailed changes
                added_products = []
                removed_products = []
                updated_products = []
                
                # Process REMOVED products
                for sku in removed_keys:
                    product = yesterday_products[sku]
                    removed_products.append({
                        "key": sku,
                        "sku": sku,
                        "product_name": product.get("Product name", ""),
                        "price": product.get("Price", {}),
                        "quantity": product.get("Quantity Available", 0)
                    })
                    
                    excel_data.append({
                        "Company Name": company_name,
                        "SKU": sku,
                        "Product name": product['Product name'],
                        "THC": product["THC"],
                        "Details": product,
                        "Price": product["Price"],
                        "Days on Shelf": product["Days on Shelf"],
                        "Flag": "Removed"
                    })
                
                # Process ADDED products
                for sku in added_keys:
                    product = today_products[sku]
                    added_products.append({
                        "key": sku,
                        "sku": sku,
                        "product_name": product.get("Product name", ""),
                        "price": product.get("Price", {}),
                        "quantity": product.get("Quantity Available", 0)
                    })
                    
                    excel_data.append({
                        "Company Name": company_name,
                        "SKU": sku,
                        "Product name": product['Product name'],
                        "THC": product["THC"],
                        "Details": product,
                        "Price": product["Price"],
                        "Days on Shelf": product["Days on Shelf"],
                        "Flag": "Added"
                    })
                
                # Process UPDATED and UNCHANGED products
                for sku in set(today_products.keys()) & set(yesterday_products.keys()):
                    today_product = today_products[sku]
                    yesterday_product = yesterday_products[sku]
                    
                    if yesterday_product["Price"] != today_product["Price"]:
                        # Product was updated
                        changes = []
                        if today_product.get("Price") != yesterday_product.get("Price"):
                            changes.append({
                                "type": "price",
                                "old_value": yesterday_product.get("Price"),
                                "new_value": today_product.get("Price")
                            })
                        
                        updated_products.append({
                            "key": sku,
                            "sku": sku,
                            "product_name": today_product.get("Product name", ""),
                            "changes": changes
                        })
                        
                        excel_data.append({
                            "Company Name": company_name,
                            "SKU": sku,
                            "Product name": today_product['Product name'],
                            "THC": today_product["THC"],
                            "Details": today_product,
                            "Price": today_product["Price"],
                            "Days on Shelf": today_product["Days on Shelf"],
                            "Flag": "Updated"
                        })
                    else:
                        # No change
                        excel_data.append({
                            "Company Name": company_name,
                            "SKU": sku,
                            "Product name": today_product['Product name'],
                            "THC": today_product["THC"],
                            "Details": today_product,
                            "Price": today_product["Price"],
                            "Days on Shelf": today_product["Days on Shelf"],
                            "Flag": "No Change"
                        })
                
                # Create individual comparison Excel file for this company
                if excel_data:
                    df = pd.DataFrame(excel_data)
                    comparison_dir = Path("notification_excel")
                    comparison_dir.mkdir(exist_ok=True)
                    
                    base_name = json_file.stem
                    excel_file_path = comparison_dir / f"{base_name}_product_comparison.xlsx"
                    df.to_excel(excel_file_path, index=False)
                    logging.info(f"Created comparison Excel for {company_name}: {excel_file_path}")
                
                # Store results
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
        
        return comparison_results

    def transform_price_data(self, price_data):
        """Transform price data from JSON string or dict to list of unit/price entries"""
        if isinstance(price_data, str):
            try:
                price_dict = json.loads(price_data.replace("'", '"'))
            except:
                try:
                    price_dict = eval(price_data)
                except:
                    return [{"Unit": "each", "Price Value": price_data}]
        elif isinstance(price_data, dict):
            price_dict = price_data
        else:
            return [{"Unit": "each", "Price Value": str(price_data)}]
        
        entries = []
        for unit, price in price_dict.items():
            entries.append({
                "Unit": unit,
                "Price Value": price
            })
        
        return entries

    def get_category(self, product_type):
        """Get category based on product type"""
        pt = str(product_type).strip().lower()
        if pt in ['cart', 'cartridge']:
            return 'Rosin'
        elif 'rosin' in pt:
            return 'Rosin'
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
            grouped_store = grouped_store.drop(columns=['Unit', 'Normalized Product Type'])
            
            return grouped_store
        else:
            return pd.DataFrame(columns=[name_column, type_column, 'Company Name', 'SKU'])

    def generate_flagged_xlsx(self, folder_path, today_date):   
        """Your original function but reading from JSON instead of Excel files"""
        
        # Instead of reading Excel files, get data from JSON files and convert to DataFrame format
        dfs = []
        
        # Get data from JSON files in data_base folder
        data_path = Path("data_base")
        
        for json_file in data_path.glob("db_*.json"):
            company_name = json_file.stem.replace("db_", "").replace("_", " ").title()
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    company_data = json.load(f)
                    
                # Get today's data
                if today_date not in company_data:
                    print(f"No data for {today_date} in {json_file.name}")
                    continue
                    
                products = company_data[today_date]
                
                # Convert JSON data to DataFrame format (simulating Excel file)
                json_rows = []
                for product in products:
                    json_rows.append({
                        'Company Name': company_name,
                        'Product name': product.get('Product name', ''),
                        'Brand': product.get('Brand', ''),
                        'Category': product.get('Category', ''),
                        'Price': str(product.get('Price', {})),  # Convert to string like Excel
                        'THC': product.get('THC', ''),
                        'Quantity Available': product.get('Quantity Available', 0),
                        'SKU': product.get('SKU', ''),
                        'Days on Shelf': product.get('Days on Shelf', 0),
                        'Flag': product.get('Flag', ''),
                        'Details': '',
                        'Domain': ''
                    })
                
                if not json_rows:
                    print(f"No products found in {json_file.name}")
                    continue
                    
                # Create DataFrame from JSON data (simulating reading Excel file)
                df = pd.DataFrame(json_rows)
                
            except Exception as e:
                print(f"Skipping {json_file.name} due to error: {e}")
                continue
            
            # YOUR EXACT ORIGINAL LOGIC STARTS HERE (unchanged)
            expanded_rows = []
            for _, row in df.iterrows():
                row_dict = row.to_dict()
                thc_value = row_dict.get('THC', '')
                price_data = row_dict.get('Price', '{}' if not isinstance(row_dict.get('Price'), str) else row_dict.get('Price'))
                price_entries = self.transform_price_data(price_data)

                if len(price_entries) > 1:
                    filtered_entries = [entry for entry in price_entries if entry['Unit'] in ['1/8 oz', '3.5g']]
                    if not filtered_entries:
                        filtered_entries = price_entries
                else:
                    filtered_entries = price_entries

                for entry in filtered_entries:
                    new_row = row_dict.copy()
                    new_row['Original Price Data'] = new_row.get('Price', '')
                    new_row['Unit'] = entry['Unit']
                    new_row['Price Value'] = entry['Price Value']
                    new_row['THC'] = thc_value

                    try:
                        internal_name, internal_type = self.product_name_type_mapping(new_row)
                        new_row['Product Name'] = internal_name
                        new_row['Product Type'] = internal_type
                    except Exception as e:
                        print(f"Error extracting product info: {e}")
                        new_row['Product Name'] = ''
                        new_row['Product Type'] = ''

                    expanded_rows.append(new_row)

            if expanded_rows:
                dfs.append(pd.DataFrame(expanded_rows))
            else:
                print(f"No valid rows found in {json_file.name}")   

        # YOUR EXACT ORIGINAL LOGIC CONTINUES (unchanged)
        if not dfs:
            print("No data to process.")
            return None

        final_df = pd.concat(dfs, ignore_index=True)

        # Get all unique price units across all products for individual columns
        all_price_units = set()
        for df in dfs:
            for _, row in df.iterrows():
                price_data = row.get('Original Price Data', '{}')
                try:
                    if isinstance(price_data, str):
                        price_dict = eval(price_data) if price_data != '{}' else {}
                    else:
                        price_dict = price_data
                    if isinstance(price_dict, dict):
                        all_price_units.update(price_dict.keys())
                except:
                    continue
        
        all_price_units = sorted(list(all_price_units))
        print(f"Found price units: {all_price_units}")

        # Add individual price unit columns to final_df
        for unit in all_price_units:
            final_df[unit] = ''
            
        # Populate individual price columns
        for idx, row in final_df.iterrows():
            price_data = row.get('Original Price Data', '{}')
            try:
                if isinstance(price_data, str):
                    price_dict = eval(price_data) if price_data != '{}' else {}
                else:
                    price_dict = price_data
                
                if isinstance(price_dict, dict):
                    for unit in all_price_units:
                        if unit in price_dict:
                            final_df.at[idx, unit] = price_dict[unit]
            except:
                continue

        # Insert Category column based on Product Type
        def get_category(product_type):
            pt = str(product_type).strip().lower()
            if pt in ['cart', 'cartridge']:
                return 'Rosin'
            elif 'rosin' in pt:
                return 'Rosin'
            elif 'flower' in pt or pt in ['jar', 'bulk','preroll']:
                return 'Flower'
            elif 'edible' in pt:
                return 'Edibles'
            elif 'accessory' in pt:
                return 'Accessory'
            else:
                return 'Unknown'

        final_df['Category'] = final_df['Product Type'].apply(get_category)

        # Reorder columns to insert Category before Product Type and include all price units
        desired_column_order = [
            'Company Name', 'Product Name', 'Category', 'Product Type',
            'Days on Shelf', 'Flag', 'Price Value', 'Unit', 'THC', 'Price',
            'Product name', 'Details', 'Original Price Data', 'Domain', 'SKU'
        ] + all_price_units
        
        for col in desired_column_order:
            if col not in final_df.columns:
                final_df[col] = ''

        final_df = final_df[desired_column_order]
        final_df['Unit'] = final_df['Unit'].replace('each', '1g')
        
        # Group by product name and company
        grouped_df = self.product_name_and_company_grouping(final_df)
        final_df['Product Type'] = final_df['Product Type'].replace({
            'Rosin Jar': 'Jar',
            'Flower Jar': 'Jar',
            'Flower Bulk': 'Bulk',
            'Flower Bulk(Shake)': 'Bulk Shake'
        })
        final_df.rename(columns={'Product Type': 'Type','Days on Shelf': 'Days','Price Value':'Price','Price':'Price Value'}, inplace=True)
        
        # Remove Normalized Product Type column if it exists
        if 'Normalized Product Type' in final_df.columns:
            final_df.drop(columns=['Normalized Product Type'], inplace=True)
        
        # Save to Excel on disk and memory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        current_inventory_dir = os.path.join(script_dir, '..', 'current_inventory')
        os.makedirs(current_inventory_dir, exist_ok=True)
        
        # Use correct filename
        current_inventory_path = os.path.join(current_inventory_dir, f'DataBase_Rhize_Cannabis_Company_{today_date}.xlsx')

        with pd.ExcelWriter(current_inventory_path, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='Sheet1', index=False)
            grouped_df.to_excel(writer, sheet_name='store', index=False)
            removed_df = final_df[final_df['Flag'] == 'Removed']
            if not removed_df.empty:
                removed_df.to_excel(writer, sheet_name='Removed', index=False)

        self.excel_buffer = BytesIO()
        with pd.ExcelWriter(self.excel_buffer, engine='openpyxl') as writer:
            final_df.to_excel(writer, sheet_name='Sheet1', index=False)
            grouped_df.to_excel(writer, sheet_name='store', index=False)
            removed_df = final_df[final_df['Flag'] == 'Removed']
            if not removed_df.empty:
                removed_df.to_excel(writer, sheet_name='Removed', index=False)

        self.excel_buffer.seek(0)
        drive_resp = self.upload_to_drive(current_inventory_path,'1DutUCylz5t_Fx0vK63wJaAegfq61s-Af')
        print(f"Upload to Drive response: {drive_resp}")
        logging.info(f"Generated Excel file: {current_inventory_path}")
        return current_inventory_path

    
    def get_google_drive_credentials(self):
        """Get valid user credentials from storage"""
        creds = None
        script_dir = os.path.dirname(os.path.abspath(__file__))
        token_file = os.path.join(script_dir, 'token.pickle')
        
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
            # self.sender_user = mail_cfg.user
            # self.sender_pw = mail_cfg.pw
            sender_email = self.sender_user
            # receiver = mail_cfg.receiver if mail_to_prod else mail_cfg.receiver_test
            subject = "Rhize Cannabis Company - Change"
            body = f"Hi<br><br>Please find below the changes to the product for Rhize Cannabis Company:<br>{html}<br><br>Menu Scraping Team"
        except Exception as e:
            logging.error(f"Error retrieving email configurations: {str(e)}")
            return
        
        self.message = EmailMessage()
        self.message["From"] = f"{self.sender_name}<{sender_email}>"
        # self.message["To"] = receiver
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
        try:
            self.generate_flagged_xlsx(os.path.join(os.path.dirname(__file__), "notification_excel"), today_date)
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
            current_file_name = f'current_inventory/current_inventory_{today_date}.xlsx'
            script_dir = os.path.dirname(os.path.abspath(__file__))
            current_inventory_path = os.path.join(script_dir, current_file_name)
            
            with open(current_inventory_path, 'rb') as file:
                self.message.add_attachment(
                    file.read(),
                    maintype=mime_type,
                    subtype=mime_subtype,
                    filename=current_file_name)
              
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
                # smtp.sendmail(sender_email, receiver, self.message.as_string())
            print("-->Notification sent successfully!")
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
        print("-->End")

    def send_log_notification(self, log_file_name, mail_to_prod=True):
        """Send log file via email"""
        print("\n-->Start sending log email notification")
        
        try:
            # self.sender_user = mail_cfg.user
            # self.sender_pw = mail_cfg.pw
            sender_email = self.sender_user
            # receiver = mail_cfg.receiver if mail_to_prod else mail_cfg.receiver_test
            subject = "Rhize Cannabis Company - Scraping Log"
            body = f"Hi<br><br>Please find attached the scraping log for Rhize Cannabis Company.<br><br>Menu Scraping Team"
        except Exception as e:
            logging.error(f"Error retrieving email configurations: {str(e)}")
            return
        
        self.message = EmailMessage()
        self.message["From"] = f"{self.sender_name}<{sender_email}>"
        # self.message["To"] = receiver
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
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=self.context) as smtp:
                smtp.login(sender_email, self.sender_pw)
                # smtp.sendmail(sender_email, receiver, self.message.as_string())
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

def generate_combined_excel(data_dir: str = "data_base", output_dir: str = "reports"):
    """Generate single comprehensive Excel file for all stores with multiple sheets"""
    processor = DataProcessor()
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Use the new generate_flagged_xlsx method instead
    excel_file = processor.generate_flagged_xlsx("notification_excel", today)
    
    if excel_file:
        logging.info(f"Generated comprehensive Excel file: {excel_file}")
        return excel_file
    else:
        logging.warning("Failed to generate Excel file")
        return None

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

def update_main_excel_with_flags(comparison_data: Dict[str, Any], output_dir: str = "reports"):
    """Update the main Excel file with flags and removed products sheet"""
    # This is handled within generate_flagged_xlsx now
    return None