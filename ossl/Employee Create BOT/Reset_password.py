import re
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select
from webdriver_manager.chrome import ChromeDriverManager

from automation import ADMIN_EMAIL, ADMIN_PASSWORD


# Base URL of your live HR system
BASE_URL = "https://o-erp.otithee.com/"
EMPLOYEES_LIST_PATH = "/hr/employees"

# For now: on the FIRST DataTable page, skip employee IDs 123–223
FIRST_PAGE_SKIP_IDS = {str(i) for i in range(123, 224)}

###['7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22']

#####['23', '24', '25', '26', '27', '28', '29', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59', '60', '61', '62', '63', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74', '75', '76', '77', '78', '79', '80', '81', '82', '83', '84', '85', '86', '87', '88', '89', '90', '91', '92', '93', '94', '95', '96', '97', '98', '99', '100', '101', '102', '103', '104', '105', '106', '107', '108', '109', '110', '111', '112', '113', '114', '115', '116', '117', '118', '119', '120', '121', '122']

#####[INFO] Found 100 employee IDs on this page: ['123', '124', '125', '126', '127', '128', '129', '130', '131', '132', '133', '134', '135', '136', '137', '138', '139', '140', '141', '142', '143', '144', '145', '146', '147', '148', '149', '150', '151', '152', '153', '154', '155', '156', '157', '158', '159', '160', '161', '162', '163', '164', '165', '166', '167', '168', '169', '170', '171', '172', '173', '174', '175', '176', '177', '178', '179', '180', '181', '182', '183', '184', '185', '186', '187', '188', '189', '190', '191', '192', '193', '194', '195', '196', '197', '198', '199', '200', '201', '202', '203', '204', '205', '206', '207', '208', '209', '210', '211', '212', '213', '214', '215', '216', '217', '218', '219', '220', '221', '222']


def setup_driver() -> webdriver.Chrome:
    """Create and return a Chrome WebDriver instance."""
    import os
    print("[INFO] Launching Chrome via Selenium...")
    
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
        
        # If the path points to a directory, look for the actual executable
        if os.path.isdir(driver_path):
            possible_names = ['chromedriver', 'chromedriver.exe']
            for name in possible_names:
                exec_path = os.path.join(driver_path, name)
                if os.path.isfile(exec_path) and not exec_path.endswith('.chromedriver'):
                    driver_path = exec_path
                    break
        
        # Ensure the driver path is executable (Linux/Mac)
        if os.path.isfile(driver_path) and not driver_path.endswith('.exe') and not driver_path.endswith('.chromedriver'):
            try:
                os.chmod(driver_path, 0o755)
            except:
                pass
        
        # Verify the file is actually executable
        if os.path.isfile(driver_path) and driver_path.endswith('.chromedriver'):
            raise ValueError(f"Invalid chromedriver path: {driver_path}")
        
        service = Service(driver_path)
    except Exception as e:
        print(f"[WARNING] Error with ChromeDriverManager: {e}. Trying without explicit path...")
        # Fallback: let Selenium find chromedriver automatically
        service = Service()
    
    driver = webdriver.Chrome(service=service)
    driver.maximize_window()
    return driver


def selenium_login(driver: webdriver.Chrome, base_url: str) -> bool:
    """
    Perform login in the real browser using ADMIN_EMAIL / ADMIN_PASSWORD.

    This is adapted from the Selenium login flow in automation.py.
    """
    login_url = base_url.rstrip("/") + "/login"
    driver.get(login_url)
    print(f"[INFO] Opened login page: {login_url}")

    # If we're already logged in (session cookie, SSO, etc.) then skip
    current_url = driver.current_url
    if current_url is None:
        current_url = ""
    current_url = current_url.rstrip("/")
    if current_url and not current_url.endswith("/login"):
        print(f"[OK] Already logged in. Current URL: {current_url}")
        return True

    try:
        # Wait until at least a password field is present
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
        )

        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"[DEBUG] Found {len(inputs)} input fields on login page.")

        password_field = None
        email_field = None

        for inp in inputs:
            itype = (inp.get_attribute("type") or "").lower()
            name = (inp.get_attribute("name") or "").lower()
            if itype == "password" and password_field is None:
                password_field = inp
            if itype == "email" and email_field is None:
                email_field = inp

        # If no explicit email input, fall back to first visible text-like input
        if email_field is None:
            for inp in inputs:
                itype = (inp.get_attribute("type") or "").lower()
                name = (inp.get_attribute("name") or "").lower()
                if itype in ("text", "") and name not in ("_token",):
                    email_field = inp
                    break

        if not email_field or not password_field:
            print("[ERROR] Could not locate email or password fields on login page.")
            return False

        email_field.clear()
        email_field.send_keys(ADMIN_EMAIL)
        password_field.clear()
        password_field.send_keys(ADMIN_PASSWORD)
        print("[DEBUG] Filled email and password fields on login page.")

        # Try to find and click submit button
        submit_clicked = False
        submit_locators = [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (
                By.XPATH,
                "//button[contains(., 'Login') or contains(., 'Sign in') or contains(., 'Sign In')]",
            ),
        ]

        for by, value in submit_locators:
            try:
                btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((by, value))
                )
                btn.click()
                submit_clicked = True
                break
            except Exception:
                continue

        if not submit_clicked:
            # Fallback: submit the form via Enter key on password field
            try:
                password_field.submit()
                submit_clicked = True
            except Exception:
                pass

        if not submit_clicked:
            print("[ERROR] Could not find or click the login submit button.")
            return False

        # Wait up to 30 seconds for login redirect
        start_time = time.time()
        while time.time() - start_time < 30:
            current_url = driver.current_url
            if current_url is None:
                current_url = ""
            current_url = current_url.rstrip("/")
            if current_url and not current_url.endswith("/login"):
                print(f"[OK] Login successful. Current URL: {current_url}")
                return True
            time.sleep(1)

        print("[ERROR] Login did not redirect away from /login. Check credentials.")
        return False

    except Exception as e:
        print(f"[ERROR] Unexpected error during login: {e}")
        return False


