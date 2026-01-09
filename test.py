from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def open_website():
    # Configure Chrome options
    chrome_options = Options()
    # chrome_options.add_argument('--headless')  # Uncomment to run in headless mode
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--start-maximized')
    
    # Initialize the Chrome driver
    # If you have chromedriver in your PATH, you can use:
    driver = webdriver.Chrome(options=chrome_options)
    
    # Or specify the path to chromedriver explicitly:
    # service = Service('/path/to/chromedriver')
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Open the website
        url = "https://dutchie.com/stores/garcias-cannabis-collective/products?brands=rhize-cannabis-co"
        print(f"Opening {url}...")
        driver.get(url)
        
        # Wait for the page to load
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        print(f"Page title: {driver.title}")
        print(f"Current URL: {driver.current_url}")
        
        # Keep the browser open for 5 seconds
        time.sleep(5)
        
        # Example: Find an element (uncomment and modify as needed)
        # element = driver.find_element(By.ID, "element_id")
        # element.click()
        
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        # Close the browser
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    open_website()