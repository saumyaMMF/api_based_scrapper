"""Main scraper application - Using your old working functions"""

import sys
import logging
import time
import os
from datetime import datetime
from pathlib import Path

# Import scrapers
from scrapers.leafly_scraper import scrape_leafly
from scrapers.dutchie_scraper import scrape_dutchie
from scrapers.iheartjane_scraper import scrape_iheartjane
from scrapers.gramcentral_scraper import scrape_gramcentral
from scrapers.mothaplant_scraper import scrape_mothaplant
from scrapers.valleymeade_scraper import scrape_valleymeade
from scrapers.teahouse_scraper import scrape_teahouse

# Import utilities
from utils.common import setup_logging, load_config, save_products_by_date, upload_to_drive
from utils.data_processing import DataProcessor, compare_with_yesterday

# Map URL patterns to scraper functions
SCRAPER_MAP = {
    'leafly': scrape_leafly,
    'dutchie': scrape_dutchie,
    'iheartjane': scrape_iheartjane,
    'gramcentral': scrape_gramcentral,
    'mothaplant': scrape_mothaplant,
    'dispenseapp': scrape_valleymeade,  # Valley Meade uses dispenseapp
    'dispensary.shop':scrape_teahouse
}

MAIL_TO_PROD = True

def get_scraper_function(store_url: str):
    """Get the appropriate scraper function based on URL"""
    url_lower = store_url.lower()
    
    for platform, scraper_func in SCRAPER_MAP.items():
        if platform in url_lower:
            return scraper_func
    
    raise ValueError(f"No scraper available for URL: {store_url}")

def normalize_company_name(company_name: str) -> str:
    """Normalize company name for consistent mapping"""
    return company_name.lower().replace(" ", "").replace("-", "").replace("_", "")

def print_summary(successful: int, failed: int, total_products: int, total_skus: int, duration: float):
    """Print an enhanced summary with SKU information"""
    print("\n" + "="*60)
    print(" SCRAPING COMPLETED!")
    print("="*60)
    print(f"Successful stores: {successful}")
    print(f"Failed stores: {failed}")
    print(f"Total products: {total_products}")
    print(f" Unique SKUs generated: {total_skus}")
    print(f" Duration: {duration:.2f} seconds")
    
    if successful > 0:
        avg_products = total_products / successful
        avg_skus = total_skus / successful
        print(f" Average: {avg_products:.1f} products per store")
        print(f"Average: {avg_skus:.1f} SKUs per store")
    
    print("="*60)

def print_sku_comparison_summary(comparison_data: dict):
    """Print summary of SKU-based changes"""
    if not comparison_data:
        return
    
    print(f"\n SKU-based Changes from yesterday:")
    total_added = sum(data["added"] for data in comparison_data.values())
    total_removed = sum(data["removed"] for data in comparison_data.values())
    total_updated = sum(data["updated"] for data in comparison_data.values())
    
    print(f"   Added: {total_added} SKUs")
    print(f"   Removed: {total_removed} SKUs")
    print(f"   Updated: {total_updated} SKUs")
    
    # Show per-company breakdown
    print(f"\n   Per Company:")
    for company, data in comparison_data.items():
        net_change = data["total_today"] - data.get("total_yesterday", 0)
        change_indicator = "📈" if net_change > 0 else "📉" if net_change < 0 else "➡️"
        print(f"     {company}: {change_indicator} {net_change:+d} SKUs ({data['added']}+/{data['removed']}-/{data['updated']}~)")

def generate_html_summary(comparison_data: dict) -> str:
    """Generate HTML summary for email notification"""
    if not comparison_data:
        return "<p>No changes detected.</p>"
    
    html = "<table border='1' style='border-collapse: collapse; margin: 20px 0;'>"
    html += "<tr style='background-color: #f2f2f2;'>"
    html += "<th style='padding: 8px;'>Company</th>"
    html += "<th style='padding: 8px;'>Added</th>"
    html += "<th style='padding: 8px;'>Removed</th>"
    html += "<th style='padding: 8px;'>Updated</th>"
    html += "<th style='padding: 8px;'>Total Today</th>"
    html += "<th style='padding: 8px;'>Net Change</th>"
    html += "</tr>"
    
    total_added = 0
    total_removed = 0
    total_updated = 0
    
    for company, data in comparison_data.items():
        net_change = data["total_today"] - data.get("total_yesterday", 0)
        change_color = "green" if net_change > 0 else "red" if net_change < 0 else "black"
        
        html += f"<tr>"
        html += f"<td style='padding: 8px;'>{company}</td>"
        html += f"<td style='padding: 8px; color: green;'>{data['added']}</td>"
        html += f"<td style='padding: 8px; color: red;'>{data['removed']}</td>"
        html += f"<td style='padding: 8px; color: orange;'>{data['updated']}</td>"
        html += f"<td style='padding: 8px;'>{data['total_today']}</td>"
        html += f"<td style='padding: 8px; color: {change_color};'>{net_change:+d}</td>"
        html += f"</tr>"
        
        total_added += data['added']
        total_removed += data['removed']
        total_updated += data['updated']
    
    # Add summary row
    html += "<tr style='background-color: #f9f9f9; font-weight: bold;'>"
    html += "<td style='padding: 8px;'>TOTAL</td>"
    html += f"<td style='padding: 8px; color: green;'>{total_added}</td>"
    html += f"<td style='padding: 8px; color: red;'>{total_removed}</td>"
    html += f"<td style='padding: 8px; color: orange;'>{total_updated}</td>"
    html += "<td style='padding: 8px;'>-</td>"
    html += "<td style='padding: 8px;'>-</td>"
    html += "</tr>"
    
    html += "</table>"
    
    return html

