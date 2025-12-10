# ============================================================================
# SIMPLE JSON/EXCEL UPLOADER - No Date Patterns Required
# ============================================================================

import os
import json
from pathlib import Path
import pandas as pd
import pymysql
from dotenv import load_dotenv

load_dotenv()

# MySQL Configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
    'port': int(os.getenv('MYSQL_PORT'))
}


def create_mysql_connection():
    """Create and return a MySQL connection."""
    try:
        connection = pymysql.connect(
            host=os.getenv('MYSQL_HOST'),
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            db=os.getenv('MYSQL_DATABASE'),
            port=int(os.getenv('MYSQL_PORT')),
        )
        if connection.open:
            print("✓ Connection to MySQL database successful")
            return connection
    except Exception as e:
        print(f"✗ Error connecting to MySQL: {e}")
        return None


def safe_convert_for_mysql(df):
    """Convert all columns to types compatible with MySQL."""
    for column in df.columns:
        try:
            sample = df[column].dropna().head(1)
            if len(sample) == 0:
                df[column] = df[column].astype(str)
                continue

            dtype = df[column].dtype
            sample_value = sample.iloc[0]

            if pd.api.types.is_float_dtype(dtype):
                if df[column].dropna().apply(lambda x: x.is_integer()).all():
                    df[column] = df[column].astype('Int64')
            elif isinstance(dtype, pd.CategoricalDtype):
                df[column] = df[column].astype(str)
            elif pd.api.types.is_object_dtype(dtype):
                if isinstance(sample_value, (list, dict, set, tuple)):
                    df[column] = df[column].apply(lambda x: str(x) if x is not None else None)
                try:
                    converted_col = pd.to_datetime(df[column], format="%Y-%m-%d %H:%M:%S", errors='coerce')
                    if converted_col.notna().sum() > 0:
                        df[column] = converted_col.dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        df[column] = df[column].astype(str)
                except Exception:
                    df[column] = df[column].astype(str)
            elif pd.api.types.is_datetime64_dtype(dtype):
                df[column] = df[column].dt.strftime('%Y-%m-%d %H:%M:%S')
            elif pd.api.types.is_timedelta64_dtype(dtype):
                df[column] = df[column].apply(lambda x: str(x.total_seconds()) if pd.notnull(x) else None)
        except Exception as e:
            print(f"Warning: Error converting column {column}. Converting to string. Error: {str(e)}")
            df[column] = df[column].astype(str)
    return df


def get_mysql_type(pandas_dtype, column_values):
    """Map pandas dtypes to MySQL data types."""
    if pd.api.types.is_datetime64_dtype(pandas_dtype):
        return "DATETIME"
    elif pd.api.types.is_bool_dtype(pandas_dtype):
        return "TINYINT(1)"
    elif pd.api.types.is_integer_dtype(pandas_dtype):
        max_val = column_values.max() if not column_values.empty else 0
        if max_val <= 127:
            return "TINYINT"
        elif max_val <= 32767:
            return "SMALLINT"
        elif max_val <= 8388607:
            return "MEDIUMINT"
        elif max_val <= 2147483647:
            return "INT"
        else:
            return "BIGINT"
    elif pd.api.types.is_float_dtype(pandas_dtype):
        return "DOUBLE"
    else:
        non_null_values = column_values.dropna()
        if len(non_null_values) > 0:
            max_length = non_null_values.astype(str).str.len().max()
            if max_length <= 65535:
                return "TEXT"
            elif max_length <= 16777215:
                return "MEDIUMTEXT"
            else:
                return "LONGTEXT"
        return "VARCHAR(255)"


def upload_dataframe(df, table_name):
    """Insert dataframe into MySQL table with dynamic schema creation."""
    try:
        df = df.copy()
        df.drop(df.columns[df.columns.str.contains('unnamed', case=False)], axis=1, inplace=True)
        df = safe_convert_for_mysql(df)

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
                `date` DATE DEFAULT (CURRENT_DATE),
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


def flatten_json_to_dataframe(json_file_path):
    """Convert nested JSON (date-based) to a flat DataFrame."""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_records = []
    
    for date_key, products in data.items():
        for product in products:
            flat_record = {
                'date': date_key,
                'product_name': product.get('Product name', ''),
                'category': product.get('Category', ''),
                'brand': product.get('Brand', ''),
                'days_on_shelf': product.get('Days on Shelf', 0)
            }
            
            if 'Price' in product and isinstance(product['Price'], dict):
                for unit, price in product['Price'].items():
                    flat_record[f'price_{unit}'] = price
            
            all_records.append(flat_record)
    
    return pd.DataFrame(all_records)


def upload_single_json(json_file_path, table_name=None):
    """
    Upload a single JSON file to database.
    
    Args:
        json_file_path (str): Path to JSON file
        table_name (str, optional): Custom table name. If None, uses filename as-is
        
    Example:
        upload_single_json('db_store.json')  # Table name: 'db_store'
        upload_single_json('data.json', 'my_table')  # Table name: 'my_table'
    """
    try:
        if not os.path.exists(json_file_path):
            print(f"✗ Error: File '{json_file_path}' not found!")
            return
        
        if table_name is None:
            # Keep filename as-is, only remove extension and replace invalid chars
            table_name = os.path.splitext(os.path.basename(json_file_path))[0]
            table_name = table_name.replace('.', '_').replace('-', '_').replace(' ', '_')
        
        print(f"\n{'='*60}")
        print(f"Processing: {json_file_path}")
        print(f"Table name: {table_name}")
        print(f"{'='*60}\n")
        
        print("Reading and flattening JSON file...")
        df = flatten_json_to_dataframe(json_file_path)
        print(f"✓ Loaded {len(df)} rows and {len(df.columns)} columns")
        print(f"  Columns: {', '.join(df.columns.tolist())}\n")
        
        print("Inserting data into MySQL...")
        result = upload_dataframe(df, table_name)
        print(f"\n{result}\n")
        
    except Exception as e:
        print(f"✗ Error processing file: {e}")


