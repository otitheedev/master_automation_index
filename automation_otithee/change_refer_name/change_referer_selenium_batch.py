# change_referer_selenium_full.py
# pip install selenium webdriver-manager pandas
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
LOGIN_URL = "https://accounting.test/login"
CHANGE_REFERER_URL = "https://accounting.test/change-referer"
USERNAME = "needyamin@otithee.com"
PASSWORD = "Y123456789"
INPUT_CSV = "data.csv"
OUTPUT_CSV = "results.csv"
HEADLESS = False   # True to run without opening Chrome window

# Wait timeouts (tune if your server is slow)
PAGE_WAIT = 15        # general wait for pages/elements
POPULATE_WAIT = 30    # wait for AJAX population after entering entrepreneurNumber
SHORT_WAIT = 3        # quick detection for loader visibility
# ----------------------------

def setup_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    # recommended flags for CI / Linux
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_window_size(1200, 900)
    return driver

def login(driver):
    wait = WebDriverWait(driver, PAGE_WAIT)
    driver.get(LOGIN_URL)

    # Try common username/email selectors
    possible_user_selectors = ['input[name="email"]', 'input[name="username"]', 'input[type="email"]', 'input[type="text"]']
    user_elem = None
    for sel in possible_user_selectors:
        try:
            e = driver.find_element(By.CSS_SELECTOR, sel)
            if e.is_displayed():
                user_elem = e
                break
        except:
            continue
    if not user_elem:
        raise RuntimeError("Username/email input not found. Update selectors.")

    # password input
    try:
        pwd_elem = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
    except:
        raise RuntimeError("Password input not found. Update selector.")

    # fill and submit
    user_elem.clear(); user_elem.send_keys(USERNAME)
    pwd_elem.clear(); pwd_elem.send_keys(PASSWORD)

    # submit: prefer clickable submit button, otherwise try form submit
    try:
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"], button')))
        driver.execute_script("arguments[0].click();", submit_btn)
    except TimeoutException:
        try:
            pwd_elem.submit()
        except Exception:
            pass

    # wait for navigation or presence of entrepreneurNumber as login success marker
    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        # fallback: wait for entrepreneurNumber if available
        try:
            WebDriverWait(driver, PAGE_WAIT).until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
        except TimeoutException:
            # if still not present, proceed but login may not have succeeded
            raise RuntimeError("Login appears to have failed or took too long.")

def submit_one(driver, entrepreneur_num, referer_num):
    short_wait = WebDriverWait(driver, SHORT_WAIT)
    wait = WebDriverWait(driver, POPULATE_WAIT)

    driver.get(CHANGE_REFERER_URL)

    # 1) Wait for form inputs present
    wait.until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
    # locate elements after presence check
    ent = driver.find_element(By.ID, "entrepreneurNumber")
    ref = driver.find_element(By.ID, "entrepreneurReferer")

    # normalize numbers (strings) with leading zero
    entrepreneur_num = "0" + str(entrepreneur_num).lstrip("0")
    referer_num = "0" + str(referer_num).lstrip("0")

    # 2) Type entrepreneurNumber (this triggers AJAX)
    ent.clear()
    ent.send_keys(entrepreneur_num)

    # Ensure the input reached the length that triggers AJAX (your JS checks >= 10)
    try:
        wait.until(lambda d: len(d.find_element(By.ID, "entrepreneurNumber").get_attribute("value") or "") >= 10)
    except TimeoutException:
        # length didn't reach threshold in time — continue to populate wait (may still work)
        pass

    # 3) Wait for AJAX population (only TimeoutException is used for control flow)
    loader_loc = (By.ID, "loadingIndicator")
    populated = False

    try:
        # If loader quickly appears, wait for it's invisibility (preferred)
        short_wait.until(EC.visibility_of_element_located(loader_loc))
        wait.until(EC.invisibility_of_element_located(loader_loc))
        populated = True
    except TimeoutException:
        # loader didn't show within SHORT_WAIT — fallback to waiting for fields to populate
        try:
            wait.until(
                lambda d: (
                    (d.find_elements(By.ID, "entrepreneurReferer") and (d.find_element(By.ID, "entrepreneurReferer").get_attribute("value") or "").strip() != "")
                    or (d.find_elements(By.ID, "entrepreneurName") and (d.find_element(By.ID, "entrepreneurName").get_attribute("value") or "").strip() != "")
                )
            )
            populated = True
        except TimeoutException:
            # final fallback: try to wait for loader invisibility once more (in case loader already present)
            try:
                wait.until(EC.invisibility_of_element_located(loader_loc))
                populated = True
            except TimeoutException:
                return False, f"Timeout waiting for AJAX population after entering entrepreneurNumber {entrepreneur_num}"

    # 4) Ensure referer input ready and fill it
    try:
        wait.until(EC.presence_of_element_located((By.ID, "entrepreneurReferer")))
        wait.until(EC.element_to_be_clickable((By.ID, "entrepreneurReferer")))
    except TimeoutException:
        return False, f"Timeout waiting for entrepreneurReferer to become ready for {entrepreneur_num}"

    ref = driver.find_element(By.ID, "entrepreneurReferer")
    ref.clear()
    ref.send_keys(referer_num)

    # 5) Click submit (wait until clickable)
    try:
        submit_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "form#entrepreneurForm button[type='submit'], form#entrepreneurForm button")
        ))
    except TimeoutException:
        return False, "Timeout waiting for submit button to become clickable"

    driver.execute_script("arguments[0].click();", submit_btn)

    # 6) Wait for response: outputResponse value or flash message
    try:
        wait.until(
            lambda d: (
                (d.find_elements(By.ID, "outputResponse") and (d.find_element(By.ID, "outputResponse").get_attribute("value") or "").strip() != "")
                or any(el.is_displayed() and (el.text or "").strip() for el in d.find_elements(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success"))
            )
        )
    except TimeoutException:
        return False, "Timeout waiting for response after submit"

    # Prefer outputResponse
    if driver.find_elements(By.ID, "outputResponse"):
        out_val = (driver.find_element(By.ID, "outputResponse").get_attribute("value") or "").strip()
        if out_val:
            return True, out_val

    # Otherwise read first visible flash
    flashes = driver.find_elements(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success")
    for f in flashes:
        if f.is_displayed() and (f.text or "").strip():
            return True, f.text.strip()[:1000]

    return True, "Submitted — no textual response captured"

def main():
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    if not {"entrepreneurNumber", "refererNumber"}.issubset(df.columns):
        raise SystemExit("CSV must contain columns: entrepreneurNumber, refererNumber")

    driver = setup_driver()
    try:
        login(driver)
        results = []
        for idx, row in df.iterrows():
            ent = row['entrepreneurNumber']
            ref = row['refererNumber']
            try:
                ok, resp = submit_one(driver, ent, ref)
                status = "ok" if ok else "failed"
            except Exception as e:
                status = "error"
                resp = str(e)

            print(f"[{idx}] {ent} -> {ref} => {status}")
            results.append({
                "entrepreneurNumber": "0" + str(ent).lstrip("0"),
                "refererNumber": "0" + str(ref).lstrip("0"),
                "status": status,
                "response": resp
            })

        pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        print("All done. Results saved to", OUTPUT_CSV)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
