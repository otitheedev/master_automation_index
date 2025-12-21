import os
import time
import sys
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Centralized logging
try:
    # Get absolute path and resolve project root
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    project_root = os.path.dirname(os.path.dirname(current_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback to basic logging if logging_config not available
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


LOGIN_URL = "https://acc.otithee.com/login"
INVOICE_LIST_URL = "https://acc.otithee.com/invoice-generate/over-25-lakh"

# Default credentials (can be overridden)
USERNAME = "needyamin@otithee.com"
PASSWORD = "*#r@@t2025#"

DOWNLOAD_DIR = str(Path(__file__).resolve().parent / "downloads")


def create_driver() -> webdriver.Chrome:
    """
    Create and configure a Chrome WebDriver instance with automatic download
    to the local 'downloads' directory next to this script.
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    chrome_options = webdriver.ChromeOptions()

    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        # Ensure PDFs and similar files are downloaded instead of opened in-browser
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # If you prefer headless mode, uncomment the next line:
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Get chromedriver path and ensure it's the executable
    try:
        driver_path = ChromeDriverManager().install()
        
        # Check if the path points to a wrong file (like THIRD_PARTY_NOTICES.chromedriver)
        if os.path.isfile(driver_path) and driver_path.endswith('.chromedriver'):
            # This is wrong - look for the actual chromedriver in the same directory
            driver_dir = os.path.dirname(driver_path)
            actual_driver = os.path.join(driver_dir, 'chromedriver')
            if os.path.isfile(actual_driver):
                driver_path = actual_driver
            else:
                # Search in parent directories
                parent_dir = os.path.dirname(driver_dir)
                actual_driver = os.path.join(parent_dir, 'chromedriver')
                if os.path.isfile(actual_driver):
                    driver_path = actual_driver
        
        # If the path points to a directory, look for the actual executable
        if os.path.isdir(driver_path):
            # Look for chromedriver executable in the directory
            possible_names = ['chromedriver', 'chromedriver.exe']
            found = False
            for name in possible_names:
                exec_path = os.path.join(driver_path, name)
                if os.path.isfile(exec_path):
                    driver_path = exec_path
                    found = True
                    break
            
            # If not found in direct directory, search recursively
            if not found:
                for root, dirs, files in os.walk(driver_path):
                    for name in possible_names:
                        exec_path = os.path.join(root, name)
                        if os.path.isfile(exec_path) and not exec_path.endswith('.chromedriver'):
                            driver_path = exec_path
                            found = True
                            break
                    if found:
                        break
        
        # Ensure the driver path is executable (Linux/Mac)
        if os.path.isfile(driver_path) and not driver_path.endswith('.exe'):
            try:
                # Make sure it's the actual chromedriver, not a .chromedriver file
                if not driver_path.endswith('.chromedriver'):
                    os.chmod(driver_path, 0o755)
            except Exception as e:
                logger.warning(f"Could not set executable permissions: {e}")
        
        # Verify the file is actually executable
        if os.path.isfile(driver_path) and driver_path.endswith('.chromedriver'):
            raise ValueError(f"Invalid chromedriver path: {driver_path}")
        
        service = Service(driver_path)
    except Exception as e:
        logger.warning(f"Error with ChromeDriverManager: {e}. Trying without explicit path...")
        # Fallback: let Selenium find chromedriver automatically
        service = Service()
    
    driver = webdriver.Chrome(
        service=service,
        options=chrome_options,
    )
    driver.maximize_window()
    return driver


def login(driver: webdriver.Chrome, username: str = None, password: str = None) -> None:
    """
    Log into the Accounting Department Portal using the provided credentials.
    """
    # Use provided credentials or fall back to defaults
    username = username or USERNAME
    password = password or PASSWORD
    
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    email_input = wait.until(EC.presence_of_element_located((By.ID, "email")))
    password_input = wait.until(EC.presence_of_element_located((By.ID, "password")))

    email_input.clear()
    email_input.send_keys(username)

    password_input.clear()
    password_input.send_keys(password)

    # Click the Login button
    login_button = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Login')]"))
    )
    login_button.click()

    # Wait until we are no longer on the login page
    # Handle case where current_url might be None
    wait.until(lambda d: d.current_url is not None and "login" not in d.current_url.lower())


def collect_invoice_links(driver: webdriver.Chrome) -> list[str]:
    """
    Go to the Over 25 Lakh invoice page and collect all invoice download links.
    """
    driver.get(INVOICE_LIST_URL)
    wait = WebDriverWait(driver, 30)

    # Wait until at least one invoice download link is present.
    # These links look like: https://acc.otithee.com/invoice-download-over25/01711395909
    try:
        wait.until(
            EC.presence_of_all_elements_located(
                (By.XPATH, "//a[contains(@href,'invoice-download-over25')]")
            )
        )
    except Exception:
        # If we time out, fall through and attempt to collect whatever is present.
        pass

    anchors = driver.find_elements(
        By.XPATH, "//a[contains(@href,'invoice-download-over25')]"
    )
    invoice_hrefs: list[str] = []

    for a in anchors:
        href = a.get_attribute("href")
        text = (a.text or "").strip().lower()
        if href and "invoice-download-over25" in href and text == "invoice":
            invoice_hrefs.append(href)

    return invoice_hrefs


def download_invoices(driver: webdriver.Chrome, hrefs: list[str]) -> None:
    """
    Open each invoice download URL in a new tab to trigger the file downloads.
    """
    total = len(hrefs)
    print(f"Found {total} invoice links.")

    for idx, href in enumerate(hrefs, start=1):
        print(f"[{idx}/{total}] Downloading from: {href}")
        # Open the download link in a new tab to keep the main page intact
        driver.execute_script("window.open(arguments[0], '_blank');", href)
        # Small delay per download so the browser can start each download
        time.sleep(2)

    # Wait some extra time for all downloads to finish
    print("Waiting for downloads to complete...")
    time.sleep(15)


def main() -> None:
    print(f"Downloads will be saved to: {DOWNLOAD_DIR}")
    driver = create_driver()

    try:
        print("Logging in...")
        login(driver)

        print("Collecting invoice links...")
        hrefs = collect_invoice_links(driver)

        if not hrefs:
            print("No invoice links found on the page.")
            return

        download_invoices(driver, hrefs)
        print("All invoice downloads triggered.")
    finally:
        driver.quit()
        print("Browser closed.")


if __name__ == "__main__":
    main()


