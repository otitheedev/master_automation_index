import csv
import threading
import time
import webbrowser
import os
import sys
import json
import asyncio
from urllib.parse import urljoin, urlparse
from collections import deque

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

# Optional imports
try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    print("[WARNING] pytest not available - some testing features may be limited")

# GUI imports - only import if not in headless mode
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

import requests
from bs4 import BeautifulSoup

# Faker for realistic fake data
try:
    from faker import Faker
    FAKER_AVAILABLE = True
    faker = Faker()
except ImportError:
    FAKER_AVAILABLE = False
    faker = None
    print("[WARNING] Faker not available - using basic random data instead")

# Selenium imports - handle gracefully if not available
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.support.ui import Select
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[WARNING] Selenium not available - some features may be limited")

# Playwright imports - handle gracefully if not available
try:
    from playwright.async_api import async_playwright
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[WARNING] Playwright not available - browser automation features disabled")
    print("[INFO] To install: pip install playwright && playwright install")

# MCP tool function - define if not available
try:
    call_mcp_tool
except NameError:
    def call_mcp_tool(*args, **kwargs):
        print("[WARNING] MCP tools not available")
        return {"success": False, "error": "MCP tools not available"}


def load_panel_routes_from_json(json_path: str = "routelist.json") -> tuple:
    """Load and analyze ALL routes from routelist.json file for comprehensive testing."""
    try:
        if not os.path.exists(json_path):
            # Fallback to hardcoded routes if file doesn't exist
            fallback_main, fallback_create = get_fallback_routes()
            return fallback_main, fallback_create, {}

        with open(json_path, 'r') as f:
            routes = json.load(f)

        print(f"[INFO] 📊 Analyzing ALL {len(routes)} routes from Laravel application...")

        # Get ALL testable routes (not just index/create)
        all_testable_routes = get_all_testable_routes(routes)

        # Analyze routes and group by resource for CRUD testing
        resource_groups = analyze_routes_by_resource(routes)

        main_routes = []
        create_routes = []
        resource_operations = {}

        # Process each resource group for CRUD operations
        for resource_name, resource_routes in resource_groups.items():
            operations = categorize_resource_operations(resource_routes)

            # Add index route if available
            if 'index' in operations:
                main_routes.append(operations['index']['uri'])

            # Add create route if available
            if 'create' in operations:
                create_routes.append(operations['create']['uri'])

            # Store operations for this resource
            resource_operations[resource_name] = operations

        # Remove duplicates and sort
        main_routes = list(set(main_routes))
        create_routes = list(set(create_routes))
        main_routes.sort()
        create_routes.sort()

        # Prioritize important routes
        priority_routes = [
            '/', '/dashboard', '/admin', '/hr', '/accounting',
            '/hr/employees', '/accounting/invoices', '/accounting/payments'
        ]

        main_routes = prioritize_routes(main_routes, priority_routes)

        print(f"[INFO] ✅ Identified {len(resource_operations)} resources with {len(all_testable_routes)} total testable routes")
        print(f"[INFO] 📋 Will test: {len(main_routes)} index routes + {len(create_routes)} create routes + full CRUD operations")

        return all_testable_routes, create_routes, resource_operations

    except Exception as e:
        print(f"[WARN] Could not load routes from {json_path}: {e}")
        fallback_main, fallback_create = get_fallback_routes()
        return fallback_main, fallback_create, {}


def get_all_testable_routes(routes: list) -> list:
    """Get ALL testable routes from routelist.json (not just index/create)."""
    testable_routes = []

    for route in routes:
        uri = route.get('uri', '')
        method = route.get('method', '')

        # Skip API routes
        if uri.startswith('api/'):
            continue

        # Skip pure auth routes
        skip_routes = ['login', 'logout', 'password']
        if any(skip in uri for skip in skip_routes):
            continue

        # Skip yajra /datatables endpoints (these return JSON for AJAX, not pages)
        if uri.endswith('/datatables'):
            continue

        # Skip parameterized routes like /resource/{id}
        # These are NOT direct links and are handled separately by CRUD tests.
        if '{' in uri or '}' in uri:
            continue

        # Include web routes that can be tested
        if 'GET|HEAD' in method:
            testable_routes.append(uri)

    return list(set(testable_routes))  # Remove duplicates


def analyze_routes_by_resource(routes: list) -> dict:
    """Analyze routes and group them by resource type."""
    resources = {}

    for route in routes:
        uri = route.get('uri', '')
        name = route.get('name', '')
        method = route.get('method', '')

        # Skip API routes and pure auth routes (login, logout, password reset)
        if uri.startswith('api/'):
            continue

        # Skip non-resource routes (but allow parameterized routes)
        skip_routes = ['login', 'logout', 'password', 'verification', 'email']
        if any(skip in uri for skip in skip_routes):
            continue

        # Extract resource name from route name
        if name and '.' in name:
            parts = name.split('.')
            if len(parts) >= 2:
                # Get the main resource (e.g., 'hr.employees', 'accounting.invoices')
                # Skip if it's not a proper resource name
                if parts[0] in ['web', 'api', 'auth']:
                    continue

                resource_key = '.'.join(parts[:2])

                if resource_key not in resources:
                    resources[resource_key] = []
                resources[resource_key].append(route)

    return resources


def categorize_resource_operations(resource_routes: list) -> dict:
    """Categorize operations for a specific resource."""
    operations = {}

    for route in resource_routes:
        uri = route.get('uri', '')
        name = route.get('name', '')
        method = route.get('method', '')

        if not name or '.' not in name:
            continue

        route_type = name.split('.')[-1]

        # Standard CRUD operations
        if route_type == 'index' and 'GET|HEAD' in method:
            operations['index'] = route
        elif route_type == 'create' and 'GET|HEAD' in method:
            operations['create'] = route
        elif route_type == 'store' and 'POST' in method:
            operations['store'] = route
        elif route_type == 'show' and 'GET|HEAD' in method and '{' in uri:
            operations['show'] = route
        elif route_type == 'edit' and 'GET|HEAD' in method and '{' in uri:
            operations['edit'] = route
        elif route_type == 'update' and ('PUT' in method or 'PATCH' in method) and '{' in uri:
            operations['update'] = route
        elif route_type == 'destroy' and 'DELETE' in method and '{' in uri:
            operations['destroy'] = route
        elif route_type == 'datatables' and 'GET|HEAD' in method:
            operations['datatables'] = route
        # Special operations
        elif 'approve' in route_type and 'POST' in method:
            operations['approve'] = route
        elif 'reject' in route_type and 'POST' in method:
            operations['reject'] = route
        elif 'post' in route_type and 'POST' in method:
            operations['post'] = route
        elif 'activate' in route_type and 'POST' in method:
            operations['activate'] = route

    return operations


def prioritize_routes(routes: list, priority_patterns: list) -> list:
    """Prioritize important routes to the front of the list."""
    priority_routes = []
    other_routes = []

    for route in routes:
        route_path = route.lstrip('/')
        if any(pattern.lstrip('/') in route_path for pattern in priority_patterns):
            priority_routes.append(route)
        else:
            other_routes.append(route)

    return priority_routes + other_routes


def get_fallback_routes() -> tuple:
    """Fallback routes when routelist.json is not available."""
    main_routes = [
        "/", "dashboard", "admin", "hr", "accounting", "inventory", "role-permission",
        "hr/employees", "hr/departments", "hr/designations", "hr/attendance",
        "accounting/invoices", "accounting/payments", "accounting/customers", "accounting/vendors",
        "admin/settings/system", "role-permission/roles", "role-permission/permissions"
    ]
    create_routes = [
        "hr/employees/create", "accounting/invoices/create", "accounting/customers/create"
    ]
    return main_routes, create_routes


# === Backend configuration (credentials & endpoints) ===
# Base app URL
BASE_URL_DEFAULT = "http://localhost:8000/"
# Exact endpoints you specified
LOGIN_PATHS = ["/login"]

# Hard-coded admin credentials (backend side) – still used if you want scripted login later
ADMIN_EMAIL = "mirajul13041@gmail.com"
ADMIN_PASSWORD = "@Aa12345"


def log_to_widget(widget: ScrolledText | None, message: str) -> None:
    """Append a line to the log widget in a thread‑safe way."""
    if widget is None:
        print(message)
        return

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


def login_with_selenium(driver, base_url: str, log_widget: ScrolledText, email: str = None, password: str = None) -> bool:
    """Login using Selenium with robust error reporting."""
    # Use provided credentials or fall back to defaults
    email = email or ADMIN_EMAIL
    password = password or ADMIN_PASSWORD
    
    login_url = base_url.rstrip("/") + "/login"

    try:
        driver.get(login_url)
        log_to_widget(log_widget, f"[INFO] Navigating to login page: {login_url}")

        # Wait for page to load
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check if already logged in
        current_url = driver.current_url
        if current_url is None:
            current_url = ""
        current_url = current_url.rstrip("/")
        if not current_url.endswith("/login"):
            log_to_widget(log_widget, "[OK] Already logged in.")
            return True

        # Find identifier and password fields (the actual field names on this login page)
        try:
            identifier_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='identifier']"))
            )
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='password']"))
            )
            log_to_widget(log_widget, "[DEBUG] Found identifier and password fields.")
        except TimeoutException:
            log_to_widget(log_widget, "[ERROR] Could not find identifier or password fields on login page.")
            return False

        # Fill credentials
        identifier_field.clear()
        identifier_field.send_keys(email)
        password_field.clear()
        password_field.send_keys(password)
        log_to_widget(log_widget, "[DEBUG] Filled login credentials.")

        # Find and click submit button
        submit_locators = [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.XPATH, "//button[contains(., 'Login') or contains(., 'Sign in') or contains(., 'Sign In')]"),
        ]

        submit_clicked = False
        for by, value in submit_locators:
            try:
                btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((by, value)))
                btn.click()
                submit_clicked = True
                log_to_widget(log_widget, "[DEBUG] Clicked login submit button.")
                break
            except Exception:
                continue

        if not submit_clicked:
            # Try pressing Enter on password field
            try:
                password_field.send_keys("\n")
                submit_clicked = True
                log_to_widget(log_widget, "[DEBUG] Submitted login form with Enter key.")
            except Exception:
                pass

        if not submit_clicked:
            log_to_widget(log_widget, "[ERROR] Could not submit login form.")
            return False

        # Wait for redirect
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                current_url = driver.current_url
                if current_url is None:
                    current_url = ""
                current_url = current_url.rstrip("/")
                log_to_widget(log_widget, f"[DEBUG] Current URL during redirect check: {current_url}")
                if current_url and not current_url.endswith("/login"):
                    log_to_widget(log_widget, f"[OK] Login successful. Current URL: {current_url}")
                    # Wait a moment for page to fully load
                    time.sleep(2)
                    return True
            except Exception as e:
                log_to_widget(log_widget, f"[DEBUG] Error checking current URL: {e}")
            time.sleep(1)

        log_to_widget(log_widget, "[ERROR] Login did not redirect away from login page.")
        return False

    except Exception as e:
        log_to_widget(log_widget, f"[ERROR] Unexpected error during login: {e}")
        return False


