import csv
import threading
import time
import webbrowser
import os
import sys
from dotenv import load_dotenv

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
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

# Icon utility
try:
    from icon_utils import set_window_icon
except ImportError:
    def set_window_icon(window):
        pass  # Silently fail if icon can't be loaded

# Load environment variables
load_dotenv()

# === Backend configuration (credentials & endpoints) ===
# Base app URL
BASE_URL_DEFAULT = "http://localhost:8000/"
# Exact endpoints you specified
LOGIN_PATHS = ["/login"]
EMPLOYEE_CREATE_PATH = "/hr/employees/create"
EMPLOYEE_STORE_PATH = "/hr/employees"

# Load credentials from environment variables
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "your-email@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "your-password")


def log_to_widget(widget: ScrolledText, message: str) -> None:
    """Append a line to the log widget in a thread‑safe way."""
    def _append():
        widget.configure(state="normal")
        widget.insert(tk.END, message + "\n")
        widget.see(tk.END)
        widget.configure(state="disabled")

    widget.after(0, _append)


def extract_csrf_token(html: str) -> str | None:
    """Try to extract Laravel-style CSRF token from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    meta = soup.find("meta", attrs={"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]

    inp = soup.find("input", attrs={"name": "_token"})
    if inp and inp.get("value"):
        return inp["value"]

    return None


def login(session: requests.Session, base_url: str, log_widget: ScrolledText, email: str = None, password: str = None) -> bool:
    """Login using provided admin credentials and robust error reporting.

    Tries multiple candidate login URLs until one works.
    """
    # Use provided credentials or fall back to defaults
    email = email or ADMIN_EMAIL
    password = password or ADMIN_PASSWORD
    
    # Set browser-like headers
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    for path in LOGIN_PATHS:
        login_url = base_url.rstrip("/") + path
        log_to_widget(log_widget, f"[INFO] Trying login URL: {login_url} as {email}")

        try:
            r = session.get(login_url, timeout=15)
        except Exception as e:
            log_to_widget(log_widget, f"[ERROR] Failed to load login page {login_url}: {e}")
            continue

        if r.status_code >= 400:
            log_to_widget(log_widget, f"[ERROR] Login page HTTP {r.status_code} for {login_url}")
            continue

        token = extract_csrf_token(r.text)
        if not token:
            log_to_widget(
                log_widget,
                f"[WARN] Could not find CSRF token on {login_url}. "
                "Trying next login path if available.",
            )
            continue

        payload = {
            "_token": token,
            "email": email,
            "password": password,
        }

        # Some Laravel apps also send X-CSRF-TOKEN header; add it for good measure.
        session.headers["X-CSRF-TOKEN"] = token
        session.headers["Referer"] = login_url
        session.headers["Origin"] = base_url.rstrip("/")

        try:
            r2 = session.post(login_url, data=payload, timeout=15, allow_redirects=True)
        except Exception as e:
            log_to_widget(log_widget, f"[ERROR] Login request failed for {login_url}: {e}")
            continue

        if r2.status_code >= 400:
            log_to_widget(log_widget, f"[ERROR] Login HTTP {r2.status_code} for {login_url}")
            continue

        final_url = r2.url
        log_to_widget(log_widget, f"[DEBUG] After login redirect URL from {login_url}: {final_url}")

        # If we are still on the same login URL, likely failed login.
        if final_url.rstrip("/").endswith(path.strip("/")):
            soup = BeautifulSoup(r2.text, "html.parser")
            error_msgs = []
            for div in soup.find_all(class_="alert-danger"):
                txt = div.get_text(strip=True)
                if txt:
                    error_msgs.append(txt)
            if error_msgs:
                log_to_widget(
                    log_widget,
                    f"[ERROR] Login failed on {path}: " + " | ".join(error_msgs),
                )
            else:
                log_to_widget(
                    log_widget,
                    f"[ERROR] Login seems to have failed on {path} "
                    "(still on login page and no explicit error message).",
                )
            # Try next candidate path
            continue

        log_to_widget(log_widget, f"[OK] Logged in successfully via {path}.")
        return True

    log_to_widget(
        log_widget,
        "[FATAL] All login attempts failed. Please verify the base URL and admin credentials.",
    )
    return False


def map_office_location(text: str) -> str | None:
    """
    Map CSV office_location text to office_id from the form.
    Office mappings based on dropdown options:
      1: HEAD OFFICE (HO)
      2: CHITTAGONG OFFICE (CTG)
      3: Branch Office - Sylhet (SYL) / SYLHET OFFICE (SYLTO)
      4: PALTAN OFFICE (PLTO)
      5: CUMILLA OFFICE (CMAO)
      6: RAJSHAHI OFFICE (RAJO)
      7: NAOGAON (NAGO)
      8: BARISHAL OFFICE (BRLO)
      9: KHULNA OFFICE (KHLO)
      10: JESSORE OFFICE (JSRO)
      11: MYMENSINGH OFFICE (MYMIO)
      12: JAMALPUR OFFICE (JAMO)
      13: SYLHET OFFICE (SYLTO)
      14: HOBIGONJ (HBGO)
      15: JOYPURHAT (JOYO)
      16: KURIGRAM (KURIO)
    """
    if not text:
        return None

    t = text.strip().lower()
    
    # Head Office
    if "head" in t or "dhaka" in t or t == "ho":
        return "1"
    
    # Chittagong
    if "chittagong" in t or "ctg" in t or "ctgo" in t:
        return "2"
    
    # Sylhet - check both old and new format
    if "sylhet" in t or "syl" in t or "sylto" in t:
        return "3"  # Note: There's also value 13 for SYLHET OFFICE, but 3 is Branch Office - Sylhet
    
    # Paltan
    if "paltan" in t or "plto" in t:
        return "4"
    
    # Cumilla
    if "cumilla" in t or "cmao" in t:
        return "5"
    
    # Rajshahi
    if "rajshahi" in t or "rajo" in t:
        return "6"
    
    # Naogaon
    if "naogaon" in t or "nago" in t:
        return "7"
    
    # Barishal
    if "barishal" in t or "brlo" in t:
        return "8"
    
    # Khulna
    if "khulna" in t or "khlo" in t:
        return "9"
    
    # Jessore
    if "jessore" in t or "jsro" in t:
        return "10"
    
    # Mymensingh
    if "mymensingh" in t or "mymio" in t:
        return "11"
    
    # Jamalpur
    if "jamalpur" in t or "jamo" in t:
        return "12"
    
    # Hobigonj
    if "hobigonj" in t or "habigonj" in t or "hbgo" in t:
        return "14"
    
    # Joypurhat
    if "joypurhat" in t or "joyo" in t:
        return "15"
    
    # Kurigram
    if "kurigram" in t or "kurio" in t:
        return "16"

    return None


def split_name(full_name: str) -> tuple[str, str]:
    """Split full name into first and last name (very simple heuristic)."""
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def normalize_phone(phone: str) -> str:
    """Normalize phone number to ensure it starts with '0' if not already."""
    phone = (phone or "").strip()
    if not phone:
        return ""
    # If phone number doesn't start with '0', add it
    if not phone.startswith("0"):
        return "0" + phone
    return phone


def normalize_department_name(dept: str) -> str:
    """
    Normalize department name for better matching.
    Returns the original value as most CSV values match dropdown options exactly.
    Only maps when there's a clear difference.
    """
    dept = (dept or "").strip()
    dept_upper = dept.upper()
    
    # Mappings for departments that don't match exactly
    # Most CSV values like "IT DEPARTMENT", "HR & ADMIN", "OPERATION" match exactly
    mappings = {
        # Keep exact matches as-is since they exist in dropdown
        "IT DEPARTMENT": "IT DEPARTMENT",  # Exact match exists
        "HR & ADMIN": "HR & ADMIN",  # Exact match exists (as HR &amp; ADMIN)
        "OPERATION": "OPERATION",  # Exact match exists
        "CUSTOMER SUPPORT": "CUSTOMER SUPPORT",  # Exact match exists
        "DIGITAL MARKETING": "DIGITAL MARKETING",  # Exact match exists
        "PUBLIC RELATION": "PUBLIC RELATION",  # Exact match exists
        "DEVELOPMENT": "DEVELOPMENT",  # Exact match exists
        "TRAINING": "TRAINING",  # Exact match exists
        "FINANCE": "Finance",  # Try capitalized version
        "MARKETING": "Marketing",  # Try capitalized version
    }
    
    # Return mapped value if exists, otherwise return original (most will match)
    return mappings.get(dept_upper, dept)


def normalize_designation_name(desig: str) -> str:
    """Normalize designation name for better matching."""
    desig = (desig or "").strip()
    desig_upper = desig.upper()
    
    # Common mappings - try to match CSV values to dropdown options
    mappings = {
        "SR. SOFTWARE ENGINEER": "Senior Software Engineer",
        "JR. SOFTWARE ENGINEER": "Junior Software Engineer",
        "JR. EXECUTIVE": "Junior Executive",
        "SR. EXECUTIVE": "Senior Executive",
        "MD & CEO": "MD & CEO",  # Keep original as it exists in dropdown
        "MD AND CEO": "MD & CEO",
        "ADVISOR": "Advisor",
        "DIRECTOR": "Director",
        "MANAGER": "Manager",
        "ASSISTANT MANAGER": "Assistant Manager",
        "DEPUTY MANAGER": "Deputy Manager",
        "GENERAL MANAGER": "General Manager",
        "DEPUTY GENERAL MANAGER": "Deputy General Manager",
        "ASSISTANT GENERAL MANAGER": "Assistant General Manager",
        "SENIOR GENERAL MANAGER": "Senior General Manager",
        "SR. GENERAL MANAGER": "SR. GENERAL MANAGER",  # Exact match exists
        "EXECUTIVE": "Executive",
        "SENIOR EXECUTIVE": "Senior Executive",
        "CUSTOMER SUPPORT EXECUTIVE": "Customer Support Executive",
        "MARKETING EXECUTIVE": "Marketing Executive",
        "SENIOR MARKETING EXECUTIVE": "Senior Marketing Executive",
        "OFFICE ASSISTANT": "Office Assistant",
        "DRIVER": "Driver",
        "PERSONAL ASSISTANT": "Personal Assistant",
        "PUBLIC RELATION OFFICER": "Public Relation Officer",
        "ENTREPRENEUR DEVELOPMENT OFFICER": "Entrepreneur Development Officer",
        "DIVISIONAL TRAINER": "Divisional Trainer",
        "EXECUTIVE TRAINER": "Executive Trainer",
    }
    
    # Return mapped value or original
    return mappings.get(desig_upper, desig)


def select_searchable_dropdown(
    driver, input_selector: str, value: str, log_widget: ScrolledText, field_type: str = "unknown"
) -> bool:
    """
    Select a value from a searchable dropdown with improved matching.
    
    Args:
        driver: Selenium WebDriver instance
        input_selector: CSS selector for the searchable input field
        value: The text value to search for and select
        log_widget: Log widget for messages
        field_type: Type of field ("department" or "designation") for normalization
    
    Returns:
        True if selection was successful, False otherwise
    """
    if not value or not value.strip():
        return False
    
    try:
        # Normalize the value based on field type
        search_value = value.strip()
        if field_type == "department":
            search_value = normalize_department_name(value)
        elif field_type == "designation":
            search_value = normalize_designation_name(value)
        
        # Find the searchable input
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
        )
        
        # Scroll to input to ensure it's visible
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_input)
        time.sleep(0.3)
        
        # Clear any existing value first
        search_input.clear()
        time.sleep(0.2)
        
        # Click to open dropdown
        search_input.click()
        time.sleep(0.5)
        
        # Find the dropdown container (parent of the input)
        dropdown_container = search_input.find_element(By.XPATH, "./ancestor::div[contains(@class, 'searchable-select-container')]")
        dropdown = dropdown_container.find_element(By.CSS_SELECTOR, ".searchable-dropdown")
        
        # Ensure dropdown is shown (add 'show' class if needed)
        driver.execute_script("arguments[0].classList.add('show');", dropdown)
        time.sleep(0.3)
        
        # Get all available options BEFORE filtering (to see all options)
        all_options = dropdown.find_elements(By.CSS_SELECTOR, ".searchable-option")
        
        # Try multiple search strategies: original, normalized, and key words
        original_value = value.strip()
        search_terms = [original_value, search_value]
        
        # Add key word variations for better matching
        if field_type == "designation":
            # Extract key words (remove common prefixes/suffixes)
            words = original_value.upper().split()
            if len(words) > 1:
                # Try without prefixes like "LN.", "MD.", etc.
                key_words = [w for w in words if w not in ["LN.", "MD.", "DR.", "BRIG", "GEN"]]
                if key_words:
                    search_terms.append(" ".join(key_words))
        
        selected_option = None
        best_match_score = 0
        best_match_text = ""
        
        # First, get all options without filtering to see everything
        all_option_texts = {}
        for opt in all_options:
            opt_text = (opt.get_attribute("data-text") or opt.text or "").strip()
            if opt_text:
                # Decode HTML entities
                opt_text_clean = opt_text.replace("&amp;", "&").replace("&nbsp;", " ")
                all_option_texts[opt_text_clean.lower()] = (opt, opt_text)
        
        # Try direct matching against all options first (no search needed)
        original_lower = original_value.lower()
        search_value_lower = search_value.lower()
        
        for opt_text_lower, (opt, opt_text) in all_option_texts.items():
            match_score = 0
            
            # Exact match (case-insensitive)
            if opt_text_lower == original_lower or opt_text_lower == search_value_lower:
                match_score = 100
            # Exact match with HTML entity handling
            elif opt_text_lower.replace("&", "&amp;") == original_lower.replace("&", "&amp;"):
                match_score = 95
            # Starts with match
            elif opt_text_lower.startswith(original_lower) or opt_text_lower.startswith(search_value_lower):
                match_score = 85
            elif original_lower.startswith(opt_text_lower) or search_value_lower.startswith(opt_text_lower):
                match_score = 80
            # Contains match
            elif original_lower in opt_text_lower or search_value_lower in opt_text_lower:
                match_score = 70
            elif opt_text_lower in original_lower or opt_text_lower in search_value_lower:
                match_score = 65
            # Word-based matching
            else:
                original_words = set(original_lower.split())
                opt_words = set(opt_text_lower.split())
                common_words = original_words.intersection(opt_words)
                if len(common_words) >= 2:
                    match_score = 50 + (len(common_words) * 5)
            
            if match_score > best_match_score:
                best_match_score = match_score
                selected_option = opt
                best_match_text = opt_text
        
        # If we didn't find a good match, try searching with the dropdown filter
        if not selected_option or best_match_score < 50:
            for search_term in search_terms[:2]:  # Try original and normalized only
                if not search_term:
                    continue
                    
                # Clear and type the search value
                search_input.clear()
                search_input.send_keys(search_term)
                time.sleep(1.2)  # Wait for dropdown to filter
                
                # Wait for dropdown to be visible
                WebDriverWait(driver, 5).until(
                    EC.visibility_of(dropdown)
                )
                
                # Get filtered options
                visible_options = dropdown.find_elements(By.CSS_SELECTOR, ".searchable-option:not(.hidden)")
                
                # If no visible options, try all options
                if not visible_options:
                    visible_options = all_options
                
                search_term_lower = search_term.lower()
                
                # Try to find best match from filtered results
                for option in visible_options:
                    option_text = (option.get_attribute("data-text") or option.text or "").strip()
                    if not option_text:
                        continue
                    
                    # Decode HTML entities
                    option_text_clean = option_text.replace("&amp;", "&").replace("&nbsp;", " ")
                    option_text_lower = option_text_clean.lower()
                    
                    # Calculate match score
                    match_score = 0
                    if option_text_lower == search_term_lower:
                        match_score = 100
                    elif option_text_lower.startswith(search_term_lower):
                        match_score = 80
                    elif search_term_lower in option_text_lower:
                        match_score = 60
                    elif any(word in option_text_lower for word in search_term_lower.split() if len(word) > 3):
                        match_score = 40
                    
                    if match_score > best_match_score:
                        best_match_score = match_score
                        selected_option = option
                        best_match_text = option_text_clean
                
                # If we found a good match, break
                if selected_option and best_match_score >= 60:
                    break
        
        if selected_option and best_match_score >= 40:
            # Clear the search input first to show all options
            search_input.clear()
            time.sleep(0.3)
            
            # Ensure dropdown is visible
            driver.execute_script("arguments[0].classList.add('show');", dropdown)
            time.sleep(0.3)
            
            # Scroll into view and click
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", selected_option)
            time.sleep(0.3)
            selected_option.click()
            time.sleep(0.5)
            
            # Verify selection
            log_to_widget(
                log_widget,
                f"[INFO] Selected '{best_match_text}' (matched from '{value}' with score {best_match_score})",
            )
            return True
        else:
            # Log all available options for debugging
            available_options_list = [
                (opt.get_attribute("data-text") or opt.text or "").strip() 
                for opt in all_options[:15]
            ]
            log_to_widget(
                log_widget,
                f"[WARN] Could not find good match for '{value}' (searched as '{search_value}'). "
                f"Best score: {best_match_score}. Sample options: {', '.join([t for t in available_options_list if t][:10])}",
            )
            return False
            
    except Exception as e:
        log_to_widget(
            log_widget,
            f"[WARN] Error selecting from searchable dropdown '{value}': {e}",
        )
        return False


def import_with_browser(
    csv_rows: list[dict],
    base_url: str,
    log_widget: ScrolledText,
    email: str = None,
    password: str = None,
) -> tuple[int, int]:
    """Use a real Chrome browser (Selenium) to perform the import.

    Flow:
      1) Open login page in Chrome.
      2) Automatically log in using provided credentials or ADMIN_EMAIL / ADMIN_PASSWORD.
      3) For each CSV row, open the 'Add Employee' page and submit the form.
    """
    # Use provided credentials or fall back to defaults
    email = email or ADMIN_EMAIL
    password = password or ADMIN_PASSWORD
    driver = None
    success_count = 0
    total_rows = len(csv_rows)

    try:
        log_to_widget(log_widget, "[INFO] Launching Chrome via Selenium...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
        driver.maximize_window()

        login_url = base_url.rstrip("/") + "/login"
        create_url = base_url.rstrip("/") + EMPLOYEE_CREATE_PATH

        # --- Automatic login in the real browser ---
        driver.get(login_url)
        log_to_widget(
            log_widget,
            f"[INFO] Chrome opened at {login_url}. Attempting automatic login as {email}...",
        )

        current_url = driver.current_url
        if current_url is None:
            current_url = ""
        current_url = current_url.rstrip("/")
        if current_url and not current_url.endswith("/login"):
            # Already logged in (session cookie, SSO, etc.)
            log_to_widget(log_widget, f"[OK] Already logged in. Current URL: {current_url}")
        else:
            try:
                # Wait until at least a password field is present
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                )

                # Grab all input fields and heuristically pick username/email + password
                inputs = driver.find_elements(By.TAG_NAME, "input")
                log_to_widget(log_widget, f"[DEBUG] Found {len(inputs)} input fields on login page.")

                password_field = None
                email_field = None

                for inp in inputs:
                    itype = (inp.get_attribute("type") or "").lower()
                    name = (inp.get_attribute("name") or "").lower()
                    if itype == "password" and password_field is None:
                        password_field = inp
                    # Prefer explicit email field
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
                    log_to_widget(
                        log_widget,
                        "[ERROR] Could not locate email or password fields on login page. "
                        "Please check the login form structure.",
                    )
                    return success_count, total_rows

                email_field.clear()
                email_field.send_keys(email)
                password_field.clear()
                password_field.send_keys(password)
                log_to_widget(log_widget, "[DEBUG] Filled email and password fields on login page.")

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
                    log_to_widget(
                        log_widget,
                        "[ERROR] Could not find or click the login submit button.",
                    )
                    return success_count, total_rows

                # Wait up to 30 seconds for login redirect
                start_time = time.time()
                while time.time() - start_time < 30:
                    current_url = driver.current_url
                    if current_url is None:
                        current_url = ""
                    current_url = current_url.rstrip("/")
                    if current_url and not current_url.endswith("/login"):
                        log_to_widget(
                            log_widget,
                            f"[OK] Automatic login successful. Current URL: {current_url}",
                        )
                        break
                    time.sleep(1)
                else:
                    log_to_widget(
                        log_widget,
                        "[ERROR] Automatic login did not redirect away from /login. "
                        "Please verify credentials and login form fields.",
                    )
                    return success_count, total_rows
            except Exception as e:
                log_to_widget(
                    log_widget,
                    f"[ERROR] Unexpected error during automatic login: {e}",
                )
                return success_count, total_rows

        for idx, row in enumerate(csv_rows, start=1):
            # Handle different possible column names (case-insensitive)
            full_name = (
                row.get("EMPLOYEE NAME") or 
                row.get("employee name") or 
                row.get("full_name") or 
                row.get("Full Name") or 
                ""
            ).strip()
            
            phone = normalize_phone(
                row.get("CLEAN NUMBER") or 
                row.get("clean number") or 
                row.get("phone") or 
                row.get("Phone") or 
                ""
            )
            
            office_location = (
                row.get("OFFICE LOCATION") or 
                row.get("office location") or 
                row.get("office_location") or 
                row.get("Office Location") or 
                ""
            ).strip()
            
            designation = (
                row.get("DESIGNATION") or 
                row.get("designation") or 
                row.get("Designation") or 
                ""
            ).strip()
            
            department = (
                row.get("DEPARTMENT") or 
                row.get("department") or 
                row.get("Department") or 
                ""
            ).strip()

            if not full_name or not phone:
                log_to_widget(
                    log_widget,
                    f"[Row {idx}] [SKIP] Missing employee name or phone. name='{full_name}', phone='{phone}'",
                )
                continue

            office_id = map_office_location(office_location)

            try:
                driver.get(create_url)
                # Wait until first_name field is present
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.NAME, "first_name"))
                )

                first_name, last_name = split_name(full_name)

                # Fill basic fields
                driver.find_element(By.NAME, "first_name").clear()
                driver.find_element(By.NAME, "first_name").send_keys(first_name)

                last_el = driver.find_element(By.NAME, "last_name")
                last_el.clear()
                if last_name:
                    last_el.send_keys(last_name)

                phone_el = driver.find_element(By.NAME, "phone")
                phone_el.clear()
                phone_el.send_keys(phone)

                # Status select (name="status")
                try:
                    status_select = Select(driver.find_element(By.NAME, "status"))
                    status_select.select_by_value("active")
                except Exception:
                    # If anything fails here, just continue; default may already be Active
                    pass

                # Department (searchable dropdown)
                if department:
                    try:
                        # Wait for the department input to be present
                        dept_input = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-target="department-dropdown"]'))
                        )
                        success = select_searchable_dropdown(
                            driver,
                            'input[data-target="department-dropdown"]',
                            department,
                            log_widget,
                            field_type="department",
                        )
                        if success:
                            log_to_widget(
                                log_widget,
                                f"[Row {idx}] [OK] Department set successfully from '{department}'",
                            )
                        else:
                            log_to_widget(
                                log_widget,
                                f"[Row {idx}] [WARN] Could not set department '{department}' - check available options",
                            )
                    except Exception as e:
                        log_to_widget(
                            log_widget,
                            f"[Row {idx}] [ERROR] Exception setting department '{department}': {e}",
                        )

                # Designation (searchable dropdown)
                if designation:
                    try:
                        # Wait for the designation input to be present
                        desig_input = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-target="designation-dropdown"]'))
                        )
                        success = select_searchable_dropdown(
                            driver,
                            'input[data-target="designation-dropdown"]',
                            designation,
                            log_widget,
                            field_type="designation",
                        )
                        if success:
                            log_to_widget(
                                log_widget,
                                f"[Row {idx}] [OK] Designation set successfully from '{designation}'",
                            )
                        else:
                            log_to_widget(
                                log_widget,
                                f"[Row {idx}] [WARN] Could not set designation '{designation}' - check available options",
                            )
                    except Exception as e:
                        log_to_widget(
                            log_widget,
                            f"[Row {idx}] [ERROR] Exception setting designation '{designation}': {e}",
                        )

                # Office select (name="office_id")
                if office_id:
                    try:
                        office_select = Select(driver.find_element(By.NAME, "office_id"))
                        office_select.select_by_value(office_id)
                    except Exception:
                        log_to_widget(
                            log_widget,
                            f"[Row {idx}] [WARN] Could not set office_id '{office_id}' for office_location '{office_location}'.",
                        )

                # Submit the form directly via JavaScript to avoid wizard UI issues
                try:
                    driver.execute_script("document.getElementById('employeeForm').submit();")
                except Exception:
                    try:
                        form_el = driver.find_element(By.ID, "employeeForm")
                        form_el.submit()
                    except Exception as e:
                        log_to_widget(
                            log_widget,
                            f"[Row {idx}] [ERROR] Could not submit form: {e}",
                        )
                        continue

                # Wait briefly for potential redirect or success
                time.sleep(2)
                final_url = driver.current_url
                if "/hr/employees" in final_url:
                    log_to_widget(
                        log_widget,
                        f"[Row {idx}] [OK] Employee created via browser: {full_name} ({phone})",
                    )
                    success_count += 1
                else:
                    log_to_widget(
                        log_widget,
                        f"[Row {idx}] [WARN] After submit, still on {final_url}. "
                        "Please check this row manually in the browser.",
                    )
            except Exception as e:
                log_to_widget(
                    log_widget,
                    f"[Row {idx}] [ERROR] Unexpected error while processing row in browser: {e}",
                )

        # Finally, open the employees list
        employees_url = base_url.rstrip("/") + "/hr/employees"
        driver.get(employees_url)
        log_to_widget(log_widget, f"[INFO] Opened employees list in Chrome: {employees_url}")

        return success_count, total_rows
    finally:
        # Keep the browser open for inspection; do NOT quit here.
        pass


class EmployeeImporterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("HR Employee CSV Importer")
        self.root.geometry("900x750")
        self.root.minsize(800, 700)
        self.root.configure(bg="#f0f2f5")
        
        # Set window icon
        set_window_icon(self.root)

        # Main container
        main_container = tk.Frame(root, bg="#f0f2f5")
        main_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Header
        header = tk.Frame(main_container, bg="#1f2937", bd=0, relief=tk.FLAT)
        header.pack(fill=tk.X, pady=(0, 10))

        title = tk.Label(
            header,
            text="HR Employee CSV Importer",
            bg="#1f2937",
            fg="white",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
            padx=10,
            pady=8,
        )
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)

        subtitle = tk.Label(
            header,
            text="Uploads employees from CSV directly to your HR system",
            bg="#1f2937",
            fg="#e5e7eb",
            font=("Segoe UI", 9),
            anchor="w",
            padx=10,
        )
        subtitle.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Top card – configuration
        card = tk.Frame(main_container, bg="white", bd=1, relief=tk.SOLID)
        card.pack(fill=tk.X, pady=(0, 10))

        top_frame = tk.Frame(card, bg="white")
        top_frame.pack(fill=tk.X, padx=15, pady=15)

        # Base URL
        tk.Label(
            top_frame,
            text="Base URL",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.base_url_var = tk.StringVar(value=BASE_URL_DEFAULT)
        tk.Entry(
            top_frame,
            textvariable=self.base_url_var,
            width=45,
            font=("Segoe UI", 10),
            relief=tk.GROOVE,
            bd=1,
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(2, 5))

        # Credentials section (editable)
        cred_frame = tk.Frame(top_frame, bg="white")
        cred_frame.grid(row=0, column=1, rowspan=2, sticky="w", padx=10)
        
        tk.Label(
            cred_frame,
            text="Login Credentials:",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        
        # Email field
        email_inner = tk.Frame(cred_frame, bg="white")
        email_inner.pack(fill='x', pady=(0, 5))
        
        tk.Label(
            email_inner,
            text="Email:",
            bg="white",
            fg="#374151",
            font=("Segoe UI", 9),
            width=8,
            anchor='w'
        ).pack(side='left')
        
        self.email_var = tk.StringVar(value=ADMIN_EMAIL)
        tk.Entry(
            email_inner,
            textvariable=self.email_var,
            font=("Segoe UI", 9),
            width=25,
            relief=tk.GROOVE,
            bd=1
        ).pack(side='left', padx=(5, 0))
        
        # Password field
        password_inner = tk.Frame(cred_frame, bg="white")
        password_inner.pack(fill='x')
        
        tk.Label(
            password_inner,
            text="Password:",
            bg="white",
            fg="#374151",
            font=("Segoe UI", 9),
            width=8,
            anchor='w'
        ).pack(side='left')
        
        self.password_var = tk.StringVar(value=ADMIN_PASSWORD)
        tk.Entry(
            password_inner,
            textvariable=self.password_var,
            font=("Segoe UI", 9),
            width=25,
            show="*",
            relief=tk.GROOVE,
            bd=1
        ).pack(side='left', padx=(5, 0))

        # CSV file selection
        csv_label = tk.Label(
            top_frame,
            text="CSV File",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        )
        csv_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

        csv_inner = tk.Frame(top_frame, bg="white")
        csv_inner.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        self.csv_path_var = tk.StringVar(value="")
        tk.Entry(
            csv_inner,
            textvariable=self.csv_path_var,
            width=60,
            font=("Segoe UI", 10),
            relief=tk.GROOVE,
            bd=1,
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            csv_inner,
            text="Browse…",
            command=self.browse_csv,
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            bd=0,
            padx=12,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)

        # Controls row
        controls = tk.Frame(top_frame, bg="white")
        controls.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.start_button = tk.Button(
            controls,
            text="Start Import",
            command=self.start_import,
            bg="#16a34a",
            fg="white",
            activebackground="#15803d",
            activeforeground="white",
            bd=0,
            padx=16,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        )
        self.start_button.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Idle")
        status_label = tk.Label(
            controls,
            textvariable=self.status_var,
            bg="white",
            fg="#2563eb",
            font=("Segoe UI", 9, "italic"),
            padx=10,
        )
        status_label.pack(side=tk.LEFT)

        # Log area card
        log_card = tk.Frame(main_container, bg="white", bd=1, relief=tk.SOLID)
        log_card.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_card, bg="white")
        log_header.pack(fill=tk.X, padx=15, pady=(10, 0))

        tk.Label(
            log_header,
            text="Logs",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)

        tk.Label(
            log_header,
            text="Real-time progress and errors will appear here",
            bg="white",
            fg="#6b7280",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=10)

        log_frame = tk.Frame(log_card, bg="white")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

        self.log_widget = ScrolledText(
            log_frame,
            state="disabled",
            height=20,
            font=("Consolas", 9),
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="white",
        )
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    def browse_csv(self) -> None:
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = filedialog.askopenfilename(
            title="Select CSV File",
            initialdir=current_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.csv_path_var.set(path)

    def start_import(self) -> None:
        csv_path = self.csv_path_var.get().strip()
        if not csv_path:
            messagebox.showwarning("CSV Required", "Please select a CSV file first.")
            return

        base_url = self.base_url_var.get().strip()
        if not base_url:
            messagebox.showwarning(
                "Base URL Required",
                "Please provide the base URL (e.g. http://192.168.68.129:8000).",
            )
            return

        self.start_button.configure(state="disabled")
        self.status_var.set("Running...")
        log_to_widget(self.log_widget, "=== Starting import ===")

        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        
        if not email or not password:
            messagebox.showwarning(
                "Credentials Required",
                "Please provide email and password."
            )
            return
        
        thread = threading.Thread(
            target=self._run_import_thread,
            args=(csv_path, base_url, email, password),
            daemon=True,
        )
        thread.start()

    def _run_import_thread(self, csv_path: str, base_url: str, email: str, password: str) -> None:
        success_count = 0
        total_rows = 0
        try:
            # Read CSV
            try:
                with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            except Exception as e:
                log_to_widget(self.log_widget, f"[ERROR] Failed to read CSV: {e}")
                self._finish_import("Finished with CSV read error.", success_count, total_rows)
                return

            if not rows:
                log_to_widget(self.log_widget, "[WARN] CSV file has no data rows.")
                self._finish_import("Finished: no data rows found in CSV.", success_count, total_rows)
                return

            total_rows = len(rows)
            log_to_widget(self.log_widget, f"Found {total_rows} rows in CSV. Starting browser-based import...")

            success_count, total_rows = import_with_browser(
                csv_rows=rows,
                base_url=base_url,
                log_widget=self.log_widget,
                email=email,
                password=password,
            )

            self._finish_import(
                f"Finished. Successfully created {success_count} of {total_rows} rows.",
                success_count,
                total_rows,
                base_url,
                None,
            )
        finally:
            pass

    def _finish_import(
        self,
        status_message: str,
        success_count: int,
        total_rows: int,
        base_url: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        def _update_ui():
            self.start_button.configure(state="normal")
            self.status_var.set("Done")
            log_to_widget(self.log_widget, status_message)

            # Open in Chrome (or default browser) when finished
            if base_url and success_count > 0:
                employees_url = base_url.rstrip("/") + "/hr/employees"
                log_to_widget(self.log_widget, f"Opening employees page: {employees_url}")
                webbrowser.open(employees_url)

        self.root.after(0, _update_ui)


def main() -> None:
    root = tk.Tk()
    app = EmployeeImporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