def upload_all_json_from_folder(folder_path):
    """
    Upload all JSON files from a folder.
    
    Args:
        folder_path (str): Path to folder containing JSON files
        
    Example:
        upload_all_json_from_folder('data/json_files')
        upload_all_json_from_folder('D:/Projects/Rhize_scapper/data_base')
    """
    try:
        if not os.path.exists(folder_path):
            print(f"✗ Error: Folder '{folder_path}' not found!")
            return
        
        json_files = list(Path(folder_path).glob('*.json'))
        
        if not json_files:
            print(f"✗ No JSON files found in '{folder_path}'")
            return
        
        print(f"\n{'='*60}")
        print(f"FOUND {len(json_files)} JSON FILE(S) IN FOLDER")
        print(f"{'='*60}\n")
        
        for idx, file_path in enumerate(json_files, 1):
            print(f"\n[{idx}/{len(json_files)}] Processing: {file_path.name}")
            print("-" * 60)
            
            # table_name = file_path.stem.replace('.', '_').replace('-', '_').replace(' ', '_')
            
            try:
                df = flatten_json_to_dataframe(str(file_path))
                print(f"✓ Loaded {len(df)} rows")
                
                table_name = os.getenv("db_table_name")
                result = upload_dataframe(df, table_name)
                print(result)
                
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print(f"\n{'='*60}")
        print("BATCH UPLOAD COMPLETE!")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def upload_single_excel(excel_file_path, table_name=None):
    """
    Upload a single Excel file to database.
    
    Args:
        excel_file_path (str): Path to Excel file
        table_name (str, optional): Custom table name. If None, uses filename
        
    Example:
        upload_single_excel('data.xlsx', 'my_table')
        upload_single_excel('report.xlsx')  # Table name will be 'report'
    """
    try:
        if not os.path.exists(excel_file_path):
            print(f"✗ Error: File '{excel_file_path}' not found!")
            return
        
        if table_name is None:
            table_name = os.path.splitext(os.path.basename(excel_file_path))[0]
            table_name = table_name.replace('.', '_').replace('-', '_').replace(' ', '_')
        
        print(f"\n{'='*60}")
        print(f"Processing: {excel_file_path}")
        print(f"Table name: {table_name}")
        print(f"{'='*60}\n")
        
        print("Reading Excel file...")
        df = pd.read_excel(excel_file_path)
        print(f"✓ Loaded {len(df)} rows and {len(df.columns)} columns")
        print(f"  Columns: {', '.join(df.columns.tolist())}\n")
        
        print("Inserting data into MySQL...")
        result = upload_dataframe(df, table_name)
        print(f"\n{result}\n")
        
    except Exception as e:
        print(f"✗ Error processing file: {e}")


def upload_all_excel_from_folder(folder_path):
    """
    Upload all Excel files from a folder.
    
    Args:
        folder_path (str): Path to folder containing Excel files
        
    Example:
        upload_all_excel_from_folder('data/excel_files')
        upload_all_excel_from_folder('D:/Reports')
    """
    try:
        if not os.path.exists(folder_path):
            print(f"✗ Error: Folder '{folder_path}' not found!")
            return
        
        excel_files = list(Path(folder_path).glob('*.xlsx'))
        
        if not excel_files:
            print(f"✗ No Excel files found in '{folder_path}'")
            return
        
        print(f"\n{'='*60}")
        print(f"FOUND {len(excel_files)} EXCEL FILE(S) IN FOLDER")
        print(f"{'='*60}\n")
        
        for idx, file_path in enumerate(excel_files, 1):
            print(f"\n[{idx}/{len(excel_files)}] Processing: {file_path.name}")
            print("-" * 60)
            
            table_name = file_path.stem.replace('.', '_').replace('-', '_').replace(' ', '_')
            
            try:
                df = pd.read_excel(str(file_path))
                print(f"✓ Loaded {len(df)} rows")
                
                result = upload_dataframe(df, table_name)
                print(result)
                
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print(f"\n{'='*60}")
        print("BATCH UPLOAD COMPLETE!")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def delete_data_by_date(table_name, date_value, date_column='date'):
    """
    Delete rows from a table for a specific date.
    
    Args:
        table_name (str): Name of the table
        date_value (str): Date string to match (e.g., '2023-10-27')
        date_column (str): Name of the date column (default: 'date')
    """
    try:
        connection = create_mysql_connection()
        if not connection:
            return "Failed to connect to MySQL database"
            
        cursor = connection.cursor()
        
        # Check if table exists
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return f"✗ Table '{table_name}' does not exist"
            
        # Check if column exists
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE '{date_column}'")
        if not cursor.fetchone():
            cursor.close()
            connection.close()
            return f"✗ Column '{date_column}' does not exist in table '{table_name}'"
            
        # Get count before delete
        count_sql = f"SELECT COUNT(*) FROM `{table_name}` WHERE `{date_column}` = %s"
        cursor.execute(count_sql, (date_value,))
        count = cursor.fetchone()[0]
        
        if count == 0:
            print(f"⚠ No records found for date '{date_value}' in table '{table_name}'")
            cursor.close()
            connection.close()
            return "No records deleted"
            
        # Delete
        delete_sql = f"DELETE FROM `{table_name}` WHERE `{date_column}` = %s"
        cursor.execute(delete_sql, (date_value,))
        connection.commit()
        
        cursor.close()
        connection.close()
        return f"✓ Successfully deleted {count} rows from '{table_name}' for date '{date_value}'"
        
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return str(e)