class LinkTester:
    """Class to handle comprehensive link testing using MCP tools."""

    def __init__(self, base_url: str, log_widget: ScrolledText | None):
        self.base_url = base_url.rstrip("/")
        self.log_widget = log_widget
        self.visited_urls = set()
        self.test_results = []
        # Load routes from routelist.json
        self.all_routes, self.create_routes, self.resource_operations = load_panel_routes_from_json()
        self.main_routes = self.all_routes  # For backward compatibility

    def crawl_and_test_links_with_mcp(self, max_pages: int = 100) -> list:
        """Crawl and test links using MCP browser tools."""
        log_to_widget(self.log_widget, "[LINK_TEST] Starting MCP-based link crawling...")

        # Use dynamically loaded main panel routes
        test_paths = self.main_routes[:20]  # Test first 20 main routes to keep it manageable

        for path in test_paths:
            test_url = self.base_url + path
            try:
                log_to_widget(self.log_widget, f"[LINK_TEST] Testing navigation to: {test_url}")

                # Navigate using MCP
                nav_result = call_mcp_tool("cursor-ide-browser", "browser_navigate", {"url": test_url})
                log_to_widget(self.log_widget, f"[DEBUG] Navigation result: {nav_result}")

                # Wait for page load
                call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 2})

                # Record result
                self.test_results.append({
                    "type": "navigation_test",
                    "url": self.base_url,
                    "link_url": test_url,
                    "link_text": f"Navigation to {path}",
                    "status": "PASS" if nav_result.get("success", False) else "FAIL",
                    "response_time": "N/A",
                    "error_message": "" if nav_result.get("success", False) else f"Navigation failed: {nav_result}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

            except Exception as e:
                log_to_widget(self.log_widget, f"[ERROR] Error testing {test_url}: {e}")
                self.test_results.append({
                    "type": "navigation_test",
                    "url": self.base_url,
                    "link_url": test_url,
                    "link_text": f"Navigation to {path}",
                    "status": "ERROR",
                    "response_time": "N/A",
                    "error_message": str(e),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

        log_to_widget(self.log_widget, f"[LINK_TEST] Completed MCP link testing: {len(self.test_results)} results")
        return self.test_results

        # Setup session headers like in automation.py
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed_base = urlparse(self.base_url)
            parsed_url = urlparse(url)
            return parsed_base.netloc == parsed_url.netloc
        except:
            return False

    def normalize_url(self, url: str) -> str:
        """Normalize URL for consistent tracking."""
        if not url:
            return ""
        if url.startswith('/'):
            return urljoin(self.base_url.rstrip("/"), url)
        if not url.startswith(('http://', 'https://')):
            return urljoin(self.base_url.rstrip("/"), url)
        return url

    def crawl_and_test_links(self, start_url: str, max_pages: int = 200) -> list:
        """Crawl the application and test all links."""
        log_to_widget(self.log_widget, f"[INFO] Starting link crawling from: {start_url}")

        to_visit = deque([start_url])
        pages_tested = 0

        while to_visit and pages_tested < max_pages:
            current_url = to_visit.popleft()

            if current_url in self.visited_urls:
                continue

            self.visited_urls.add(current_url)
            pages_tested += 1

            log_to_widget(self.log_widget, f"[LINK_TEST] Testing page {pages_tested}/{max_pages}: {current_url}")

            try:
                self.driver.get(current_url)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )

                # Wait for potential dynamic content
                time.sleep(3)

                # Check page load status
                page_status = "PASS"
                response_time = "N/A"
                error_message = ""

                try:
                    # Try to get page title
                    title = self.driver.title or "No Title"
                    log_to_widget(self.log_widget, f"[LINK_TEST] Page title: '{title}'")
                except:
                    title = "Error Loading Title"
                    page_status = "FAIL"
                    error_message = "Could not load page title"

                # Wait a bit for dynamic content to load
                time.sleep(2)

                # Find ALL clickable elements on the page
                links = self.driver.find_elements(By.TAG_NAME, "a")
                # Also look for elements with click handlers or navigation links
                nav_links = self.driver.find_elements(By.CSS_SELECTOR, "[role='link'], .nav-link, .menu-item, .sidebar-link, .dropdown-item, .breadcrumb-item")
                # Look for button links and other clickable elements
                button_links = self.driver.find_elements(By.CSS_SELECTOR, "button[onclick], input[type='button'], input[type='submit']")
                all_clickable = links + nav_links + button_links

                log_to_widget(self.log_widget, f"[LINK_TEST] Found {len(links)} <a> tags, {len(nav_links)} nav elements, and {len(button_links)} button elements on {current_url}")

                # Debug: List all clickable elements found
                if all_clickable:
                    log_to_widget(self.log_widget, f"[LINK_TEST] Found {len(all_clickable)} total clickable elements:")
                    for i, link in enumerate(all_clickable[:10]):  # Show first 10 elements
                        try:
                            href = link.get_attribute("href") or link.get_attribute("onclick") or ""
                            text = link.text.strip() or link.get_attribute("title") or link.get_attribute("aria-label") or link.get_attribute("value") or "No text"
                            tag_name = link.tag_name
                            log_to_widget(self.log_widget, f"[LINK_TEST]   {i+1}. [{tag_name}] {text} -> {href}")
                        except Exception as e:
                            log_to_widget(self.log_widget, f"[LINK_TEST]   {i+1}. Error getting element info: {e}")

                # Test each clickable element
                for idx, element in enumerate(all_clickable, 1):
                    try:
                        href = element.get_attribute("href")
                        onclick = element.get_attribute("onclick")
                        element_text = element.text.strip() or element.get_attribute("title") or element.get_attribute("aria-label") or element.get_attribute("value") or f"Element {idx}"
                        tag_name = element.tag_name

                        # Skip if no actionable attribute
                        if not href and not onclick:
                            continue

                        log_to_widget(self.log_widget, f"[LINK_TEST] Testing element {idx}/{len(all_clickable)}: [{tag_name}] {element_text}")

                        # Handle external links
                        if href and not self.is_same_domain(self.normalize_url(href)):
                            self.test_results.append({
                                "type": "external_link",
                                "url": current_url,
                                "link_url": self.normalize_url(href) if href else onclick,
                                "link_text": f"[{tag_name}] {element_text}",
                                "status": "EXTERNAL",
                                "response_time": "N/A",
                                "error_message": "",
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            })
                            continue

                        # For internal links, try to click and navigate
                        element_status = "PASS"
                        element_error = ""
                        target_url = None

                        try:
                            # Store current URL before clicking
                            original_url = self.driver.current_url or ""

                            # Scroll element into view
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                            time.sleep(0.5)

                            # Click the element
                            element.click()
                            time.sleep(2)  # Wait for navigation/loading

                            # Check if URL changed (navigation occurred)
                            new_url = self.driver.current_url or ""
                            if new_url != original_url:
                                target_url = new_url
                                log_to_widget(self.log_widget, f"[LINK_TEST] Navigated to: {new_url}")

                                # Check if page loaded successfully
                                try:
                                    WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                                    )
                                    # Try to get page title to verify load
                                    title = self.driver.title
                                    if title:
                                        log_to_widget(self.log_widget, f"[LINK_TEST] Page loaded successfully: '{title}'")
                                    else:
                                        element_status = "WARN"
                                        element_error = "Page loaded but no title found"
                                except:
                                    element_status = "FAIL"
                                    element_error = "Page failed to load after click"
                            else:
                                # No navigation - might be a button or action
                                log_to_widget(self.log_widget, f"[LINK_TEST] No navigation occurred (button/action)")
                                target_url = f"action:{onclick if onclick else 'button'}"

                        except Exception as e:
                            element_status = "FAIL"
                            element_error = str(e)
                            log_to_widget(self.log_widget, f"[LINK_TEST] Error clicking element: {e}")

                        # Record the test result
                        self.test_results.append({
                            "type": "clickable_element",
                            "url": current_url,
                            "link_url": target_url or (self.normalize_url(href) if href else onclick),
                            "link_text": f"[{tag_name}] {element_text}",
                            "status": element_status,
                            "response_time": "N/A",
                            "error_message": element_error,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        })

                        # Add target URL to crawl queue if it's a new internal page
                        if (target_url and
                            target_url.startswith(('http://', 'https://')) and
                            self.is_same_domain(target_url) and
                            target_url not in self.visited_urls and
                            "#" not in target_url):  # Skip anchor links
                            to_visit.append(target_url)
                            log_to_widget(self.log_widget, f"[LINK_TEST] Added to crawl queue: {target_url}")

                        # Navigate back to original page for next element test (if we navigated away)
                        if target_url and target_url.startswith(('http://', 'https://')):
                            try:
                                self.driver.get(current_url)
                                WebDriverWait(self.driver, 10).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                                )
                                time.sleep(1)
                            except Exception as e:
                                log_to_widget(self.log_widget, f"[LINK_TEST] Error navigating back: {e}")

                    except Exception as e:
                        log_to_widget(self.log_widget, f"[LINK_TEST] Error testing element {idx}: {e}")
                        continue

                # Record page test result
                self.test_results.append({
                    "type": "page_load",
                    "url": current_url,
                    "link_url": "",
                    "link_text": title,
                    "status": page_status,
                    "response_time": response_time,
                    "error_message": error_message,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

                log_to_widget(self.log_widget, f"[LINK_TEST] Completed testing page: {current_url} - Status: {page_status}")

            except Exception as e:
                log_to_widget(self.log_widget, f"[LINK_TEST] Error loading page {current_url}: {e}")
                self.test_results.append({
                    "type": "page_load",
                    "url": current_url,
                    "link_url": "",
                    "link_text": "Page Load Error",
                    "status": "FAIL",
                    "response_time": "N/A",
                    "error_message": str(e),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

        log_to_widget(self.log_widget, f"[LINK_TEST] Completed link testing. Tested {pages_tested} pages, found {len(self.test_results)} test results.")
        return self.test_results


class FormTester:
    """Class to handle comprehensive form testing using MCP tools."""

    def __init__(self, base_url: str, log_widget: ScrolledText | None):
        self.base_url = base_url.rstrip("/")
        self.log_widget = log_widget
        self.test_results = []
        # Load routes from routelist.json
        self.all_routes, self.create_routes, self.resource_operations = load_panel_routes_from_json()
        self.main_routes = self.all_routes  # For backward compatibility

    def find_and_test_forms_with_mcp(self, page_url: str) -> list:
        """Test forms on current page using MCP tools."""
        log_to_widget(self.log_widget, f"[FORM_TEST] Testing forms on {page_url} using MCP")

        try:
            # Navigate to the page first
            nav_result = call_mcp_tool("cursor-ide-browser", "browser_navigate", {"url": page_url})
            if not nav_result.get("success", False):
                log_to_widget(self.log_widget, f"[ERROR] Failed to navigate to {page_url}")
                return []

            # Wait for page load
            call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 2})

            # Test common form fields for various modules
            test_fields = [
                ("input[name='first_name']", "Test First Name"),
                ("input[name='last_name']", "Test Last Name"),
                ("input[name='email']", "test@example.com"),
                ("input[name='phone']", "01712345678"),
                ("input[name='mobile']", "01712345678"),
                ("textarea[name='description']", "Test description for QA automation"),
                ("textarea[name='address']", "123 Test Street, Test City"),
                ("select[name='department']", "IT Department"),
                ("select[name='designation']", "Software Engineer"),
                ("input[name='status']", "active"),
                ("input[name='name']", "Test Name"),
                ("input[name='code']", "TEST001"),
                ("input[name='amount']", "1000"),
                ("input[name='salary']", "50000"),
            ]

            for field_selector, test_value in test_fields:
                try:
                    log_to_widget(self.log_widget, f"[FORM_TEST] Testing field: {field_selector}")

                    # For select fields, use select_option tool
                    if "select" in field_selector:
                        select_result = call_mcp_tool("cursor-ide-browser", "browser_select_option", {
                            "element": f"select field {field_selector}",
                            "ref": field_selector,
                            "values": [test_value]
                        })
                        success = select_result.get("success", False)
                    else:
                        # For input fields, use type tool
                        type_result = call_mcp_tool("cursor-ide-browser", "browser_type", {
                            "element": f"input field {field_selector}",
                            "ref": field_selector,
                            "text": test_value
                        })
                        success = type_result.get("success", False)

                    self.test_results.append({
                        "type": "form_field_test",
                        "url": page_url,
                        "link_url": field_selector,
                        "link_text": f"Field: {field_selector}",
                        "status": "PASS" if success else "FAIL",
                        "response_time": "N/A",
                        "error_message": "" if success else f"Failed to fill field: {field_selector}",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                except Exception as e:
                    log_to_widget(self.log_widget, f"[ERROR] Error testing field {field_selector}: {e}")
                    self.test_results.append({
                        "type": "form_field_test",
                        "url": page_url,
                        "link_url": field_selector,
                        "link_text": f"Field: {field_selector}",
                        "status": "ERROR",
                        "response_time": "N/A",
                        "error_message": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

            # Test form submission
            log_to_widget(self.log_widget, "[FORM_TEST] Testing form submission")
            submit_result = call_mcp_tool("cursor-ide-browser", "browser_click", {
                "element": "form submit button",
                "ref": "button[type='submit']"
            })

            self.test_results.append({
                "type": "form_submit_test",
                "url": page_url,
                "link_url": "button[type='submit']",
                "link_text": "Form Submit Button",
                "status": "PASS" if submit_result.get("success", False) else "FAIL",
                "response_time": "N/A",
                "error_message": "" if submit_result.get("success", False) else "Failed to submit form",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            # Wait for submission result
            call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 3})

        except Exception as e:
            log_to_widget(self.log_widget, f"[ERROR] Error in MCP form testing: {e}")

        log_to_widget(self.log_widget, f"[FORM_TEST] Completed MCP form testing: {len(self.test_results)} results")
        return self.test_results

    def find_and_test_forms(self, url: str) -> list:
        """Find all forms on a page and test them."""
        log_to_widget(self.log_widget, f"[FORM_TEST] Testing forms on: {url}")

        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Wait for dynamic content
            time.sleep(2)

            # Find ALL forms and form-like elements
            forms = self.driver.find_elements(By.TAG_NAME, "form")

            # Also look for dynamic forms and form containers
            form_containers = self.driver.find_elements(By.CSS_SELECTOR,
                ".form, .form-container, [data-form], .modal form, .card form, .panel form")
            all_forms = forms + form_containers

            log_to_widget(self.log_widget, f"[FORM_TEST] Found {len(forms)} <form> elements and {len(form_containers)} form containers on {url}")

            # Debug: Check for form elements
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            selects = self.driver.find_elements(By.TAG_NAME, "select")
            textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
            log_to_widget(self.log_widget, f"[FORM_TEST] Form elements: {len(buttons)} buttons, {len(inputs)} inputs, {len(selects)} selects, {len(textareas)} textareas")

            for idx, form in enumerate(all_forms, 1):
                try:
                    form_action = form.get_attribute("action") or url
                    form_method = form.get_attribute("method") or "GET"
                    form_id = form.get_attribute("id") or f"form_{idx}"
                    form_name = form.get_attribute("name") or ""

                    log_to_widget(self.log_widget, f"[FORM_TEST] Testing form {idx}: action={form_action}, method={form_method}")

                    # Find all input fields in the form
                    inputs = form.find_elements(By.CSS_SELECTOR, "input, select, textarea")
                    all_fields = []
                    required_fields = []
                    optional_fields = []

                    for inp in inputs:
                        inp_type = inp.get_attribute("type") or "text"
                        inp_name = inp.get_attribute("name") or ""
                        inp_id = inp.get_attribute("id") or ""
                        inp_required = inp.get_attribute("required") is not None

                        if inp_type in ["hidden", "submit", "button"]:
                            continue

                        field_info = (inp, inp_type, inp_name, inp_id)
                        all_fields.append(field_info)

                        if inp_required:
                            required_fields.append(field_info)
                        else:
                            optional_fields.append(field_info)

                    log_to_widget(self.log_widget, f"[FORM_TEST] Form {idx} has {len(all_fields)} fillable fields ({len(required_fields)} required, {len(optional_fields)} optional)")

                    # Test form submission
                    form_status = "PASS"
                    error_message = ""

                    try:
                        # Fill ALL fields with test data (required and optional for comprehensive testing)
                        all_fillable_fields = required_fields + optional_fields

                        for inp, inp_type, inp_name, inp_id in all_fillable_fields:
                            field_identifier = inp_name or inp_id or f"field_{all_fillable_fields.index((inp, inp_type, inp_name, inp_id))}"
                            test_value = self.generate_test_value(inp_type, field_identifier)
                            if test_value:
                                try:
                                    if inp_type in ["select", "select-one"]:
                                        select = Select(inp)
                                        options = select.options
                                        if len(options) > 1:
                                            # Try to select by value first, then by index
                                            try:
                                                select.select_by_value(test_value)
                                            except:
                                                select.select_by_index(min(1, len(options)-1))  # Select second option or last
                                    else:
                                        inp.clear()
                                        inp.send_keys(test_value)
                                    log_to_widget(self.log_widget, f"[FORM_TEST] Filled field '{field_identifier}' with: {test_value}")
                                except Exception as e:
                                    log_to_widget(self.log_widget, f"[FORM_TEST] Error filling field {field_identifier}: {e}")

                        # Try to submit the form
                        submit_buttons = form.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")

                        if submit_buttons:
                            # Click submit button
                            submit_buttons[0].click()
                        else:
                            # Try to submit form directly
                            try:
                                form.submit()
                            except:
                                # Last resort: press Enter in a text field
                                text_inputs = form.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
                                if text_inputs:
                                    text_inputs[0].send_keys("\n")

                        # Wait a bit for response
                        time.sleep(2)

                        # Check if submission was successful (various indicators)
                        current_url = self.driver.current_url or ""
                        page_source = self.driver.page_source.lower()

                        # Success indicators
                        success_indicators = [
                            "success" in page_source,
                            "created" in page_source,
                            "updated" in page_source,
                            "saved" in page_source,
                            current_url != url,  # Redirected
                        ]

                        # Error indicators
                        error_indicators = [
                            "error" in page_source,
                            "invalid" in page_source,
                            "failed" in page_source,
                            "required" in page_source and "error" in page_source,
                        ]

                        if any(success_indicators):
                            form_status = "PASS"
                        elif any(error_indicators):
                            form_status = "FAIL"
                            error_message = "Form validation errors detected"
                        else:
                            form_status = "UNKNOWN"
                            error_message = "Could not determine submission result"

                    except Exception as e:
                        form_status = "ERROR"
                        error_message = str(e)

                    # Record form test result
                    self.test_results.append({
                        "type": "form_submission",
                        "url": url,
                        "link_url": form_action,
                        "link_text": f"Form {idx} ({form_id or form_name or 'unnamed'})",
                        "status": form_status,
                        "response_time": "N/A",
                        "error_message": error_message,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                    log_to_widget(self.log_widget, f"[FORM_TEST] Form {idx} test result: {form_status}")

                    # Navigate back to original page for next form test
                    if idx < len(forms):
                        self.driver.get(url)
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )

                except Exception as e:
                    log_to_widget(self.log_widget, f"[FORM_TEST] Error testing form {idx}: {e}")
                    self.test_results.append({
                        "type": "form_submission",
                        "url": url,
                        "link_url": "",
                        "link_text": f"Form {idx} (error)",
                        "status": "ERROR",
                        "response_time": "N/A",
                        "error_message": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

        except Exception as e:
            log_to_widget(self.log_widget, f"[FORM_TEST] Error testing forms on {url}: {e}")

        return self.test_results

    def generate_test_value(self, field_type: str, field_name: str) -> str:
        """Generate appropriate test values for different field types."""
        field_name = field_name.lower()

        if field_type == "email" or "email" in field_name:
            return "test@example.com"
        elif field_type == "password" or "password" in field_name:
            return "TestPass123!"
        elif field_type == "number" or "phone" in field_name or "mobile" in field_name:
            return "01712345678"
        elif "name" in field_name:
            if "first" in field_name:
                return "Test"
            elif "last" in field_name:
                return "User"
            else:
                return "Test User"
        elif "address" in field_name:
            return "123 Test Street, Test City"
        elif "description" in field_name or "comment" in field_name:
            return "This is a test submission for QA automation."
        else:
            return "Test Value"


def login_with_mcp_tools(base_url: str, log_widget: ScrolledText | None, email: str = None, password: str = None) -> bool:
    """Login using MCP browser tools."""
    # Use provided credentials or fall back to defaults
    email = email or ADMIN_EMAIL
    password = password or ADMIN_PASSWORD
    
    login_url = base_url.rstrip("/") + "/login"

    try:
        log_to_widget(log_widget, f"[INFO] Navigating to login page: {login_url}")

        # Navigate to login page
        navigate_result = call_mcp_tool("cursor-ide-browser", "browser_navigate", {"url": login_url})
        log_to_widget(log_widget, f"[DEBUG] Navigation result: {navigate_result}")

        # Wait for page to load
        wait_result = call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 3})

        # Fill identifier field
        type_result = call_mcp_tool("cursor-ide-browser", "browser_type", {
            "element": "login identifier field",
            "ref": "input[name='identifier']",
            "text": email
        })
        log_to_widget(log_widget, f"[DEBUG] Identifier field result: {type_result}")

        # Fill password field
        type_result = call_mcp_tool("cursor-ide-browser", "browser_type", {
            "element": "login password field",
            "ref": "input[name='password']",
            "text": password
        })
        log_to_widget(log_widget, f"[DEBUG] Password field result: {type_result}")

        # Click submit button
        click_result = call_mcp_tool("cursor-ide-browser", "browser_click", {
            "element": "login submit button",
            "ref": "button[type='submit']"
        })
        log_to_widget(log_widget, f"[DEBUG] Submit button result: {click_result}")

        # Wait for redirect
        wait_result = call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 5})

        log_to_widget(log_widget, "[OK] Login completed with MCP tools!")
        return True

    except Exception as e:
        log_to_widget(log_widget, f"[ERROR] MCP login error: {e}")
        return False


class PlaywrightTester:
    """Comprehensive testing using Playwright plugin."""
    
    def __init__(self, base_url: str, log_widget: ScrolledText, email: str = None, password: str = None):
        self.base_url = base_url.rstrip("/")
        self.log_widget = log_widget
        self.email = email or ADMIN_EMAIL
        self.password = password or ADMIN_PASSWORD
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.test_results = []
        # Load routes from routelist.json
        self.all_routes, self.create_routes, self.resource_operations = load_panel_routes_from_json()
        self.main_routes = self.all_routes  # For backward compatibility

    def setup(self):
        """Setup Playwright browser."""
        log_to_widget(self.log_widget, "[PLAYWRIGHT] Setting up browser with Playwright plugin...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=False,  # Changed to False to show browser window
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--disable-web-security']
        )
        self.context = self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.page = self.context.new_page()

        # Add slow motion and visual delays for better visibility
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)  # Increase timeout for visibility
        log_to_widget(self.log_widget, "[PLAYWRIGHT] Playwright browser setup complete - browser window is now visible!")

    def teardown(self):
        """Clean up browser resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            log_to_widget(self.log_widget, "[PLAYWRIGHT] Browser cleanup complete")
        except Exception as e:
            log_to_widget(self.log_widget, f"[PLAYWRIGHT] Cleanup error: {e}")

    def login(self) -> bool:
        """Login using Playwright automation plugin."""
        try:
            login_url = self.base_url + "/login"
            log_to_widget(self.log_widget, f"[PLAYWRIGHT] Navigating to login: {login_url}")

            self.page.goto(login_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)  # Wait to see the login page

            # Fill login form using Playwright's powerful selectors
            log_to_widget(self.log_widget, "[PLAYWRIGHT] 📝 Filling login credentials...")
            self.page.fill("input[name='identifier']", self.email)
            time.sleep(1)  # Show email being typed

            self.page.fill("input[name='password']", self.password)
            time.sleep(1)  # Show password being typed

            # Click submit and wait for navigation
            log_to_widget(self.log_widget, "[PLAYWRIGHT] 🔘 Clicking login button...")
            self.page.click("button[type='submit']")
            time.sleep(2)  # Wait to see the click and loading

            self.page.wait_for_load_state('networkidle', timeout=30000)
            time.sleep(2)  # Wait to see the result

            # Check if login was successful
            current_url = self.page.url
            if "/login" not in current_url:
                log_to_widget(self.log_widget, f"[PLAYWRIGHT] ✅ Login successful! Current URL: {current_url}")
                time.sleep(2)  # Celebrate success
                return True
            else:
                log_to_widget(self.log_widget, "[PLAYWRIGHT] ❌ Login failed - still on login page")
                return False

        except Exception as e:
            user_error = self._convert_to_user_friendly_error(e)
            log_to_widget(self.log_widget, f"[PLAYWRIGHT] ❌ Login error: {user_error}")
            return False

    def systematic_crud_test(self) -> list:
        """Comprehensive testing of ALL routes from routelist.json - links, forms, and CRUD operations."""
        log_to_widget(self.log_widget, "[PLAYWRIGHT] 🔄 Starting comprehensive testing of ALL routes from routelist.json...")

        try:
            log_to_widget(self.log_widget, f"[PLAYWRIGHT] 📊 Found {len(self.all_routes)} total routes to test from routelist.json")

            # Phase 1: Test ALL individual routes (GET requests)
            log_to_widget(self.log_widget, "[PHASE 1] 🌐 Testing ALL route links...")
            self._test_all_route_links()

            # Phase 2: Test resource CRUD operations
            log_to_widget(self.log_widget, "[PHASE 2] 🧪 Testing CRUD operations for resources...")
            self._test_crud_operations()

            # Phase 3: Test forms on create pages
            log_to_widget(self.log_widget, "[PHASE 3] 📝 Testing form submissions...")
            self._test_form_submissions()

            log_to_widget(self.log_widget, f"[PLAYWRIGHT] ✅ Comprehensive testing completed. Results: {len(self.test_results)}")
            return self.test_results

        except Exception as e:
            log_to_widget(self.log_widget, f"[PLAYWRIGHT] ❌ Comprehensive testing failed: {e}")
            # Return whatever results we have so far
            return self.test_results if hasattr(self, 'test_results') else []

    def _test_all_route_links(self):
        """Test ALL routes from routelist.json by navigating to each one."""
        import random

        tested_count = 0
        max_routes = min(200, len(self.all_routes))  # Limit to 200 routes to prevent timeout

        log_to_widget(self.log_widget, f"[LINKS] 🔗 Testing {max_routes} routes out of {len(self.all_routes)} total routes...")

        # Prioritize routes without parameters first, then randomize order
        simple_routes = [r for r in self.all_routes if '{' not in r and '}' not in r]
        param_routes = [r for r in self.all_routes if '{' in r or '}' in r]

        # Randomize the order for less predictable testing
        random.shuffle(simple_routes)
        random.shuffle(param_routes)

        test_routes = simple_routes[:150] + param_routes[:50]  # Focus on simple routes first

        for route_uri in test_routes:
            if tested_count >= max_routes:
                break

            try:
                full_url = self.base_url + '/' + route_uri.lstrip('/')
                log_to_widget(self.log_widget, f"[LINKS] 🌐 Testing route: {route_uri}")

                # Navigate to the route
                self.page.goto(full_url, wait_until='networkidle', timeout=30000)
                time.sleep(1)  # Brief pause to see the page

                # Check if page loaded successfully
                user_friendly_error = self._check_page_for_user_errors()

                if user_friendly_error:
                    status = "FAIL"
                    error_message = user_friendly_error
                else:
                    status = "PASS"
                    error_message = ""

                self.test_results.append({
                    "type": "route_link_test",
                    "url": full_url,
                    "link_url": route_uri,
                    "link_text": f"Route: {route_uri}",
                    "status": status,
                    "response_time": "N/A",
                    "error_message": error_message,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

                tested_count += 1

                # Return to admin dashboard periodically to maintain session
                if tested_count % 20 == 0:
                    try:
                        admin_url = self.base_url + "/admin"
                        self.page.goto(admin_url, wait_until='networkidle', timeout=15000)
                        time.sleep(1)
                        log_to_widget(self.log_widget, f"[LINKS] 🔄 Session refresh - tested {tested_count} routes so far")
                    except Exception as e:
                        user_error = self._convert_to_user_friendly_error(e)
                        log_to_widget(self.log_widget, f"[LINKS] ⚠️ Session refresh failed: {user_error}")

            except Exception as e:
                user_error = self._convert_to_user_friendly_error(e)
                log_to_widget(self.log_widget, f"[LINKS] ❌ Error testing route {route_uri}: {user_error}")
                self.test_results.append({
                    "type": "route_link_test",
                    "url": self.base_url + '/' + route_uri.lstrip('/'),
                    "link_url": route_uri,
                    "link_text": f"Route: {route_uri}",
                    "status": "ERROR",
                    "response_time": "N/A",
                    "error_message": user_error,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                tested_count += 1

        log_to_widget(self.log_widget, f"[LINKS] ✅ Completed testing {tested_count} routes")

    def _test_crud_operations(self):
        """Test CRUD operations for resources with available operations."""
        import random

        # Prioritize testing order: most important resources first
        priority_resources = [
            'hr.employees', 'accounting.invoices', 'accounting.payments',
            'accounting.customers', 'accounting.vendors', 'hr.departments',
            'hr.designations', 'hr.attendance', 'hr.leave'
        ]

        tested_resources = []
        remaining_resources = list(self.resource_operations.keys())

        # Test priority resources first
        for resource_name in priority_resources:
            if resource_name in self.resource_operations and resource_name not in tested_resources:
                tested_resources.append(resource_name)

        # Add remaining resources up to our limit
        for resource_name in remaining_resources:
            if resource_name not in tested_resources and len(tested_resources) < 15:  # Test up to 15 resources for CRUD
                tested_resources.append(resource_name)

        # Randomize the testing order for unpredictability
        random.shuffle(tested_resources)

        log_to_widget(self.log_widget, f"[CRUD] 🎯 Testing CRUD operations for {len(tested_resources)} resources (randomized order)")

        for resource_name in tested_resources:
            try:
                operations = self.resource_operations[resource_name]
                log_to_widget(self.log_widget, f"[CRUD] 🧪 Testing resource: {resource_name} ({len(operations)} operations)")

                self._test_resource_operations(resource_name, operations)

                # Return to admin dashboard between resources
                try:
                    admin_url = self.base_url + "/admin"
                    self.page.goto(admin_url, wait_until='networkidle', timeout=20000)
                    time.sleep(1)
                except Exception as e:
                    log_to_widget(self.log_widget, f"[WARN] Could not return to admin dashboard: {e}")

            except Exception as e:
                user_error = self._convert_to_user_friendly_error(e)
                log_to_widget(self.log_widget, f"[CRUD] ❌ Error testing resource {resource_name}: {user_error}")

    def _test_form_submissions(self):
        """Test form submissions on create pages."""
        import random

        log_to_widget(self.log_widget, f"[FORMS] 📝 Testing form submissions on {len(self.create_routes)} create pages")

        # Randomize the order of form testing
        test_forms = self.create_routes[:20].copy()  # Test first 20 create forms
        random.shuffle(test_forms)

        for create_route in test_forms:
            try:
                create_url = self.base_url + '/' + create_route.lstrip('/')
                log_to_widget(self.log_widget, f"[FORMS] 📋 Testing create form: {create_route}")

                self.page.goto(create_url, wait_until='networkidle', timeout=30000)
                time.sleep(2)

                # Fill and submit the form
                filled_fields = self._fill_form_with_dummy_data()
                submitted = self._submit_create_form()

                self.test_results.append({
                    "type": "form_submission_test",
                    "url": create_url,
                    "link_url": create_route,
                    "link_text": f"Create Form: {create_route}",
                    "status": "PASS" if submitted else "FAIL",
                    "response_time": "N/A",
                    "error_message": f"Filled {filled_fields} fields, submitted: {submitted}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

            except Exception as e:
                user_error = self._convert_to_user_friendly_error(e)
                log_to_widget(self.log_widget, f"[FORMS] ❌ Error testing create form {create_route}: {user_error}")
                self.test_results.append({
                    "type": "form_submission_test",
                    "url": self.base_url + '/' + create_route.lstrip('/'),
                    "link_url": create_route,
                    "link_text": f"Create Form: {create_route}",
                    "status": "ERROR",
                    "response_time": "N/A",
                    "error_message": user_error,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

    def _submit_create_form(self) -> bool:
        """Submit a create form and check for success."""
        try:
            # Find and click submit button
            submit_buttons = self.page.query_selector_all('button[type="submit"], input[type="submit"]')
            if submit_buttons:
                submit_buttons[0].click()
                time.sleep(3)  # Wait for submission

                # Check for success indicators
                page_content = self.page.content().lower()
                success_indicators = ['created', 'success', 'saved', 'added', 'successfully']

                return any(indicator in page_content for indicator in success_indicators)
            return False
        except:
            return False

    def _categorize_routes(self) -> dict:
        """Categorize routes by resource type from routelist.json."""
        try:
            if not os.path.exists("routelist.json"):
                log_to_widget(self.log_widget, "[WARN] routelist.json not found, using fallback routes")
                return self._get_fallback_routes_by_resource()

            with open("routelist.json", 'r') as f:
                routes = json.load(f)

            resources = {}

            for route in routes:
                uri = route.get('uri', '')
                method = route.get('method', '')
                name = route.get('name', '')

                # Skip API routes and non-web routes
                if uri.startswith('api/') or 'GET|HEAD' not in method:
                    continue

                # Skip routes that require specific parameters
                if '{' in uri and '}' in uri:
                    continue

                # Extract resource name from URI
                resource_name = self._extract_resource_name(uri, name)
                if resource_name:
                    if resource_name not in resources:
                        resources[resource_name] = []
                    resources[resource_name].append(route)

            return resources

        except Exception as e:
            log_to_widget(self.log_widget, f"[ERROR] Failed to categorize routes: {e}")
            return self._get_fallback_routes_by_resource()

    def _extract_resource_name(self, uri: str, name: str) -> str:
        """Extract resource name from URI and route name."""
        # Remove leading slash
        uri = uri.lstrip('/')

        # Try to extract from route name first
        if name and '.' in name:
            parts = name.split('.')
            if len(parts) >= 2:
                resource = parts[0]
                if resource not in ['web', 'api', 'admin']:
                    return resource

        # Extract from URI
        parts = uri.split('/')
        if len(parts) >= 1:
            resource = parts[0]
            if resource and resource not in ['api', 'storage', 'app']:
                return resource

        return None

    def _get_fallback_routes_by_resource(self) -> dict:
        """Fallback resource categorization."""
        return {
            'dashboard': [{'uri': '/', 'method': 'GET|HEAD', 'name': 'dashboard'}],
            'hr': [{'uri': 'hr', 'method': 'GET|HEAD', 'name': 'hr.index'}],
            'employees': [{'uri': 'hr/employees', 'method': 'GET|HEAD', 'name': 'hr.employees.index'}],
            'accounting': [{'uri': 'accounting', 'method': 'GET|HEAD', 'name': 'accounting.index'}],
            'settings': [{'uri': 'admin/settings/system', 'method': 'GET|HEAD', 'name': 'settings.system.index'}],
        }

    def _test_resource_operations(self, resource_name: str, operations: dict):
        """Test CRUD operations for a specific resource using pre-analyzed operations."""
        try:
            # Test operations in logical order: Create, Read, Update, Delete
            created_id = None

            # 1. CREATE (POST) - Try to create a new record
            if 'store' in operations and 'create' in operations:
                create_page_route = operations['create']
                store_route = operations['store']
                created_id = self._test_create_operation(resource_name, create_page_route['uri'], store_route['uri'])

            # 2. READ (GET) - Test reading/listing
            if 'index' in operations:
                self._test_read_operation(resource_name, operations['index']['uri'])

            # 3. UPDATE (PUT/PATCH) - Try to update (if we created something)
            if 'update' in operations and 'edit' in operations and created_id:
                edit_route = operations['edit']
                update_route = operations['update']
                edit_uri = edit_route['uri'].replace('{id}', str(created_id)).replace('{'+resource_name.split('.')[-1]+'}', str(created_id))
                self._test_update_operation(resource_name, edit_uri, update_route['uri'], created_id)

            # 4. DELETE - Try to delete (if we created something)
            if 'destroy' in operations and created_id:
                destroy_route = operations['destroy']
                destroy_uri = destroy_route['uri'].replace('{id}', str(created_id)).replace('{'+resource_name.split('.')[-1]+'}', str(created_id))
                self._test_delete_operation(resource_name, destroy_uri, created_id)

            # 5. Test special operations (approve, reject, post, activate, etc.)
            self._test_special_operations(resource_name, operations, created_id)

        except Exception as e:
            log_to_widget(self.log_widget, f"[CRUD] ❌ Error in _test_resource_operations for {resource_name}: {e}")
            # Add error result
            self.test_results.append({
                "type": "resource_operations_error",
                "url": self.base_url,
                "link_url": resource_name,
                "link_text": f"Operations test for {resource_name}",
                "status": "ERROR",
                "response_time": "N/A",
                "error_message": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

    def _test_special_operations(self, resource_name: str, operations: dict, record_id: str = None):
        """Test special operations like approve, reject, post, activate."""
        special_operations = ['approve', 'reject', 'post', 'activate']

        for op_name in special_operations:
            if op_name in operations and record_id:
                try:
                    op_route = operations[op_name]
                    op_uri = op_route['uri'].replace('{id}', str(record_id)).replace('{'+resource_name.split('.')[-1]+'}', str(record_id))

                    log_to_widget(self.log_widget, f"[CRUD] 🔄 Testing {op_name.upper()} operation: {op_uri}")

                    # Navigate to the operation page or directly POST
                    if 'GET|HEAD' in op_route['method']:
                        self.page.goto(self.base_url + op_uri, wait_until='networkidle', timeout=30000)
                        time.sleep(2)

                        # Look for and click operation button
                        button_selectors = [
                            f'button[data-action="{op_name}"]',
                            f'button.{op_name}',
                            f'a[href*="{op_name}"]',
                            f'form[action*="{op_name}"] button[type="submit"]'
                        ]

                        for selector in button_selectors:
                            try:
                                button = self.page.query_selector(selector)
                                if button:
                                    button.click()
                                    time.sleep(3)
                                    break
                            except:
                                continue

                    elif 'POST' in op_route['method']:
                        # For POST operations, we might need to simulate the action
                        # This is complex as it may require CSRF tokens, etc.
                        log_to_widget(self.log_widget, f"[CRUD] ⚠️ {op_name.upper()} operation requires POST - manual testing recommended")

                    # Check result
                    page_content = self.page.content().lower()
                    if op_name.lower() in page_content or 'success' in page_content:
                        log_to_widget(self.log_widget, f"[CRUD] ✅ {op_name.upper()} operation successful")
                        self.test_results.append({
                            "type": f"operation_{op_name}",
                            "url": self.base_url + op_uri,
                            "link_url": op_uri,
                            "link_text": f"{op_name.upper()} {resource_name} (ID: {record_id})",
                            "status": "PASS",
                            "response_time": "N/A",
                            "error_message": "",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        })
                    else:
                        log_to_widget(self.log_widget, f"[CRUD] ⚠️ {op_name.upper()} operation result unclear")

                except Exception as e:
                    log_to_widget(self.log_widget, f"[CRUD] ❌ Error testing {op_name} operation: {e}")

    def _test_create_operation(self, resource_name: str, create_page_uri: str, post_uri: str) -> str:
        """Test CREATE operation (POST) with dummy data."""
        try:
            create_page_url = self.base_url + '/' + create_page_uri.lstrip('/')
            log_to_widget(self.log_widget, f"[CRUD] ➕ Testing CREATE: {create_page_url}")

            # Navigate to create page first
            self.page.goto(create_page_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Fill the create form with dummy data
            filled_fields = self._fill_form_with_dummy_data()

            # Submit the form
            submit_buttons = self.page.query_selector_all('button[type="submit"], input[type="submit"]')
            if submit_buttons:
                log_to_widget(self.log_widget, f"[CRUD] 📤 Submitting CREATE form with {filled_fields} fields")
                submit_buttons[0].click()
                time.sleep(3)  # Wait for submission

                # Check if creation was successful
                current_url = self.page.url
                page_content = self.page.content().lower()

                success_indicators = ['created', 'success', 'saved', 'added', 'successfully']
                if any(indicator in page_content for indicator in success_indicators) or current_url != create_page_url:
                    log_to_widget(self.log_widget, f"[CRUD] ✅ CREATE successful for {resource_name}")
                    self.test_results.append({
                        "type": "crud_create",
                        "url": create_url,
                        "link_url": current_url,
                        "link_text": f"CREATE {resource_name}",
                        "status": "PASS",
                        "response_time": "N/A",
                        "error_message": "",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                    # Try to extract created ID from URL
                    url_parts = current_url.split('/')
                    if url_parts and url_parts[-1].isdigit():
                        return url_parts[-1]
                else:
                    log_to_widget(self.log_widget, f"[CRUD] ❌ CREATE failed for {resource_name}")
                    self.test_results.append({
                        "type": "crud_create",
                        "url": create_url,
                        "link_url": current_url,
                        "link_text": f"CREATE {resource_name}",
                        "status": "FAIL",
                        "response_time": "N/A",
                        "error_message": "Creation failed - no success indicators found",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
            else:
                log_to_widget(self.log_widget, f"[CRUD] ⚠️ No submit button found for CREATE {resource_name}")

        except Exception as e:
            log_to_widget(self.log_widget, f"[CRUD] ❌ CREATE error for {resource_name}: {e}")
            self.test_results.append({
                "type": "crud_create",
                "url": create_url if 'create_url' in locals() else post_uri,
                "link_url": post_uri,
                "link_text": f"CREATE {resource_name}",
                "status": "ERROR",
                "response_time": "N/A",
                "error_message": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

        return None

    def _test_read_operation(self, resource_name: str, get_uri: str):
        """Test READ operation (GET)."""
        try:
            read_url = self.base_url + '/' + get_uri.lstrip('/')
            log_to_widget(self.log_widget, f"[CRUD] 👁️ Testing READ: {read_url}")

            self.page.goto(read_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Check if page loaded successfully
            try:
                page_title = self.page.title() or "No Title"
            except:
                page_title = "No Title"

            if isinstance(page_title, str) and "error" not in page_title.lower() and "not found" not in page_title.lower():
                log_to_widget(self.log_widget, f"[CRUD] ✅ READ successful for {resource_name} - '{page_title}'")
                self.test_results.append({
                    "type": "crud_read",
                    "url": read_url,
                    "link_url": read_url,
                    "link_text": f"READ {resource_name}",
                    "status": "PASS",
                    "response_time": "N/A",
                    "error_message": "",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })
            else:
                log_to_widget(self.log_widget, f"[CRUD] ❌ READ failed for {resource_name}")
                self.test_results.append({
                    "type": "crud_read",
                    "url": read_url,
                    "link_url": read_url,
                    "link_text": f"READ {resource_name}",
                    "status": "FAIL",
                    "response_time": "N/A",
                    "error_message": f"Page title indicates error: {page_title}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

        except Exception as e:
            log_to_widget(self.log_widget, f"[CRUD] ❌ READ error for {resource_name}: {e}")
            self.test_results.append({
                "type": "crud_read",
                "url": read_url if 'read_url' in locals() else get_uri,
                "link_url": get_uri,
                "link_text": f"READ {resource_name}",
                "status": "ERROR",
                "response_time": "N/A",
                "error_message": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })

    def _test_update_operation(self, resource_name: str, edit_page_uri: str, put_uri: str, record_id: str):
        """Test UPDATE operation (PUT/PATCH)."""
        try:
            # Navigate to edit page
            edit_url = self.base_url + '/' + edit_page_uri.replace('/{id}', f'/{record_id}').lstrip('/')
            log_to_widget(self.log_widget, f"[CRUD] ✏️ Testing UPDATE: {edit_url}")

            self.page.goto(edit_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Fill update form with modified dummy data
            filled_fields = self._fill_form_with_dummy_data(suffix="_updated")

            # Submit the form
            submit_buttons = self.page.query_selector_all('button[type="submit"], input[type="submit"]')
            if submit_buttons:
                log_to_widget(self.log_widget, f"[CRUD] 📤 Submitting UPDATE form with {filled_fields} fields")
                submit_buttons[0].click()
                time.sleep(3)

                # Check success
                page_content = self.page.content().lower()
                success_indicators = ['updated', 'success', 'saved', 'modified']
                if any(indicator in page_content for indicator in success_indicators):
                    log_to_widget(self.log_widget, f"[CRUD] ✅ UPDATE successful for {resource_name}")
                    self.test_results.append({
                        "type": "crud_update",
                        "url": edit_url,
                        "link_url": self.page.url,
                        "link_text": f"UPDATE {resource_name} (ID: {record_id})",
                        "status": "PASS",
                        "response_time": "N/A",
                        "error_message": "",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    log_to_widget(self.log_widget, f"[CRUD] ❌ UPDATE failed for {resource_name}")
            else:
                log_to_widget(self.log_widget, f"[CRUD] ⚠️ No submit button found for UPDATE {resource_name}")

        except Exception as e:
            log_to_widget(self.log_widget, f"[CRUD] ❌ UPDATE error for {resource_name}: {e}")

    def _test_delete_operation(self, resource_name: str, delete_uri: str, record_id: str):
        """Test DELETE operation."""
        try:
            # Navigate to the record page or list page
            list_url = self.base_url + '/' + delete_uri.replace('/{id}', '').replace('/destroy', '').lstrip('/')
            log_to_widget(self.log_widget, f"[CRUD] 🗑️ Testing DELETE: {list_url}")

            self.page.goto(list_url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Try to find and click delete button/link for the specific record
            # This is tricky as delete buttons might be in tables, modals, etc.
            delete_selectors = [
                f'a[href*="{record_id}"][data-method="delete"]',
                f'button[data-id="{record_id}"][onclick*="delete"]',
                f'form[action*="{record_id}"] button[type="submit"]',
                f'a[href*="/{record_id}"].delete, .delete-link'
            ]

            delete_found = False
            for selector in delete_selectors:
                try:
                    delete_element = self.page.query_selector(selector)
                    if delete_element:
                        log_to_widget(self.log_widget, f"[CRUD] 🗑️ Found delete element, clicking...")
                        delete_element.click()
                        time.sleep(1)

                        # Handle confirmation dialog if it appears
                        try:
                            self.page.click('button.confirm, .btn-confirm, button[data-bb-handler="confirm"]', timeout=5000)
                        except:
                            pass  # No confirmation dialog

                        time.sleep(2)
                        delete_found = True
                        break
                except:
                    continue

            if delete_found:
                page_content = self.page.content().lower()
                success_indicators = ['deleted', 'success', 'removed', 'successfully']
                if any(indicator in page_content for indicator in success_indicators):
                    log_to_widget(self.log_widget, f"[CRUD] ✅ DELETE successful for {resource_name} (ID: {record_id})")
                    self.test_results.append({
                        "type": "crud_delete",
                        "url": list_url,
                        "link_url": self.page.url,
                        "link_text": f"DELETE {resource_name} (ID: {record_id})",
                        "status": "PASS",
                        "response_time": "N/A",
                        "error_message": "",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    log_to_widget(self.log_widget, f"[CRUD] ❌ DELETE may have failed for {resource_name}")
            else:
                log_to_widget(self.log_widget, f"[CRUD] ⚠️ DELETE element not found for {resource_name} (ID: {record_id})")

        except Exception as e:
            log_to_widget(self.log_widget, f"[CRUD] ❌ DELETE error for {resource_name}: {e}")

    def _fill_form_with_dummy_data(self, suffix: str = "") -> int:
        """Fill all form fields with dummy data."""
        filled_count = 0

        # Common form field selectors
        field_selectors = [
            'input[type="text"]:not([readonly]):not([disabled])',
            'input[type="email"]:not([readonly]):not([disabled])',
            'input[type="number"]:not([readonly]):not([disabled])',
            'input[type="tel"]:not([readonly]):not([disabled])',
            'input[type="password"]:not([readonly]):not([disabled])',
            'textarea:not([readonly]):not([disabled])',
            'select:not([disabled])'
        ]

        for selector in field_selectors:
            try:
                fields = self.page.query_selector_all(selector)
                for field in fields:
                    try:
                        field_name = field.get_attribute('name') or field.get_attribute('id') or ''
                        field_type = field.get_attribute('type') or field.tag_name.lower()

                        # Generate dummy value based on field type and name
                        dummy_value = self._generate_smart_dummy_value(field_type, field_name, suffix)

                        if dummy_value or field.tag_name.lower() == 'select':
                            if field.tag_name.lower() == 'select':
                                # Handle select dropdowns - randomly select from available options
                                try:
                                    options = field.query_selector_all('option')
                                    if options and len(options) > 1:
                                        # Skip the first option (usually empty/placeholder)
                                        import random
                                        selected_option = random.choice(options[1:])  # Random from non-empty options
                                        option_value = selected_option.get_attribute('value')
                                        if option_value:
                                            self.page.select_option(f'select[name="{field_name}"]', option_value)
                                        else:
                                            # Fallback: click the option directly
                                            selected_option.click()
                                        filled_count += 1
                                    elif options and len(options) == 1:
                                        # Only one option available
                                        options[0].click()
                                        filled_count += 1
                                except Exception as e:
                                    # Last resort: try to click the select itself
                                    try:
                                        field.click()
                                        filled_count += 1
                                    except:
                                        pass
                            else:
                                # Handle input fields with random data
                                if dummy_value:
                                    field.fill(dummy_value)
                                    filled_count += 1
                                    time.sleep(0.1)  # Small delay between fields

                    except Exception as e:
                        continue  # Skip problematic fields

            except Exception as e:
                continue  # Skip problematic selectors

        return filled_count

    def _check_page_for_user_errors(self) -> str:
        """Check the current page for user-understandable errors."""
        try:
            # Check page title for common error indicators
            page_title = self.page.title() or ""
            title_lower = page_title.lower()

            if "404" in title_lower or "not found" in title_lower:
                return "Page Not Found (404 Error)"
            elif "403" in title_lower or "forbidden" in title_lower:
                return "Access Forbidden (403 Error)"
            elif "500" in title_lower or "server error" in title_lower:
                return "Server Error (500 Error)"
            elif "401" in title_lower or "unauthorized" in title_lower:
                return "Login Required (401 Error)"
            elif "403" in title_lower or "access denied" in title_lower:
                return "Access Denied"

            # Check page content for error messages
            page_text = self.page.inner_text("body").lower()

            if "csrf token mismatch" in page_text:
                return "Security Token Error (CSRF)"
            elif "validation error" in page_text or "the given data was invalid" in page_text:
                return "Form Validation Error"
            elif "method not allowed" in page_text:
                return "Invalid Request Method"
            elif "too many requests" in page_text:
                return "Too Many Requests (Rate Limited)"
            elif "service unavailable" in page_text:
                return "Service Temporarily Unavailable"
            elif "bad request" in page_text:
                return "Bad Request Error"
            elif "gateway timeout" in page_text:
                return "Gateway Timeout"
            elif "connection refused" in page_text:
                return "Connection Refused"
            elif "network error" in page_text:
                return "Network Connection Error"

            # Check for common Laravel error indicators
            if "whoops, looks like something went wrong" in page_text:
                return "Application Error (Laravel)"
            elif "maintenance mode" in page_text:
                return "Site Under Maintenance"
            elif "database connection" in page_text and "error" in page_text:
                return "Database Connection Error"

            return ""  # No user-visible errors found

        except Exception:
            return "Unable to check page content"

    def _convert_to_user_friendly_error(self, error: Exception) -> str:
        """Convert technical Playwright/browser errors to user-friendly messages."""
        error_str = str(error).lower()

        # HTTP Status Errors
        if "404" in error_str or "not found" in error_str:
            return "Page Not Found (404)"
        elif "403" in error_str or "forbidden" in error_str:
            return "Access Forbidden (403)"
        elif "401" in error_str or "unauthorized" in error_str:
            return "Authentication Required (401)"
        elif "500" in error_str or "internal server error" in error_str:
            return "Server Error (500)"
        elif "502" in error_str or "bad gateway" in error_str:
            return "Bad Gateway (502)"
        elif "503" in error_str or "service unavailable" in error_str:
            return "Service Unavailable (503)"
        elif "504" in error_str or "gateway timeout" in error_str:
            return "Gateway Timeout (504)"

        # Network/Connection Errors
        elif "connection refused" in error_str:
            return "Connection Refused - Server may be down"
        elif "connection timeout" in error_str or "timeout" in error_str:
            return "Connection Timeout - Server taking too long to respond"
        elif "network error" in error_str or "net::" in error_str:
            return "Network Error - Check internet connection"
        elif "dns" in error_str:
            return "DNS Error - Cannot resolve website address"

        # Browser/Page Errors
        elif "target page" in error_str and "closed" in error_str:
            return "Browser page was closed unexpectedly"
        elif "context" in error_str and "closed" in error_str:
            return "Browser session ended unexpectedly"
        elif "browser has been closed" in error_str:
            return "Browser was closed during testing"

        # Form/Input Errors
        elif "element not found" in error_str or "element is not attached" in error_str:
            return "Page element not found - Page structure may have changed"
        elif "element not visible" in error_str:
            return "Form element not accessible - May be hidden or disabled"
        elif "element not enabled" in error_str:
            return "Form element not interactive - May be disabled"

        # Security/Validation Errors
        elif "csrf" in error_str:
            return "Security token error - Try refreshing the page"
        elif "validation" in error_str:
            return "Form data validation failed"
        elif "required" in error_str:
            return "Required field is missing"

        # Generic fallback for technical errors
        else:
            # Extract just the main error type, not the full technical stack trace
            error_parts = str(error).split(':')
            main_error = error_parts[0].strip() if error_parts else str(error)

            # If it's still too technical, provide a generic message
            if len(main_error) > 100 or any(term in main_error.lower() for term in ['traceback', 'stack', 'exception']):
                return "Unexpected application error occurred"

            return main_error

    def _generate_smart_dummy_value(self, field_type: str, field_name: str, suffix: str = "") -> str:
        """Generate realistic fake values based on field type and name.

        Uses Faker when available, falls back to random data otherwise.
        """
        import random
        import string
        from datetime import datetime, timedelta

        field_name = (field_name or "").lower()

        # ===== Prefer Faker for realistic fake data when available =====
        if FAKER_AVAILABLE and faker is not None:
            # Email fields
            if field_type == 'email' or 'email' in field_name:
                return faker.unique.email()

            # Password fields
            if field_type == 'password' or 'password' in field_name:
                return faker.password(length=12)

            # Phone/Mobile fields
            if field_type == 'tel' or 'phone' in field_name or 'mobile' in field_name:
                return faker.phone_number()

            # Name fields
            if 'first_name' in field_name or 'firstname' in field_name:
                return faker.first_name()
            elif 'last_name' in field_name or 'lastname' in field_name:
                return faker.last_name()
            elif 'name' in field_name:
                return faker.name()

            # Address fields
            if 'address' in field_name:
                return faker.address().replace("\n", ", ")

            # Description/Comment fields
            if 'description' in field_name or 'comment' in field_name or field_type == 'textarea':
                return faker.paragraph(nb_sentences=3)

            # Date fields
            if 'date' in field_name:
                return faker.date_between(start_date='-1y', end_date='today').strftime("%Y-%m-%d")

            # Status fields
            if 'status' in field_name:
                return random.choice(['active', 'inactive', 'pending', 'approved', 'rejected', 'completed', 'draft'])

            # Department/Position fields
            if 'department' in field_name:
                return random.choice(['IT', 'HR', 'Finance', 'Marketing', 'Sales', 'Operations', 'Engineering', 'Support'])
            if 'designation' in field_name or 'position' in field_name:
                return random.choice(['Manager', 'Developer', 'Engineer', 'Analyst', 'Coordinator', 'Specialist', 'Assistant', 'Director'])

        # ===== Fallbacks when Faker is not available or field not matched =====

        # Email fields - random email
        if field_type == 'email' or 'email' in field_name:
            random_prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 10)))
            domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'example.com']
            return f"{random_prefix}{suffix}@{random.choice(domains)}"

        # Password fields - random strong password
        if field_type == 'password' or 'password' in field_name:
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            return ''.join(random.choices(chars, k=random.randint(8, 12))) + suffix

        # Phone/Mobile fields - random phone number
        if field_type == 'tel' or 'phone' in field_name or 'mobile' in field_name:
            prefixes = ['017', '018', '019', '015', '016']
            return random.choice(prefixes) + ''.join(random.choices(string.digits, k=8))

        # Number fields - random appropriate numbers
        if field_type == 'number':
            if 'salary' in field_name:
                return str(random.randint(30000, 150000))
            elif 'age' in field_name:
                return str(random.randint(18, 65))
            elif 'amount' in field_name or 'price' in field_name:
                return str(random.randint(100, 10000))
            elif 'quantity' in field_name or 'qty' in field_name:
                return str(random.randint(1, 100))
            elif 'year' in field_name:
                return str(random.randint(2020, 2030))
            else:
                return str(random.randint(1, 1000))

        # Name fields - random names
        if 'first_name' in field_name or 'firstname' in field_name:
            first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emma', 'James', 'Olivia', 'Robert', 'Sophia']
            return random.choice(first_names) + suffix
        elif 'last_name' in field_name or 'lastname' in field_name:
            last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
            return random.choice(last_names) + suffix
        elif 'name' in field_name:
            names = ['Test Company', 'Sample Corp', 'Demo Inc', 'Example LLC', 'Test Organization']
            return random.choice(names) + suffix

        # Address fields - random addresses
        if 'address' in field_name:
            streets = ['Main St', 'Oak Ave', 'Pine Rd', 'Elm St', 'Maple Dr', 'Cedar Ln', 'Birch Blvd']
            cities = ['Dhaka', 'Chittagong', 'Khulna', 'Rajshahi', 'Sylhet', 'Barisal', 'Rangpur']
            return f"{random.randint(1, 999)} {random.choice(streets)}{suffix}, {random.choice(cities)}"

        # Description/Comment fields - random text
        if 'description' in field_name or 'comment' in field_name or field_type == 'textarea':
            words = ['This', 'is', 'a', 'test', 'description', 'for', 'automated', 'testing', 'of', 'the', 'system']
            length = random.randint(10, 30)
            text = ' '.join(random.choices(words, k=length))
            return text + suffix

        # Date fields - random recent dates
        if 'date' in field_name:
            days_ago = random.randint(0, 365)
            date = datetime.now() - timedelta(days=days_ago)
            return date.strftime("%Y-%m-%d")

        # Status fields - random appropriate status
        if 'status' in field_name:
            statuses = ['active', 'inactive', 'pending', 'approved', 'rejected', 'completed', 'draft']
            return random.choice(statuses)

        # Department/Position fields - random values
        if 'department' in field_name:
            departments = ['IT', 'HR', 'Finance', 'Marketing', 'Sales', 'Operations', 'Engineering', 'Support']
            return random.choice(departments)
        elif 'designation' in field_name or 'position' in field_name:
            positions = ['Manager', 'Developer', 'Engineer', 'Analyst', 'Coordinator', 'Specialist', 'Assistant', 'Director']
            return random.choice(positions)

        # Select dropdowns - if it's a select field, we'll handle it in the fill method
        if field_type == 'select' or field_type == 'select-one':
            # Return empty string, will be handled by select option logic
            return ""

        # Generic fallback - random string
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=random.randint(5, 15))) + suffix

    def test_all_links_on_page(self, page_url: str):
        """Test all clickable links using Playwright plugin."""
        try:
            # Find all clickable elements
            links = self.page.query_selector_all('a[href]')
            buttons = self.page.query_selector_all('button[onclick], button:not([type="submit"])')
            clickable_elements = self.page.query_selector_all('[role="button"], .clickable, [data-clickable]')

            all_clickable = links + buttons + clickable_elements

            log_to_widget(self.log_widget, f"[LINK_TEST] 🔗 Found {len(all_clickable)} clickable elements")

            for i, element in enumerate(all_clickable[:30]):  # Limit to 30 elements per page
                try:
                    # Get element description
                    element_text = element.inner_text().strip()[:50] or f"Element {i+1}"
                    element_attrs = element.get_attribute('href') or element.get_attribute('onclick') or element.get_attribute('data-target') or ""

                    original_url = self.page.url

                    # Try to click the element
                    log_to_widget(self.log_widget, f"[LINK_TEST] 🔗 Clicking: {element_text}")
                    element.click(timeout=5000)
                    time.sleep(2)  # Wait to see the click
                    self.page.wait_for_load_state('networkidle', timeout=10000)

                    # Check if navigation occurred
                    new_url = self.page.url
                    navigation_occurred = new_url != original_url

                    self.test_results.append({
                        "type": "link_click",
                        "url": page_url,
                        "link_url": new_url if navigation_occurred else original_url,
                        "link_text": f"[{element_text}] {element_attrs[:30]}",
                        "status": "PASS",
                        "response_time": "N/A",
                        "error_message": "",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                    log_to_widget(self.log_widget, f"[LINK_TEST] ✅ Clicked: {element_text}")
                    time.sleep(2)  # Show the result

                    # If navigation occurred, go back
                    if navigation_occurred:
                        log_to_widget(self.log_widget, f"[LINK_TEST] 🔙 Going back...")
                        self.page.go_back(wait_until='networkidle', timeout=10000)
                        time.sleep(2)  # Show going back

                except Exception as e:
                    self.test_results.append({
                        "type": "link_click",
                        "url": page_url,
                        "link_url": page_url,
                        "link_text": f"Element {i+1}",
                        "status": "FAIL",
                        "response_time": "N/A",
                        "error_message": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    log_to_widget(self.log_widget, f"[LINK_TEST] ❌ Failed to click element {i+1}: {e}")

        except Exception as e:
            log_to_widget(self.log_widget, f"[LINK_TEST] ❌ Error testing links: {e}")

    def test_all_forms_on_page(self, page_url: str):
        """Test all forms using Playwright's powerful form handling plugin."""
        try:
            # Find all forms
            forms = self.page.query_selector_all('form')
            log_to_widget(self.log_widget, f"[FORM_TEST] 📝 Found {len(forms)} forms")

            for form_idx, form in enumerate(forms):
                try:
                    log_to_widget(self.log_widget, f"[FORM_TEST] 🧪 Testing form {form_idx + 1}")

                    # Get all form inputs
                    inputs = form.query_selector_all('input:not([type="submit"]):not([type="button"]), select, textarea')

                    # Fill form fields with test data
                    filled_fields = 0
                    for input_field in inputs:
                        try:
                            input_type = input_field.get_attribute('type') or 'text'
                            input_name = input_field.get_attribute('name') or ''
                            input_id = input_field.get_attribute('id') or ''

                            test_value = self.generate_test_value(input_type, input_name or input_id)

                            if test_value:
                                log_to_widget(self.log_widget, f"[FORM_TEST] 📝 Filling field: {input_name or input_id}")
                                if input_field.tag_name.lower() == 'select':
                                    # Handle select dropdowns
                                    try:
                                        self.page.select_option(f'select[name="{input_name}"]', test_value)
                                        filled_fields += 1
                                    except:
                                        # Try with visible text
                                        options = input_field.query_selector_all('option')
                                        if options:
                                            options[0].click()  # Select first option
                                            filled_fields += 1
                                else:
                                    # Handle text inputs
                                    input_field.fill(test_value)
                                    filled_fields += 1
                                time.sleep(0.5)  # Show each field being filled

                        except Exception as e:
                            log_to_widget(self.log_widget, f"[FORM_TEST] ⚠️ Error filling field: {e}")

                    log_to_widget(self.log_widget, f"[FORM_TEST] 📝 Filled {filled_fields} fields in form {form_idx + 1}")
                    time.sleep(1)  # Show all fields filled

                    # Try to submit the form
                    submit_buttons = form.query_selector_all('button[type="submit"], input[type="submit"]')

                    if submit_buttons:
                        log_to_widget(self.log_widget, f"[FORM_TEST] 📤 Clicking submit button for form {form_idx + 1}")
                        submit_buttons[0].click()
                    else:
                        # Try pressing Enter in a text field
                        text_inputs = form.query_selector_all('input[type="text"], input[type="email"]')
                        if text_inputs:
                            log_to_widget(self.log_widget, f"[FORM_TEST] 📤 Pressing Enter to submit form {form_idx + 1}")
                            text_inputs[0].press('Enter')

                    time.sleep(2)  # Show the submit action
                    # Wait for form submission result
                    self.page.wait_for_load_state('networkidle', timeout=15000)
                    time.sleep(2)  # Show the result

                    # Check for success indicators
                    page_content = self.page.content().lower()
                    success_indicators = ['success', 'created', 'updated', 'saved', 'submitted', 'complete']
                    error_indicators = ['error', 'invalid', 'failed', 'required']

                    if any(indicator in page_content for indicator in success_indicators):
                        status = "PASS"
                        error_msg = ""
                        log_to_widget(self.log_widget, f"[FORM_TEST] ✅ Form {form_idx + 1} submitted successfully")
                    elif any(indicator in page_content for indicator in error_indicators):
                        status = "FAIL"
                        error_msg = "Form validation errors detected"
                        log_to_widget(self.log_widget, f"[FORM_TEST] ❌ Form {form_idx + 1} has validation errors")
                    else:
                        status = "UNKNOWN"
                        error_msg = "Could not determine submission result"
                        log_to_widget(self.log_widget, f"[FORM_TEST] ❓ Form {form_idx + 1} submission result unknown")

                    self.test_results.append({
                        "type": "form_submission",
                        "url": page_url,
                        "link_url": f"form_{form_idx + 1}",
                        "link_text": f"Form {form_idx + 1} ({filled_fields} fields)",
                        "status": status,
                        "response_time": "N/A",
                        "error_message": error_msg,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

                    # Navigate back to original page for next form
                    self.page.goto(page_url, wait_until='networkidle', timeout=30000)

                except Exception as e:
                    log_to_widget(self.log_widget, f"[FORM_TEST] ❌ Error testing form {form_idx + 1}: {e}")
                    self.test_results.append({
                        "type": "form_submission",
                        "url": page_url,
                        "link_url": f"form_{form_idx + 1}",
                        "link_text": f"Form {form_idx + 1}",
                        "status": "ERROR",
                        "response_time": "N/A",
                        "error_message": str(e),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })

        except Exception as e:
            log_to_widget(self.log_widget, f"[FORM_TEST] ❌ Error in form testing: {e}")

    def generate_test_value(self, field_type: str, field_name: str) -> str:
        """Generate appropriate test values for different field types."""
        field_name = field_name.lower()

        if field_type == "email" or "email" in field_name:
            return "test@example.com"
        elif field_type == "password" or "password" in field_name:
            return "TestPass123!"
        elif field_type in ["number", "tel"] or "phone" in field_name or "mobile" in field_name:
            return "01712345678"
        elif "name" in field_name:
            if "first" in field_name:
                return "Test"
            elif "last" in field_name:
                return "User"
            else:
                return "Test User"
        elif "address" in field_name:
            return "123 Test Street, Test City"
        elif "description" in field_name or "comment" in field_name:
            return "This is a test submission for QA automation."
        else:
            return "Test Value"


def run_comprehensive_test(base_url: str, log_widget, email: str = None, password: str = None) -> list:
    """Run comprehensive QA testing using Playwright plugin with single login and systematic CRUD testing."""
    all_results = []

    # Check dependencies
    if not PLAYWRIGHT_AVAILABLE:
        error_msg = "[ERROR] ❌ Playwright is required for testing. Install with: pip install playwright && playwright install"
        if log_widget:
            log_to_widget(log_widget, error_msg)
        else:
            print(error_msg)
        return []

    try:
        log_to_widget(log_widget, "[INFO] 🚀 Starting comprehensive QA testing with Playwright plugin...")
        log_to_widget(log_widget, "[INFO] 👁️  Browser window will be visible - you can watch the testing in real-time!")
        log_to_widget(log_widget, "[INFO] 🔐 Login once, then test all routes systematically...")

        # Initialize Playwright tester
        tester = PlaywrightTester(base_url, log_widget, email, password)
        tester.setup()

        try:
            # Login once at the beginning
            if not tester.login():
                log_to_widget(log_widget, "[ERROR] ❌ Login failed. Cannot proceed with testing.")
                return []

            log_to_widget(log_widget, "[SUCCESS] ✅ Login successful! Starting systematic route testing...")

            # Run systematic CRUD testing for all routes
            results = tester.systematic_crud_test()
            if results:
                all_results.extend(results)

        except Exception as e:
            log_to_widget(log_widget, f"[ERROR] ❌ Testing failed but continuing: {e}")
        finally:
            try:
                tester.teardown()
            except:
                pass

        log_to_widget(log_widget, f"[INFO] ✅ Testing completed. Total results: {len(all_results)}")
        return all_results

    except Exception as e:
        # Try to convert to user-friendly error if we have a tester instance
        try:
            if 'tester' in locals() and hasattr(tester, '_convert_to_user_friendly_error'):
                user_error = tester._convert_to_user_friendly_error(e)
            else:
                user_error = str(e)
        except:
            user_error = str(e)

        log_to_widget(log_widget, f"[ERROR] ❌ Unexpected error during testing setup: {user_error}")
        # Make sure we return an empty list, not None
        return all_results if isinstance(all_results, list) else []


def test_forms_with_mcp(page_url: str, log_widget: ScrolledText | None) -> list:
    """Test forms on current page using MCP tools."""
    results = []

    try:
        log_to_widget(log_widget, f"[FORM_TEST] Testing forms on {page_url}")

        # Try to fill common form fields for various modules
        test_fields = [
            ("input[name='first_name']", "Test"),
            ("input[name='last_name']", "User"),
            ("input[name='email']", "test@example.com"),
            ("input[name='phone']", "01712345678"),
            ("input[name='mobile']", "01712345678"),
            ("textarea[name='description']", "Test submission for QA automation"),
            ("textarea[name='address']", "123 Test Street, Test City"),
            ("input[name='name']", "Test Name"),
            ("input[name='code']", "TEST001"),
            ("input[name='amount']", "1000"),
            ("input[name='salary']", "50000"),
        ]

        for field_selector, test_value in test_fields:
            try:
                type_result = call_mcp_tool("cursor-ide-browser", "browser_type", {
                    "element": f"form field {field_selector}",
                    "ref": field_selector,
                    "text": test_value
                })

                results.append({
                    "type": "form_field_fill",
                    "url": page_url,
                    "link_url": field_selector,
                    "link_text": f"Field: {field_selector}",
                    "status": "PASS" if type_result.get("success", False) else "FAIL",
                    "response_time": "N/A",
                    "error_message": "" if type_result.get("success", False) else f"Failed to fill field: {type_result}",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

            except Exception as e:
                results.append({
                    "type": "form_field_fill",
                    "url": page_url,
                    "link_url": field_selector,
                    "link_text": f"Field: {field_selector}",
                    "status": "ERROR",
                    "response_time": "N/A",
                    "error_message": str(e),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                })

        # Try to submit form
        submit_result = call_mcp_tool("cursor-ide-browser", "browser_click", {
            "element": "form submit button",
            "ref": "button[type='submit']"
        })

        results.append({
            "type": "form_submission",
            "url": page_url,
            "link_url": "button[type='submit']",
            "link_text": "Form Submit Button",
            "status": "PASS" if submit_result.get("success", False) else "FAIL",
            "response_time": "N/A",
            "error_message": "" if submit_result.get("success", False) else f"Failed to submit form: {submit_result}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        # Wait for form submission result
        call_mcp_tool("cursor-ide-browser", "browser_wait_for", {"time": 3})

    except Exception as e:
        log_to_widget(log_widget, f"[FORM_TEST] Error testing forms: {e}")

    return results


def save_results_to_csv(results: list, filename: str, log_widget: ScrolledText | None) -> None:
    """Save test results to CSV file."""
    if not results:
        log_to_widget(log_widget, "[WARN] No results to save.")
        return

    try:
        # Ensure directory exists (only if there's a directory path)
        dir_path = os.path.dirname(filename)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ["type", "url", "link_url", "link_text", "status", "response_time", "error_message", "timestamp"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        log_to_widget(log_widget, f"[OK] Results saved to {filename} ({len(results)} records)")

    except Exception as e:
        log_to_widget(log_widget, f"[ERROR] Failed to save results to CSV: {e}")


class QATestingApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("QA Testing Automation Tool")
        self.root.geometry("1000x700")
        self.root.minsize(900, 650)
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
            text="QA Testing Automation Tool",
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
            text="Automated QA testing for links, forms, and functionality",
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
            width=50,
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

        # Output CSV file selection
        csv_label = tk.Label(
            top_frame,
            text="Output CSV File",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        )
        csv_label.grid(row=2, column=0, sticky="w", pady=(10, 0))

        csv_inner = tk.Frame(top_frame, bg="white")
        csv_inner.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Default to current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        default_csv = os.path.join(current_dir, "record.csv")
        self.csv_path_var = tk.StringVar(value=default_csv)
        tk.Entry(
            csv_inner,
            textvariable=self.csv_path_var,
            width=70,
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
            text="Start QA Testing",
            command=self.start_testing,
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

        # Progress indicators
        progress_frame = tk.Frame(controls, bg="white")
        progress_frame.pack(side=tk.LEFT, padx=20)

        tk.Label(
            progress_frame,
            text="Links tested:",
            bg="white",
            fg="#6b7280",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT)
        self.links_count_var = tk.StringVar(value="0")
        tk.Label(
            progress_frame,
            textvariable=self.links_count_var,
            bg="white",
            fg="#111827",
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=(2, 10))

        tk.Label(
            progress_frame,
            text="Forms tested:",
            bg="white",
            fg="#6b7280",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT)
        self.forms_count_var = tk.StringVar(value="0")
        tk.Label(
            progress_frame,
            textvariable=self.forms_count_var,
            bg="white",
            fg="#111827",
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=(2, 0))

        # Log area card
        log_card = tk.Frame(main_container, bg="white", bd=1, relief=tk.SOLID)
        log_card.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_card, bg="white")
        log_header.pack(fill=tk.X, padx=15, pady=(10, 0))

        tk.Label(
            log_header,
            text="Test Logs",
            bg="white",
            fg="#111827",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)

        tk.Label(
            log_header,
            text="Real-time testing progress and results",
            bg="white",
            fg="#6b7280",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=10)

        log_frame = tk.Frame(log_card, bg="white")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

        self.log_widget = ScrolledText(
            log_frame,
            state="disabled",
            height=25,
            font=("Consolas", 9),
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="white",
        )
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    def browse_csv(self) -> None:
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = filedialog.asksaveasfilename(
            title="Save Test Results CSV",
            initialdir=current_dir,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="record.csv",
        )
        if path:
            self.csv_path_var.set(path)

    def start_testing(self) -> None:
        base_url = self.base_url_var.get().strip()
        if not base_url:
            messagebox.showwarning(
                "Base URL Required",
                "Please provide the base URL (e.g. http://192.168.68.129:8000).",
            )
            return

        csv_path = self.csv_path_var.get().strip()
        if not csv_path:
            messagebox.showwarning("Output File Required", "Please specify an output CSV file.")
            return
        
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        
        if not email or not password:
            messagebox.showwarning(
                "Credentials Required",
                "Please provide email and password."
            )
            return

        self.start_button.configure(state="disabled")
        self.status_var.set("Running...")
        self.links_count_var.set("0")
        self.forms_count_var.set("0")
        log_to_widget(self.log_widget, "=== Starting QA Testing ===")

        thread = threading.Thread(
            target=self._run_testing_thread,
            args=(base_url, csv_path, email, password),
            daemon=True,
        )
        thread.start()

    def _run_testing_thread(self, base_url: str, csv_path: str, email: str, password: str) -> None:
        try:
            # Run comprehensive testing
            results = run_comprehensive_test(base_url, self.log_widget, email, password)

            # Always try to save results to CSV, even if empty or with errors
            try:
                if results is None:
                    results = []
                save_results_to_csv(results, csv_path, self.log_widget)
                csv_saved = True
            except Exception as csv_error:
                log_to_widget(self.log_widget, f"[ERROR] Failed to save CSV: {csv_error}")
                csv_saved = False

            # Update progress counters
            if results:
                links_count = len([r for r in results if r["type"] in ["internal_link", "external_link", "page_load", "crud_read"]])
                forms_count = len([r for r in results if r["type"] in ["form_submission", "crud_create", "crud_update", "crud_delete"]])
            else:
                links_count = 0
                forms_count = 0

            def update_ui():
                self.links_count_var.set(str(links_count))
                self.forms_count_var.set(str(forms_count))
                self.start_button.configure(state="normal")

                if results and len(results) > 0:
                    self.status_var.set("Completed")
                    log_to_widget(self.log_widget, f"=== Testing Complete ===")
                    log_to_widget(self.log_widget, f"Links tested: {links_count}")
                    log_to_widget(self.log_widget, f"Forms tested: {forms_count}")
                    if csv_saved:
                        log_to_widget(self.log_widget, f"Results saved to: {csv_path}")

                        # Open CSV file in default application
                        try:
                            os.startfile(csv_path)
                        except:
                            pass  # Ignore if startfile not available
                else:
                    self.status_var.set("Completed with Errors")
                    log_to_widget(self.log_widget, "[WARN] Testing completed but no results were generated.")
                    if csv_saved:
                        log_to_widget(self.log_widget, f"Empty results file created at: {csv_path}")

            self.root.after(0, update_ui)

        except Exception as e:
            def update_ui():
                self.start_button.configure(state="normal")
                self.status_var.set("Error")
                log_to_widget(self.log_widget, f"[FATAL] Testing failed with error: {e}")

            self.root.after(0, update_ui)


def run_headless_testing(base_url: str, csv_path: str) -> None:
    """Run testing in headless mode without GUI."""
    print("=== Starting QA Testing (Headless Mode) ===")
    print(f"Base URL: {base_url}")
    print(f"Output CSV: {csv_path}")

    # Ensure CSV path is absolute or in current directory
    if not os.path.dirname(csv_path):
        csv_path = os.path.join(os.getcwd(), csv_path)

    # Run comprehensive testing
    results = run_comprehensive_test(base_url, None)

    # Always try to save results to CSV, even if empty
    try:
        if results is None:
            results = []
        save_results_to_csv(results, csv_path, None)
        csv_saved = True
    except Exception as csv_error:
        print(f"[ERROR] Failed to save CSV: {csv_error}")
        csv_saved = False

    # Update progress counters
    if results:
        links_count = len([r for r in results if r["type"] in ["internal_link", "external_link", "page_load", "crud_read"]])
        forms_count = len([r for r in results if r["type"] in ["form_submission", "crud_create", "crud_update", "crud_delete"]])
    else:
        links_count = 0
        forms_count = 0

    print("=== Testing Complete ===")
    print(f"Links tested: {links_count}")
    print(f"Forms tested: {forms_count}")
    if csv_saved:
        print(f"Results saved to: {csv_path}")
        # Try to open CSV file
        try:
            os.startfile(csv_path)
        except:
            pass  # Ignore if startfile not available
    else:
        print("[ERROR] Failed to save results to CSV file.")


def main() -> None:
    # Check command line arguments for headless mode
    if len(sys.argv) >= 3:
        base_url = sys.argv[1]
        csv_path = sys.argv[2]
        run_headless_testing(base_url, csv_path)
        return

    # GUI mode
    if not GUI_AVAILABLE:
        print("GUI not available. Use command line: python testing.py <base_url> <csv_path>")
        sys.exit(1)

    root = tk.Tk()
    app = QATestingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