def main():
    """Enhanced main application entry point using your old working functions"""
    
    # Setup logging
    logger = setup_logging()
    
    logger.info(" Enhanced Cannabis Scraper Started (using your old working functions)")
    print(" Enhanced Cannabis Scraper Started (using your old working functions)")
    
    start_time = time.time()
    
    # Initialize data processor with your old functions
    data_processor = DataProcessor()
    
    try:
        # Load store configurations
        script_dir = Path(__file__).parent
        config_path = script_dir / "config" / "website_list.json"
        stores = load_config(config_path)
        if not stores:
            logger.error("No stores to process")
            return 1
        
        logger.info(f"Loaded {len(stores)} store configurations")
        print(f" Loaded {len(stores)} stores to process")
        
        # Track results
        successful = 0
        failed = 0
        total_products = 0
        all_skus = set()  # Track unique SKUs
        
        # Process each store
        for i, store in enumerate(stores, 1):
            company_name = store["Company name"]
            normalized_company = normalize_company_name(company_name)
            
            print(f"\n[{i}/{len(stores)}] Processing: {company_name}")
            logger.info(f"[{i}/{len(stores)}] Processing: {company_name}")
            
            try:
                # Get the appropriate scraper
                scraper_func = get_scraper_function(store["Store url"])
                
                # Run scraper
                products = scraper_func(store)
                
                if products:
                    # Save data with company name for SKU generation
                    save_products_by_date(products, store["Data_base"], normalized_company)
                    
                    # Count SKUs generated
                    from utils.common import enhance_product_with_mapping
                    enhanced_products = [enhance_product_with_mapping(p, normalized_company) for p in products]
                    product_skus = {p.get("SKU") for p in enhanced_products if p.get("SKU")}
                    all_skus.update(product_skus)
                    
                    successful += 1
                    total_products += len(products)
                    print(f" Success: {len(products)} products, {len(product_skus)} SKUs")
                    
                    # Log some sample SKUs for debugging
                    if product_skus:
                        sample_skus = list(product_skus)[:3]
                        logger.info(f"Sample SKUs for {company_name}: {sample_skus}")
                else:
                    failed += 1
                    print(f" Failed: No products found")
                    
            except Exception as e:
                logger.error(f" {company_name}: {e}")
                print(f" Error: {e}")
                failed += 1
                continue
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Generate reports and handle notifications using your old functions
        print("\n Generating reports and sending notifications using your old functions...")
        logger.info("Generating reports and sending notifications using your old functions...")
        
        try:
            # Step 1: Run comparison logic using your old function
            print(" Starting comparison_with_yesterday()...")
            note, comparison_data, removed_rows = data_processor.compare_with_yesterday("data_base")
            today_str = datetime.now().strftime("%Y-%m-%d")
            # data_processor.append_removed_products_log(removed_rows, today_str)
            if removed_rows:
                data_processor.append_removed_products_log(removed_rows, today_str)
            else:
                print("No removed products to append to cumulative log.")
                
            if comparison_data:
                print(f" Comparison completed using your old comparison logic")
                print_sku_comparison_summary(comparison_data)
            else:
                print("  No yesterday data found for comparison")

            time.sleep(2)
            
            # Step 2: Generate the main Excel file using your old generate_flagged_xlsx function
            today_date = datetime.now().strftime('%Y-%m-%d')
            excel_file = data_processor.generate_flagged_xlsx("notification_excel", today_date)
            
            if excel_file:
                print(f" Generated Excel using your old generate_flagged_xlsx function: {excel_file}")
                logger.info(f"Generated Excel using old function: {excel_file}")
                
                # Step 3: Send email notification using your old email functions
                if comparison_data:
                    # Generate HTML summary for email
                    html_summary = generate_html_summary(comparison_data)
                    if note:
                        html_summary += f"<br><hr><h3>SKU-Level Details</h3><br>{note}"
                    # Send notification email using your old function
                    try:
                        data_processor.send_notification(html_summary, mail_to_prod=MAIL_TO_PROD)
                        print(" Email notification sent using your old send_notification function")
                        logger.info("Email notification sent using old function")
                    except Exception as e:
                        logger.error(f"Failed to send email notification: {e}")
                        print(f"  Failed to send email notification: {e}")
                else:
                    print("📧 No changes detected - no email notification sent")
                
            else:
                print("  No Excel file generated - check your old generate_flagged_xlsx function")
                logger.warning("No Excel file generated")
        
        except Exception as e:
            logger.error(f"Error in report generation/notification: {e}")
            print(f" Error in report generation/notification: {e}")
        
        # Send log file notification using your old function
        try:
            # Get the most recent log file
            log_dir = Path("logs")
            if log_dir.exists():
                log_files = list(log_dir.glob("scraper_*.log"))
                if log_files:
                    latest_log = max(log_files, key=os.path.getctime)
                    data_processor.send_log_notification(str(latest_log), mail_to_prod=MAIL_TO_PROD)
                    print(f" Log notification sent using your old send_log_notification function: {latest_log.name}")
                    logger.info(f"Log notification sent using old function: {latest_log.name}")
        except Exception as e:
            logger.error(f"Failed to send log notification: {e}")
            print(f"  Failed to send log notification: {e}")
        
        # Print final summary with SKU information
        print_summary(successful, failed, total_products, len(all_skus), duration)
        
        # Log SKU statistics
        logger.info(f"Scraping completed: {successful} successful, {failed} failed, {total_products} total products, {len(all_skus)} unique SKUs")
        
        if all_skus:
            # Log sample of generated SKUs
            sample_skus = sorted(list(all_skus))[:10]
            logger.info(f"Sample generated SKUs: {sample_skus}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
        print(f" Critical error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)