def collect_employee_ids_from_page(driver: webdriver.Chrome) -> list[str]:
    """
    Collect all employee IDs from the current /hr/employees page.

    It looks for links whose href matches /hr/employees/<numeric_id>.
    """
    # Ensure DataTables content has loaded at least once
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#employees-table tbody tr"))
        )
    except Exception:
        print("[WARN] No table rows detected in #employees-table yet.")

    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/hr/employees/']")
    ids: set[str] = set()

    pattern = re.compile(r"/hr/employees/(\d+)(?:\D|$)")

    for a in links:
        href = a.get_attribute("href") or ""
        # Skip obvious non-detail links
        if any(bad in href for bad in ("/create", "/import", "/edit")):
            continue
        m = pattern.search(href)
        if m:
            ids.add(m.group(1))

    id_list = sorted(ids, key=lambda x: int(x))
    print(f"[INFO] Found {len(id_list)} employee IDs on this page: {id_list}")
    return id_list


def set_datatable_page_length_to_max(driver: webdriver.Chrome) -> None:
    """
    For the Yajra/DataTables employees table, set the "Show entries" dropdown
    to the maximum available value (e.g. 100) so we process more employees per page.
    """
    try:
        length_select = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "select[name='employees-table_length']")
            )
        )
        options = length_select.find_elements(By.TAG_NAME, "option")
        numeric_values: list[int] = []
        for opt in options:
            val = opt.get_attribute("value") or ""
            try:
                numeric_values.append(int(val))
            except ValueError:
                continue

        if not numeric_values:
            print("[WARN] No numeric page length options found for employees-table.")
            return

        max_len = max(numeric_values)
        Select(length_select).select_by_value(str(max_len))
        print(f"[INFO] Set DataTables page length to {max_len} entries per page.")

        # Wait for the table to redraw with the new page length
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "#employees-table tbody tr")
            )
        )
        time.sleep(1.0)
    except Exception as e:
        print(f"[WARN] Could not adjust DataTables page length: {e}")


def go_to_next_employees_page(driver: webdriver.Chrome) -> bool:
    """
    Try to navigate to the next page in the employees list.

    Returns True if a next page was found and clicked, False otherwise.
    """
    # Preferred: use DataTables JS API if available (more reliable than clicking "Next")
    try:
        has_more = driver.execute_script(
            """
            try {
                if (window.jQuery && $('#employees-table').length && $('#employees-table').DataTable) {
                    var t = $('#employees-table').DataTable();
                    var info = t.page.info();
                    if (info.page < info.pages - 1) {
                        t.page('next').draw('page');
                        return true;
                    } else {
                        return false; // already on last page
                    }
                }
            } catch (e) {
                return null;
            }
            return null;
            """
        )

        if has_more is True:
            print("[INFO] Moved to next DataTables page via JS API.")
            # Wait for rows to (re)load
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "#employees-table tbody tr")
                )
            )
            time.sleep(1.5)
            return True
        if has_more is False:
            print("[INFO] DataTables API reports last page reached.")
            return False
        # if has_more is None, fall through to DOM-based logic
    except Exception:
        # If JS API fails for any reason, fall back to DOM-based logic below
        pass
    # Fallback: handle the specific Yajra/DataTables pagination for employees-table via DOM
    try:
        li_next = driver.find_element(By.ID, "employees-table_next")
        li_class = (li_next.get_attribute("class") or "").lower()
        if "disabled" in li_class:
            print("[INFO] DataTables next button is disabled – last page reached.")
            return False

        next_link = li_next.find_element(By.CSS_SELECTOR, "a.page-link")
        print("[INFO] Clicking DataTables Next button for employees-table...")
        next_link.click()

        # Wait for DataTables processing indicator to complete or for rows to change
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#employees-table tbody tr"))
            )
        except Exception:
            pass

        time.sleep(1.5)
        return True
    except Exception:
        # Fall back to generic pagination handling below
        pass

    # Common patterns: rel="next" or link with text "Next"
    candidates = [
        (By.CSS_SELECTOR, "a[rel='next']"),
        (By.XPATH, "//a[contains(., 'Next')]"),
    ]

    for by, value in candidates:
        try:
            next_link = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by, value))
            )
            href = next_link.get_attribute("href") or ""
            print(f"[INFO] Navigating to next employees page: {href}")
            next_link.click()
            time.sleep(2)
            return True
        except Exception:
            continue

    print("[INFO] No further employees pages detected.")
    return False


