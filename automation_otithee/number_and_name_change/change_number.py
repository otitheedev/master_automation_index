import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIG ---
LOGIN_URL = "https://administrator.otithee.com/login"
BASE_URL = "https://administrator.otithee.com"
TARGET_URL = f"{BASE_URL}/agent-ranking/agent/edit/"

EMAIL_OR_MOBILE = "0187857850401878578504"
PASSWORD = "Y123456789"

CSV_FILE = "data.xlsx"        # Must have columns: now, new, first_name, last_name
OUTPUT_FILE = "output2.csv"   # Save scraped results

# --- READ CSV SAFELY ---
try:
    data = pd.read_excel(CSV_FILE, engine='openpyxl')
except UnicodeDecodeError:
    print("Failed to read CSV as UTF-8, trying cp1252...")
    data = pd.read_csv(CSV_FILE, encoding="cp1252")

for col in ["now", "new", "first_name", "last_name"]:
    if col not in data.columns:
        raise ValueError(f"CSV must contain '{col}' column.")

# --- SETUP SELENIUM ---
options = Options()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 15)

# --- LOGIN ---
driver.get(LOGIN_URL)
time.sleep(2)

driver.find_element(By.NAME, "email").send_keys(EMAIL_OR_MOBILE)
driver.find_element(By.NAME, "password").send_keys(PASSWORD)

# Correct login button selector
login_button = driver.find_element(By.XPATH, "//button[contains(@class, 'auth-form-btn')]")
login_button.click()
time.sleep(3)

if driver.current_url == LOGIN_URL:
    print("Login failed! Check credentials or selectors.")
    driver.quit()
    exit()

# --- LOOP THROUGH PHONE NUMBERS ---
results = []

for idx, row in data.iterrows():
    now_number = str(row["now"]).strip()
    new_number = str(row["new"]).strip()
    first_name = str(row["first_name"]).strip()
    last_name = str(row["last_name"]).strip()

    # Ensure phone numbers start with 0
    if not now_number.startswith("0"):
        now_number = "0" + now_number
    if not new_number.startswith("0"):
        new_number = "0" + new_number

    url = f"{TARGET_URL}{now_number}"
    driver.get(url)
    time.sleep(2)

    try:
        # Enable and fill username, first_name, last_name
        for field_id in ["username", "first_name", "last_name"]:
            checkbox = driver.find_element(By.ID, f"edit_{field_id}")
            if not checkbox.is_selected():
                checkbox.click()
            input_field = driver.find_element(By.ID, field_id)
            input_field.clear()
            if field_id == "username":
                input_field.send_keys(new_number)
            elif field_id == "first_name":
                input_field.send_keys(first_name)
            elif field_id == "last_name":
                input_field.send_keys(last_name)

        # Wait until jQuery-enabled submit button is clickable
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.btn-primary")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
        driver.execute_script("arguments[0].click();", submit_button)
        time.sleep(2)

        results.append({"now": now_number, "new": new_number, "status": "Success"})
        print(f"Updated {now_number} successfully.")

    except Exception as e:
        print(f"Failed to update {now_number}: {e}")
        results.append({"now": now_number, "new": new_number, "status": f"Failed: {e}"})

# --- SAVE RESULTS ---
pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
print(f"Update completed. Results saved to {OUTPUT_FILE}")
driver.quit()