def click_reset_password(driver: webdriver.Chrome, base_url: str, employee_id: str) -> None:
    """
    Open the employee detail page and click the 'Reset Password' link/button.
    """
    detail_url = base_url.rstrip("/") + f"{EMPLOYEES_LIST_PATH}/{employee_id}"
    print(f"[INFO] Opening employee #{employee_id} page: {detail_url}")
    driver.get(detail_url)

    try:
        # Wait for page to load some content
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Prefer the exact reset-password-sms form that you shared
        try:
            reset_form = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "form[action$='/reset-password-sms']")
                )
            )
            reset_button = reset_form.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", reset_button
            )
            time.sleep(0.3)
            print(
                f"[OK] Found reset-password-sms form for employee #{employee_id}, clicking submit button..."
            )
            reset_button.click()
        except Exception:
            # Fallback: find reset password action by text (case-insensitive)
            xpath_reset = (
                "//a[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') "
                "contains(., 'reset password')]"
                " | "
                "//button[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') "
                "contains(., 'reset password')]"
            )

            reset_el = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, xpath_reset))
            )
            print(
                f"[OK] Found generic reset password control for employee #{employee_id}, clicking..."
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", reset_el
            )
            time.sleep(0.3)
            reset_el.click()

        # Handle possible JS alert confirmation
        try:
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            print("[INFO] Confirming browser alert for reset password...")
            alert.accept()
        except Exception:
            # No alert – ignore
            pass

        time.sleep(1.5)
        print(f"[OK] Reset password triggered for employee #{employee_id}")

    except Exception as e:
        print(f"[WARN] Could not reset password for employee #{employee_id}: {e}")


def reset_passwords_for_all_employees() -> None:
    """
    Main flow:
      1) Login to the HR system.
      2) Open employees list.
      3) For each employee on each page, open their detail page and trigger 'Reset Password'.
    """
    driver = setup_driver()
    base_url = BASE_URL

    try:
        if not selenium_login(driver, base_url):
            print("[FATAL] Login failed. Aborting.")
            return

        employees_url = base_url.rstrip("/") + EMPLOYEES_LIST_PATH
        print(f"[INFO] Opening employees list: {employees_url}")
        driver.get(employees_url)

        # Increase page length so we see as many employees as possible per page
        set_datatable_page_length_to_max(driver)

        all_processed_ids: set[str] = set()
        page_index = 0  # 0-based: 0 = first page

        while True:
            # Wait for table/list to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            ids = collect_employee_ids_from_page(driver)

            # For now: skip the entire first and second DataTable pages
            if page_index in (0, 1):
                print(
                    f"[INFO] Skipping entire DataTables page {page_index + 1} as requested. "
                    f"Employee IDs on this page: {ids}"
                )
                ids_to_use = []
            else:
                ids_to_use = ids

            new_ids = [i for i in ids_to_use if i not in all_processed_ids]

            if not new_ids:
                print("[INFO] No new employee IDs found on this page.")
            else:
                for emp_id in new_ids:
                    click_reset_password(driver, base_url, emp_id)
                    all_processed_ids.add(emp_id)

            # Try to move to next page; stop if none
            if not go_to_next_employees_page(driver):
                break

            page_index += 1

        print(f"[DONE] Attempted reset password for {len(all_processed_ids)} employees.")

    finally:
        # Keep the browser open for inspection – comment the next line back in
        # if you want the script to close the browser automatically.
        # driver.quit()
        print("[INFO] Script finished. Browser window left open for manual review.")


if __name__ == "__main__":
    reset_passwords_for_all_employees()


