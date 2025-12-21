import sys
import os
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
from tkinter import ttk
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import datetime
import PyPDF2
import tabula
from urllib.parse import urljoin
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import config
# Use new config names for consistency
LOGIN_URL = config.ADMIN_LOGIN_URL
EMAIL_OR_MOBILE = config.ADMIN_EMAIL_OR_MOBILE
PASSWORD = config.ADMIN_PASSWORD
TARGET_URL = config.ADMIN_TARGET_URL
BASE_URL = config.ADMIN_BASE_URL
try:
    import sv_ttk  # modern ttk themes
except Exception:
    sv_ttk = None

# Add project root to path for icon_utils
try:
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from icon_utils import set_window_icon
except ImportError:
    # Fallback if icon_utils not found
    def set_window_icon(window):
        try:
            current_file = os.path.abspath(__file__)
            current_dir = os.path.dirname(current_file)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            icon_path = os.path.join(project_root, "icon.ico")
            if os.path.exists(icon_path):
                window.iconbitmap(icon_path)
        except:
            pass

class BuyPackageGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Otithee Agent Buy Package")
        self.root.geometry("1000x750")
        self.root.minsize(900, 650)
        set_window_icon(self.root)
        self.file_path = None
        self.phone_numbers = []
        self.package_data = {}  # Dictionary to store phone -> package_cost mapping
        self.log_file = os.path.join(os.path.dirname(__file__), 'log.txt')
        self.use_selenium = tk.BooleanVar(value=False)
        self.verbose_logs = tk.BooleanVar(value=False)
        self.fallback_to_selenium = tk.BooleanVar(value=True)
        self.current_theme = tk.StringVar(value='light')
        # Apply modern theme if available
        try:
            if sv_ttk:
                sv_ttk.set_theme("light")
        except Exception:
            pass
        self.create_widgets()

    def create_widgets(self):
        # Header
        header = tk.Frame(self.root)
        header.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(header, text="🛒 Otithee Agent Buy Package", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        if sv_ttk:
            ttk.Button(header, text="Toggle Theme", command=self.toggle_theme).pack(side=tk.RIGHT)

        # Content wrapper
        content = tk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        # Input section
        input_frame = ttk.Labelframe(content, text="Input")
        input_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
        self.excel_upload_btn = ttk.Button(input_frame, text="📄 Upload CSV/Excel", command=self.upload_excel)
        self.excel_upload_btn.pack(side=tk.LEFT, padx=(10, 8), pady=10)
        self.selected_file_label = tk.Label(input_frame, text="No file selected", fg="#666")
        self.selected_file_label.pack(side=tk.LEFT, padx=4)

        # Options section
        options_frame = ttk.Labelframe(content, text="Options")
        options_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
        tk.Checkbutton(options_frame, text="Run with visible browser (Selenium)", variable=self.use_selenium).pack(side=tk.LEFT, padx=10, pady=8)
        tk.Checkbutton(options_frame, text="Fallback to Selenium on failure (faster)", variable=self.fallback_to_selenium).pack(side=tk.LEFT, padx=10, pady=8)
        tk.Checkbutton(options_frame, text="Verbose logs", variable=self.verbose_logs).pack(side=tk.LEFT, padx=10, pady=8)
        ttk.Button(options_frame, text="🧩 Merge all CSVs in sheets/", command=self.merge_all_csvs).pack(side=tk.LEFT, padx=8, pady=8)

        # Actions section
        actions_frame = ttk.Labelframe(content, text="Actions")
        actions_frame.pack(fill=tk.X, padx=0, pady=(0, 10))
        self.status_label = tk.Label(actions_frame, text="No files loaded", fg="red")
        self.status_label.pack(side=tk.LEFT, padx=10, pady=(10, 6))
        self.start_btn = ttk.Button(actions_frame, text="▶️ Buy Package (Auto Select)", command=self.start_buying, state=tk.DISABLED)
        self.start_btn.pack(side=tk.RIGHT, padx=10, pady=(10, 6))

        # Progress
        self.progress = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(content, variable=self.progress, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=2, pady=(0, 10))

        # Logs section
        logs_frame = ttk.Labelframe(content, text="Logs")
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self.log_area = scrolledtext.ScrolledText(logs_frame, height=20, width=100, state='disabled')
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    def upload_excel(self):
        """Upload Excel/CSV file with 'number', 'package cost', and optional 'due' columns"""
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = filedialog.askopenfilename(
            initialdir=current_dir,
            filetypes=[ ("CSV files", "*.csv"),("Excel files", "*.xlsx *.xls")]
        )
        if not file_path:
            return
        try:
            if self.verbose_logs.get():
                self.log("Parsing Excel/CSV file...")
            self.status_label.config(text="Parsing Excel/CSV...", fg="orange")

            # Read the file with robust header detection (handles multi-row headers)
            is_csv = file_path.lower().endswith('.csv')
            header_idx = None

            def _normalize_header(val):
                try:
                    return str(val).strip().replace('"', '').lower().replace(' ', '').replace('\n', '').replace('\r', '')
                except Exception:
                    return ''

            # Probe first up to 50 rows to find a header row containing key columns
            try:
                if is_csv:
                    probe_df = pd.read_csv(file_path, header=None, nrows=50, dtype=str, engine='python')
                else:
                    probe_df = pd.read_excel(file_path, header=None, nrows=50, dtype=str)
                number_hdr_candidates = [
                    "number", "agentnumber", "agent_no", "agentno", "phone", "mobile", "agent_phone"
                ]
                cost_hdr_candidates = [
                    "packagecost", "package_cost", "packageprice", "price"
                ]
                for i in range(len(probe_df)):
                    row_vals = probe_df.iloc[i].tolist()
                    norm_vals = [_normalize_header(v) for v in row_vals]
                    has_number = any(c in norm_vals for c in number_hdr_candidates)
                    has_cost = any(c in norm_vals for c in cost_hdr_candidates)
                    if has_number and has_cost:
                        header_idx = i
                        break
            except Exception:
                header_idx = None

            # Fallback to row 0 if not found
            if is_csv:
                df = pd.read_csv(
                    file_path,
                    header=header_idx if header_idx is not None else 0,
                    quotechar='"',
                    skipinitialspace=True,
                    dtype=str,
                    engine='python'
                )
            else:
                df = pd.read_excel(
                    file_path,
                    header=header_idx if header_idx is not None else 0,
                    dtype=str
                )

            if header_idx is not None and self.verbose_logs.get():
                self.log(f"Detected header row at index {header_idx}")

            # Clean column names
            df.columns = [str(col).strip().replace('"', '').lower().replace(' ', '') for col in df.columns]
            if self.verbose_logs.get():
                self.log(f"File loaded with {len(df)} rows and columns: {list(df.columns)}")

            # Determine number and cost columns with fallbacks
            number_col_candidates = [
                "number", "agentnumber", "agent_no", "agentno", "phone", "mobile", "agent_phone"
            ]
            cost_col_candidates = [
                "packagecost", "package_cost", "packageprice", "price"
            ]
            name_col_candidates = [
                "agentname", "name", "fullname", "full_name", "first_name", "firstname"
            ]
            last_name_candidates = [
                "last_name", "lastname"
            ]
            referer_col_candidates = [
                "references", "referer", "referrer", "leaderreferences", "assistantmanagerreferer", "performancereferer"
            ]
            payment_cols_candidates = [
                "1stpayment", "firstpayment", "payment1", "payment_1",
                "2ndpayment", "secondpayment", "payment2", "payment_2",
                "3rdpayment", "thirdpayment", "payment3", "payment_3"
            ]

            number_col = next((c for c in number_col_candidates if c in df.columns), None)
            cost_col = next((c for c in cost_col_candidates if c in df.columns), None)
            name_col = next((c for c in name_col_candidates if c in df.columns), None)
            last_name_col = next((c for c in last_name_candidates if c in df.columns), None)
            referer_col = next((c for c in referer_col_candidates if c in df.columns), None)
            has_due = "due" in df.columns

            if not number_col or not cost_col:
                messagebox.showerror(
                    "Error",
                    "File must have columns for agent number and package cost (e.g., 'Agent Number', 'Package Cost')."
                )
                return

            phone_numbers = []
            package_data = {}
            for index, row in df.iterrows():
                raw_number = str(row.get(number_col, "")).strip()
                # Normalize: keep only digits
                digits_only = re.sub(r'\D', '', raw_number)
                # Handle country code 880 / +880
                if digits_only.startswith('880') and len(digits_only) > 3:
                    digits_only = '0' + digits_only[3:]
                # Ensure leading 0
                if digits_only and not digits_only.startswith('0'):
                    digits_only = '0' + digits_only
                agent_id = digits_only
                if not self.validate_phone(agent_id):
                    if self.verbose_logs.get():
                        self.log(f"Skipping invalid phone number: {agent_id}")
                    continue
                package_cost = None
                try:
                    cost_val = row[cost_col]
                    if pd.notna(cost_val):
                        package_cost = float(cost_val)
                except (ValueError, TypeError):
                    pass
                # Sum paid amounts if available
                total_paid = 0
                for col in payment_cols_candidates:
                    if col in df.columns:
                        try:
                            v = row[col]
                            if pd.notna(v):
                                total_paid += float(v)
                        except (ValueError, TypeError):
                            continue

                # Extract name and referer
                first_name = ""
                last_name = ""
                if name_col and pd.notna(row.get(name_col, None)):
                    full_name = str(row[name_col]).strip()
                    parts = [p for p in re.split(r"\s+", full_name) if p]
                    if parts:
                        first_name = parts[0]
                        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                if not first_name and last_name_col and pd.notna(row.get(last_name_col, None)):
                    first_name = ""
                    last_name = str(row[last_name_col]).strip()
                # fallback
                if not first_name:
                    first_name = agent_id

                referer_phone = None
                if referer_col and pd.notna(row.get(referer_col, None)):
                    ref_raw = str(row[referer_col])
                    m = re.search(r"(\d{8,15})", ref_raw)
                    if m:
                        referer_phone = m.group(1)
                        # Ensure leading 0 for referer phone
                        if referer_phone and not referer_phone.startswith('0'):
                            referer_phone = '0' + referer_phone

                due_amount = None
                if has_due:
                    try:
                        due_val = row['due']
                        if pd.notna(due_val):
                            due_amount = float(due_val)
                    except (ValueError, TypeError, KeyError):
                        pass
                if due_amount is None and package_cost is not None:
                    try:
                        due_amount = max(0, float(package_cost) - float(total_paid))
                    except Exception:
                        due_amount = 0
                if package_cost is not None:
                    package_data[agent_id] = {
                        'agent_id': agent_id,
                        'package_cost': int(package_cost),
                        'total_paid': int(total_paid),
                        'due_amount': int(due_amount) if due_amount is not None else 0,
                        'first_name': first_name,
                        'last_name': last_name,
                        'referer_phone': referer_phone,
                        'raw_row_data': row.to_dict()
                    }
                    phone_numbers.append(agent_id)
                    if self.verbose_logs.get():
                        self.log(f"Found: Number {agent_id} -> Package Cost: {package_cost}, Paid: {total_paid}, Due: {due_amount}")
            if not phone_numbers:
                messagebox.showerror("Error", "No valid phone numbers found in the file.")
                return
            self.phone_numbers = phone_numbers
            self.package_data = package_data
            self.file_path = file_path
            self.log(f"Successfully loaded {len(self.phone_numbers)} phone numbers from Excel/CSV")
            self.log(f"Package data for {len(self.package_data)} numbers")
            for phone, data in self.package_data.items():
                self.log(f"  {phone}: Cost={data['package_cost']}, Due={data['due_amount']}")
            self.status_label.config(text=f"Excel/CSV loaded: {len(self.phone_numbers)} numbers", fg="green")
            self.start_btn.config(state=tk.NORMAL)
            try:
                self.selected_file_label.config(text=os.path.basename(file_path))
            except Exception:
                pass
        except Exception as e:
            error_msg = f"Failed to parse Excel/CSV file: {e}"
            self.log(error_msg)
            messagebox.showerror("Error", error_msg)
            self.status_label.config(text="Excel/CSV parsing failed", fg="red")

    def validate_phone(self, phone):
        return bool(re.fullmatch(r'\d{8,15}', phone))

    def start_buying(self):
        self.start_btn.config(state=tk.DISABLED)
        self.excel_upload_btn.config(state=tk.DISABLED)
        self.progress.set(0)
        threading.Thread(target=self.buy_for_all, daemon=True).start()

    # Add this mapping at the top of the file (after imports)
    PACKAGE_ID_TO_NAME = {
        "2": "DHAKA-BOGURA-HELICOPTER-SERVICE - 7000 TK",
        "3": "ENTREPRENEUR-SKILL-ENHANCEMENT-TRAINING-UNLOCK-POT - 2500 TK",
        "4": "COXS-BAZAR-TOUR-PACKAGE-LARGEST-SEA-BEACH-BANGLADE - 10999 TK",
        "5": "DHAKA-SAINT-MARTIN-TOUR-PACKAGE-CORAL-ISLAND-PARAD - 12990 TK",
        "6": "DHAKA -SAJEK-DHAKA -TOUR-PACKAGE-DISCOVER-THE-LAND - 11800 TK",
        "7": "DHAKA-SYLHET-TOUR-PACKAGE-HEART-OF-SYLHET - 11630 TK",
        "8": "DIGITAL-MARKETING-FREELANCING-COURSE-OTITHEE-SKILL - 7800 TK",
        "9": "GRAPHICS-DESIGN-COURSE-OTITHEE-SKILL-DEVELOPMENT - 7800 TK",
        "12": "REAL-ESTATE-INVESTMENT-PACKAGE-SECURE-YOUR-FUTURE- - 310000 TK",
    }

    # Price map for known package IDs
    PACKAGE_ID_TO_PRICE = {
        "2": 7000,
        "3": 2500,
        "4": 10999,
        "5": 12990,
        "6": 11800,
        "7": 11630,
        "8": 7800,
        "9": 7800,
        "12": 310000,
    }

    CREATE_USER_URL = BASE_URL + "/sudo/create-user-custom"

    def buy_for_all(self):
        import os
        import pandas as pd
        self.log("Starting package purchase...")
        self.log("LOGIN URL " + LOGIN_URL)
        self.log("TARGET URL " + TARGET_URL)
        # Initialize log file
        timestamp_format = '%Y-%m-%d %H:%M:%S'
        timestamp = datetime.datetime.now().strftime(timestamp_format)
        self.write_to_log(f"\n{'='*80}")
        self.write_to_log(f"BUY PACKAGE SESSION STARTED: {timestamp}")
        self.write_to_log(f"Total phone numbers to process: {len(self.phone_numbers)}")
        self.write_to_log(f"Phone numbers: {self.phone_numbers}")

        session = None
        driver = None
        use_ui = bool(self.use_selenium.get())
        if use_ui:
            try:
                driver = self._init_selenium_driver(headless=False)
                logged_in = self._selenium_login(driver)
                if not logged_in:
                    self.log("Selenium login failed!")
                    self.start_btn.config(state=tk.NORMAL)
                    self.excel_upload_btn.config(state=tk.NORMAL)
                    return
                else:
                    self.log("Selenium login success.")
            except Exception as e:
                self.log(f"Selenium setup/login error: {e}")
                self.start_btn.config(state=tk.NORMAL)
                self.excel_upload_btn.config(state=tk.NORMAL)
                try:
                    if driver:
                        driver.quit()
                except Exception:
                    pass
                return
        else:
            # Reuse one session with connection pool tuning
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=2)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            })
        successful_purchases = []  # To store results for saving
        failed_purchases = []      # To store errors for saving
        if not use_ui:
            try:
                login_page = session.get(LOGIN_URL, timeout=12)
                soup = BeautifulSoup(login_page.text, 'lxml')
                csrf_token = soup.find('input', {'name': '_token'})['value']
                login_data = {
                    'email': EMAIL_OR_MOBILE,
                    'password': PASSWORD,
                    '_token': csrf_token,
                }
                login_response = session.post(LOGIN_URL, data=login_data, timeout=12)
                if login_response.status_code == 200 and "dashboard" in login_response.text:
                    self.log("Successfully logged in!")
                else:
                    self.log("Login failed! Check credentials or CSRF token.")
                    self.start_btn.config(state=tk.NORMAL)
                    self.excel_upload_btn.config(state=tk.NORMAL)
                    return
            except Exception as e:
                self.log(f"Login error: {e}")
                self.start_btn.config(state=tk.NORMAL)
                self.excel_upload_btn.config(state=tk.NORMAL)
                return
        total = len(self.phone_numbers)
        for idx, phone_number in enumerate(self.phone_numbers):
            try:
                package_cost = self.package_data.get(phone_number, {}).get('package_cost')
                due_amount = self.package_data.get(phone_number, {}).get('due_amount', 0)
                package_id = self.select_package_option(package_cost, due_amount)
                package_name = self.PACKAGE_ID_TO_NAME.get(str(package_id), str(package_id))
                if use_ui:
                    result = self.buy_package_with_selenium(phone_number, driver)
                else:
                    result = self.buy_package(phone_number, session)
                    # Optional fast fallback: if requests path fails and fallback enabled, try Selenium just for this number
                    if not result and self.fallback_to_selenium.get():
                        if not driver:
                            try:
                                driver = self._init_selenium_driver(headless=False)
                                if not self._selenium_login(driver):
                                    raise RuntimeError('Selenium login failed in fallback')
                            except Exception as e:
                                self.write_to_log(f"Fallback Selenium init/login failed: {e}")
                                driver = None
                        if driver:
                            result = self.buy_package_with_selenium(phone_number, driver)
                if result:
                    self.log(f"[{idx+1}/{total}] Bought package for {phone_number} at Package ID: {package_id} ({package_name})")
                    successful_purchases.append({
                        'number': phone_number,
                        'package_cost': package_cost,
                        'due': due_amount,
                        'package_id': package_id,
                        'package_name': package_name
                    })
                else:
                    self.log(f"[{idx+1}/{total}] Failed to buy package for {phone_number}")
                    failed_purchases.append({
                        'number': phone_number,
                        'package_cost': package_cost,
                        'due': due_amount,
                        'error_message': 'Failed to buy package (unknown error)'
                    })
            except Exception as e:
                self.log(f"[{idx+1}/{total}] Error: {phone_number} | {e}")
                failed_purchases.append({
                    'number': phone_number,
                    'package_cost': self.package_data.get(phone_number, {}).get('package_cost'),
                    'due': self.package_data.get(phone_number, {}).get('due_amount', 0),
                    'error_message': str(e)
                })
            self.progress.set((idx+1)/total*100)
        self.log("Package purchase finished.")
        self.start_btn.config(state=tk.NORMAL)
        self.excel_upload_btn.config(state=tk.NORMAL)
        try:
            if driver:
                driver.quit()
        except Exception:
            pass

        # Save results to CSV in results folder
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        results_dir = os.path.join(project_root, 'results', 'purchase_package')
        os.makedirs(results_dir, exist_ok=True)
        now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        if successful_purchases:
            result_file = os.path.join(results_dir, f"buy_package_results_{now_str}.csv")
            pd.DataFrame(successful_purchases).to_csv(result_file, index=False)
            self.log(f"Results saved to {result_file}")
        if failed_purchases:
            error_file = os.path.join(results_dir, f"buy_package_errors_{now_str}.csv")
            pd.DataFrame(failed_purchases).to_csv(error_file, index=False)
            self.log(f"Error results saved to {error_file}")

    def extract_package_info(self, soup, phone_number):
        """Extract package cost from file data (PDF/Excel/CSV) and due amount from the agent profile page"""
        # Get package data from file (PDF/Excel/CSV)
        file_data = self.package_data.get(phone_number, {})
        package_cost = file_data.get('package_cost')
        total_paid = file_data.get('total_paid')
        file_due_amount = file_data.get('due_amount')
        raw_row_data = file_data.get('raw_row_data', [])
        
        # Log the raw data for debugging
        self.write_to_log(f"File Raw Data for {phone_number}: {raw_row_data}")
        self.write_to_log(f"File Data for {phone_number}: Cost={package_cost}, Paid={total_paid}, Due={file_due_amount}")
        
        # Extract due amount from the web page (as backup/verification)
        web_due_amount = None
        try:
            page_text = soup.get_text(" ", strip=True)
        except Exception:
            page_text = str(soup)
        
        # Look for due amount patterns
        due_patterns = [
            r'due[:\s]*(\d+)',
            r'balance[:\s]*(\d+)',
            r'(\d+)\s*due',
            r'available\s*balance[:\s]*(\d+)',
            r'(\d+)\s*tk\s*due'
        ]
        
        for pattern in due_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                web_due_amount = int(match.group(1))
                break
        
        # Use file due amount if available, otherwise use web due amount
        due_amount = file_due_amount if file_due_amount is not None else web_due_amount

        # If still None but we have total_paid and package_cost, compute
        if due_amount is None and package_cost is not None and total_paid is not None:
            try:
                due_amount = max(0, int(package_cost) - int(total_paid))
            except Exception:
                pass
        
        # Log the extracted information
        self.write_to_log(f"File Package Cost for {phone_number}: {package_cost}")
        self.write_to_log(f"Web Due Amount for {phone_number}: {web_due_amount}")
        self.write_to_log(f"Final Due Amount for {phone_number}: {due_amount}")
        
        return package_cost, due_amount

    def select_package_option(self, package_cost, due_amount):
        """Select the appropriate package option (by ID) based on known price points."""
        try:
            normalized_cost = int(package_cost) if package_cost is not None else None
        except Exception:
            normalized_cost = None

        cost_to_id = {
            7000: "2",
            2500: "3",
            10999: "4",
            12990: "5",
            11800: "6",
            11630: "7",
            7800: "8",  # default to 8 when duplicate price exists
            310000: "12",
            210000: "12",  # legacy mapping if encountered
        }
        if normalized_cost in cost_to_id:
            return cost_to_id[normalized_cost]
            # Default fallback
        return "3"

    def buy_package(self, phone_number, session):
        # Ensure phone_number starts with 0
        if not phone_number.startswith('0'):
            phone_number = '0' + phone_number
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        agent_profile_url = f"{TARGET_URL}{phone_number}"
        
        # Log the request
        self.write_to_log(f"\n{'='*80}")
        self.write_to_log(f"[{timestamp}] Processing phone: {phone_number}")
        self.write_to_log(f"Agent Profile URL: {agent_profile_url}")
        # The form action on profile page dictates actual POST endpoint; no fixed buy URL
        
        # First, get the agent profile page to extract CSRF token from the modal form
        response = session.get(agent_profile_url, timeout=12)
        self.write_to_log(f"GET Profile Response Status: {response.status_code}")
        self.write_to_log(f"GET Profile Response URL: {response.url}")
        
        if response.status_code != 200:
            self.write_to_log(f"ERROR: Failed to load agent profile page for {phone_number}")
            self.write_to_log(f"Response Headers: {dict(response.headers)}")
            self.write_to_log(f"Response Text (first 500 chars): {response.text[:500]}")
            self.log(f"Failed to load agent profile page for {phone_number}")
            # Attempt to create user and retry
            try:
                created = self.create_user_if_needed(session, phone_number)
                if created:
                    self.write_to_log("User created, retrying profile fetch...")
                    response = session.get(agent_profile_url, timeout=12)
                    if response.status_code != 200:
                        return False
                    soup = BeautifulSoup(response.text, 'lxml')
                else:
                    return False
            except Exception as e:
                self.write_to_log(f"ERROR: create-user attempt failed: {e}")
            return False
        else:
        # Parse the response
            soup = BeautifulSoup(response.text, 'lxml')
        self.write_to_log(f"Page Title: {soup.title.string if soup.title else 'No title found'}")
        
        # Extract package cost and due amount
        package_cost, due_amount = self.extract_package_info(soup, phone_number)
        self.write_to_log(f"Extracted Package Cost: {package_cost}")
        self.write_to_log(f"Extracted Due Amount: {due_amount}")
        
        # Select the appropriate package option
        selected_package = self.select_package_option(package_cost, due_amount)
        self.write_to_log(f"Selected Package Option: {selected_package}")

        # Determine price and compute paid/due for form fields
        package_price = self.PACKAGE_ID_TO_PRICE.get(str(selected_package))
        file_data = self.package_data.get(phone_number, {})
        total_paid = file_data.get('total_paid')
        paid_amount = None
        due_amount_final = None

        if package_price is None and package_cost is not None:
            try:
                package_price = int(package_cost)
            except Exception:
                package_price = None

        if total_paid is not None and package_price is not None:
            try:
                paid_amount = max(0, min(int(total_paid), int(package_price)))
            except Exception:
                paid_amount = None

        if paid_amount is None and package_price is not None and due_amount is not None:
            try:
                paid_amount = max(0, int(package_price) - int(due_amount))
            except Exception:
                pass

        if paid_amount is None and package_price is not None:
            paid_amount = int(package_price)

        if package_price is not None:
            try:
                due_amount_final = max(0, int(package_price) - int(paid_amount))
            except Exception:
                due_amount_final = due_amount if due_amount is not None else 0
        else:
            due_amount_final = due_amount if due_amount is not None else 0

        # Decide section 1 flags based on paid/due
        section1_flags = {
            'installment_package': None,
            'due_package': None,
            'full_paid_package': None,
        }
        if due_amount_final == 0 and paid_amount and paid_amount > 0:
            section1_flags['full_paid_package'] = '1'
        elif due_amount_final > 0 and paid_amount and paid_amount > 0:
            section1_flags['installment_package'] = '1'
        elif due_amount_final > 0 and (not paid_amount or paid_amount == 0):
            section1_flags['due_package'] = '1'
        else:
            section1_flags['full_paid_package'] = '1'
        
        # Look for the buy package form in the modal
        buy_package_form = soup.find('form', {'id': 'buy_package_form'})
        if not buy_package_form:
            # Try to locate CSRF token from meta or any input[name=_token]
            token_input = soup.find('input', {'name': '_token'})
            meta_token = soup.find('meta', {'name': 'csrf-token'})
            csrf_token = token_input['value'] if token_input and token_input.has_attr('value') else (meta_token['content'] if meta_token and meta_token.has_attr('content') else None)
            if not csrf_token:
                self.write_to_log(f"ERROR: Buy package form/token not found for {phone_number}")
            self.write_to_log(f"Available forms: {[form.get('id', 'no-id') for form in soup.find_all('form')]}")
            self.log(f"Buy package form not found for {phone_number}")
            return False
        else:
            token_input = buy_package_form.find('input', {'name': '_token'})
            csrf_token = token_input['value'] if token_input and token_input.has_attr('value') else None
            if not csrf_token:
                self.write_to_log(f"ERROR: CSRF token not found in buy package form for {phone_number}")
                self.write_to_log(f"Available form inputs: {[input_tag.get('name', 'no-name') for input_tag in buy_package_form.find_all('input')]}")
                self.log(f"CSRF token not found for {phone_number}")
                return False
        self.write_to_log(f"CSRF Token found: {str(csrf_token)[:10]}...")
        
        # Prepare POST data with the selected package and new fields
        data = {
            '_token': csrf_token,
            'package_id': selected_package,
            'paid_amount_total': str(paid_amount if paid_amount is not None else ''),
            'total_due_amount': str(due_amount_final if due_amount_final is not None else ''),
            'assistant_manager_referer': '',
            'performance_referer': '',
        }

        # Add section 1 flags if set
        for key, val in section1_flags.items():
            if val:
                data[key] = val

        # Section 2: enable referrer commission unless due-only
        if not section1_flags.get('due_package'):
            data['refferer_commission'] = '1'

        # Determine POST URL: prefer form action; fallback to profile URL
        post_url = agent_profile_url
        try:
            if buy_package_form and buy_package_form.has_attr('action'):
                action_attr = buy_package_form.get('action')
                if action_attr:
                    post_url = urljoin(BASE_URL, action_attr)
        except Exception:
            pass

        self.write_to_log(f"POST URL: {post_url}")
        self.write_to_log(f"POST Data: {data}")
        
        # Submit the form directly to the buy package URL
        # Add referer to mimic browser form submission context
        headers = {'Referer': agent_profile_url}
        post_response = session.post(post_url, data=data, headers=headers, timeout=12, allow_redirects=True)
        self.write_to_log(f"POST Response Status: {post_response.status_code}")
        self.write_to_log(f"POST Response URL: {post_response.url}")
        self.write_to_log(f"POST Response Headers: {dict(post_response.headers)}")
        self.write_to_log(f"POST Response Text (first 1000 chars): {post_response.text[:1000]}")
        
        # Check for success
        if post_response.status_code in (200, 201, 302):
            # Heuristic: redirect back to agent page or contains success markers
            if TARGET_URL in post_response.url or 'success' in post_response.text.lower() or 'package' in post_response.text.lower():
                self.write_to_log(f"SUCCESS: Package purchase completed for {phone_number}")
                return True
        
        # If we get here, treat as failure and extract errors if possible
        self.write_to_log(f"FAILED: Package purchase failed for {phone_number}")
        # Parse the response to look for error messages
        response_soup = BeautifulSoup(post_response.text, 'lxml')
        error_messages = response_soup.find_all(['div', 'p', 'span'], class_=lambda x: x and any(word in x.lower() for word in ['error', 'alert', 'danger', 'warning', 'invalid']))
        if error_messages:
            self.write_to_log(f"Error messages found: {[msg.get_text(strip=True) for msg in error_messages]}")
        # Also log possible Location header if redirects disabled upstream
        loc = post_response.headers.get('Location')
        if loc:
            self.write_to_log(f"POST Location header: {loc}")
        return False

    def create_user_if_needed(self, session, phone_number):
        # Extract name/reference from loaded data
        record = self.package_data.get(phone_number, {})
        first_name = record.get('first_name') or phone_number
        last_name = record.get('last_name') or ''
        referer = record.get('referer_phone') or ''
        # Normalize referer number (digits only, handle 880, ensure leading 0)
        if referer:
            try:
                ref_digits = re.sub(r'\D', '', str(referer))
                if ref_digits.startswith('880') and len(ref_digits) > 3:
                    ref_digits = '0' + ref_digits[3:]
                if ref_digits and not ref_digits.startswith('0'):
                    ref_digits = '0' + ref_digits
                referer = ref_digits
            except Exception:
                pass

        # Load form for token
        try:
            r = session.get(self.CREATE_USER_URL, timeout=12)
            if r.status_code != 200:
                self.write_to_log(f"Create-user GET failed: {r.status_code}")
                return False
            soup = BeautifulSoup(r.text, 'lxml')
            token_input = soup.find('input', {'name': '_token'})
            csrf_token = token_input['value'] if token_input and token_input.has_attr('value') else None
            if not csrf_token:
                self.write_to_log("Create-user token not found")
                return False
        except Exception as e:
            self.write_to_log(f"Create-user GET error: {e}")
            return False

        payload = {
            '_token': csrf_token,
            'username': phone_number,
            'first_name': first_name,
            'last_name': last_name,
            'referer': referer,
        }
        try:
            pr = session.post(self.CREATE_USER_URL, data=payload, timeout=12)
            self.write_to_log(f"Create-user POST status: {pr.status_code}")
            self.write_to_log(f"Create-user POST text (first 500): {pr.text[:500]}")
            # Handle 'Referrer not found' by creating referer first, then retry
            need_create_referer = (pr.status_code == 404)
            try:
                j = pr.json()
                msg = str(j.get('message', '')).lower()
                status_val = j.get('status')
                if status_val == 404 or str(status_val) == '404':
                    need_create_referer = True
                if ('referrer not found' in msg) or ('referer not found' in msg):
                    need_create_referer = True
            except Exception:
                low = pr.text.lower()
                if ('referrer not found' in low) or ('referer not found' in low):
                    need_create_referer = True

            if need_create_referer and referer:
                self.write_to_log(f"Create-user: referer {referer} not found. Creating referer user first...")
                if self._create_minimal_user(session, referer):
                    self.write_to_log("Referer created. Retrying target user creation...")
                    # Retry target user create
                    pr2 = session.post(self.CREATE_USER_URL, data=payload, timeout=12)
                    self.write_to_log(f"Create-user retry status: {pr2.status_code}")
                    self.write_to_log(f"Create-user retry text (first 500): {pr2.text[:500]}")
                    return pr2.status_code in (200, 201, 302)
                else:
                    self.write_to_log("Failed to create referer; cannot proceed with user creation.")
                    return False

            return pr.status_code in (200, 201, 302)
        except Exception as e:
            self.write_to_log(f"Create-user POST error: {e}")
            return False

    def _create_minimal_user(self, session, phone):
        """Create a minimal user with username=phone and first_name=phone, no referer."""
        try:
            r = session.get(self.CREATE_USER_URL, timeout=12)
            if r.status_code != 200:
                self.write_to_log(f"Minimal user GET failed: {r.status_code}")
                return False
            soup = BeautifulSoup(r.text, 'lxml')
            token_input = soup.find('input', {'name': '_token'})
            csrf_token = token_input['value'] if token_input and token_input.has_attr('value') else None
            if not csrf_token:
                self.write_to_log("Minimal user token not found")
                return False
            payload = {
                '_token': csrf_token,
                'username': phone,
                'first_name': phone,
                'last_name': '',
                # Set company referer as requested when creating the referer user itself
                'referer': '01810093752',
            }
            pr = session.post(self.CREATE_USER_URL, data=payload, timeout=12)
            self.write_to_log(f"Minimal user POST status: {pr.status_code}")
            self.write_to_log(f"Minimal user POST text (first 300): {pr.text[:300]}")
            return pr.status_code in (200, 201, 302)
        except Exception as e:
            self.write_to_log(f"Minimal user POST error: {e}")
            return False

    def _init_selenium_driver(self, headless=False):
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        from webdriver_manager.chrome import ChromeDriverManager

        options = ChromeOptions()
        # Browser flags for speed and stability
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        if headless:
            options.add_argument('--headless=new')
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        # Speed up DOM operations
        try:
            driver.delete_all_cookies()
            driver.implicitly_wait(0)
            driver.set_page_load_timeout(15)
            driver.set_script_timeout(10)
        except Exception:
            pass
        driver.set_window_size(1280, 900)
        return driver

    def _selenium_login(self, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        driver.get(LOGIN_URL)
        try:
            wait = WebDriverWait(driver, 10)
            email_el = wait.until(EC.presence_of_element_located((By.NAME, 'email')))
            pwd_el = wait.until(EC.presence_of_element_located((By.NAME, 'password')))
            email_el.clear(); email_el.send_keys(EMAIL_OR_MOBILE)
            pwd_el.clear(); pwd_el.send_keys(PASSWORD)
            # Try to click submit button
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
                driver.execute_script("arguments[0].click();", submit_btn)
            except Exception:
                pwd_el.submit()
            # Wait for dashboard indicator
            wait.until(lambda d: 'dashboard' in d.page_source.lower() or 'dashboard' in d.current_url.lower())
            return True
        except Exception as e:
            self.write_to_log(f"Selenium login error: {e}")
            return False

    def buy_package_with_selenium(self, phone_number, driver):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC

        if not phone_number.startswith('0'):
            phone_number = '0' + phone_number

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        agent_profile_url = f"{TARGET_URL}{phone_number}"

        self.write_to_log(f"\n{'='*80}")
        self.write_to_log(f"[{timestamp}] [UI] Processing phone: {phone_number}")
        self.write_to_log(f"[UI] Agent Profile URL: {agent_profile_url}")

        driver.get(agent_profile_url)
        wait = WebDriverWait(driver, 8)
        # Ensure page loaded
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'body')))

        soup = BeautifulSoup(driver.page_source, 'lxml')
        package_cost, due_amount = self.extract_package_info(soup, phone_number)
        self.write_to_log(f"[UI] Extracted Package Cost: {package_cost}")
        self.write_to_log(f"[UI] Extracted Due Amount: {due_amount}")

        selected_package = self.select_package_option(package_cost, due_amount)
        self.write_to_log(f"[UI] Selected Package Option: {selected_package}")

        # Determine price and compute paid/due
        package_price = self.PACKAGE_ID_TO_PRICE.get(str(selected_package))
        file_data = self.package_data.get(phone_number, {})
        total_paid = file_data.get('total_paid')
        paid_amount = None
        due_amount_final = None
        if package_price is None and package_cost is not None:
            try:
                package_price = int(package_cost)
            except Exception:
                package_price = None
        if total_paid is not None and package_price is not None:
            try:
                paid_amount = max(0, min(int(total_paid), int(package_price)))
            except Exception:
                paid_amount = None
        if paid_amount is None and package_price is not None and due_amount is not None:
            try:
                paid_amount = max(0, int(package_price) - int(due_amount))
            except Exception:
                pass
        if paid_amount is None and package_price is not None:
            paid_amount = int(package_price)
        if package_price is not None:
            try:
                due_amount_final = max(0, int(package_price) - int(paid_amount))
            except Exception:
                due_amount_final = due_amount if due_amount is not None else 0
        else:
            due_amount_final = due_amount if due_amount is not None else 0

        # Ensure the modal opens: click trigger if present; if profile missing, create user and retry
        form_el = None
        try:
            # Prefer direct open via button if available
            trigger = None
            try:
                trigger = driver.find_element(By.CSS_SELECTOR, '[data-bs-target="#buy_package"], [data-target="#buy_package"]')
            except Exception:
                pass
            if trigger:
                driver.execute_script("arguments[0].click();", trigger)
            form_el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form#buy_package_form')))
        except Exception:
            self.write_to_log(f"[UI] WARNING: Form not visible; attempting to create user and retry.")
            if self.selenium_create_user_if_needed(driver, phone_number):
                driver.get(agent_profile_url)
                try:
                    form_el = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form#buy_package_form')))
                except Exception:
                    self.write_to_log(f"[UI] ERROR: Buy package form still not found for {phone_number}")
                    return False
            else:
                return False

        # Select package (trigger change to run page logic)
        try:
            select_el = driver.find_element(By.ID, 'packageSelect')
            try:
                Select(select_el).select_by_value(str(selected_package))
            except Exception:
                pass
            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                    select_el,
                    str(selected_package),
                )
            except Exception:
                pass
            # If package 12, wait for paid/due box to become visible
            if str(selected_package) == "12":
                try:
                    WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, 'fullPaidPackage')))
                except Exception:
                    pass
        except Exception as e:
            self.write_to_log(f"[UI] WARNING: Unable to select package by value: {e}")

        # Fill amounts if fields exist
        try:
            paid_input = driver.find_element(By.ID, 'paid_amount_total')
            due_input = driver.find_element(By.ID, 'total_due_amount')
            paid_input.clear(); paid_input.send_keys(str(paid_amount if paid_amount is not None else ''))
            due_input.clear(); due_input.send_keys(str(due_amount_final if due_amount_final is not None else ''))
        except Exception as e:
            self.write_to_log(f"[UI] INFO: Amount inputs missing or not required: {e}")

        # Fill referer fields if available
        try:
            record = self.package_data.get(phone_number, {})
            referer = record.get('referer_phone') or ''
            try:
                amr = driver.find_element(By.ID, 'assistant_manager_referer')
                amr.clear();
                if referer:
                    amr.send_keys(referer)
            except Exception:
                pass
            try:
                perf = driver.find_element(By.ID, 'performance_referer')
                perf.clear();
                if referer:
                    perf.send_keys(referer)
            except Exception:
                pass
        except Exception:
            pass

        # Section 1 checkboxes
        def set_checkbox(box_id, checked):
            try:
                el = driver.find_element(By.ID, box_id)
                if el.is_selected() != bool(checked):
                    el.click()
            except Exception:
                pass

        # Decide section 1 flags
        if due_amount_final == 0 and paid_amount and paid_amount > 0:
            set_checkbox('full_paid_package', True)
            set_checkbox('installment_package', False)
            set_checkbox('due_package', False)
        elif due_amount_final > 0 and paid_amount and paid_amount > 0:
            set_checkbox('installment_package', True)
            set_checkbox('full_paid_package', False)
            set_checkbox('due_package', False)
        elif due_amount_final > 0 and (not paid_amount or paid_amount == 0):
            set_checkbox('due_package', True)
            set_checkbox('full_paid_package', False)
            set_checkbox('installment_package', False)
        else:
            set_checkbox('full_paid_package', True)

        # Section 2: default referrer if not due-only
        try:
            if not driver.find_element(By.ID, 'due_package').is_selected():
                set_checkbox('refferer_commission', True)
                set_checkbox('package_type_ctg', False)
                set_checkbox('package_type_offer', False)
        except Exception:
            pass

        # Submit form
        try:
            submit_btn = form_el.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
            driver.execute_script("arguments[0].click();", submit_btn)
        except Exception:
            try:
                driver.execute_script("arguments[0].submit();", form_el)
            except Exception as e:
                self.write_to_log(f"[UI] ERROR: Failed to submit form: {e}")
                return False

        # Wait briefly for result
        try:
            WebDriverWait(driver, 6).until(
                lambda d: 'success' in d.page_source.lower() or 'package' in d.page_source.lower()
            )
            self.write_to_log(f"[UI] SUCCESS: Package purchase completed for {phone_number}")
            return True
        except Exception:
            self.write_to_log(f"[UI] FAILED: Package purchase may not have completed for {phone_number}")
            return False

    def selenium_create_user_if_needed(self, driver, phone_number):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        wait = WebDriverWait(driver, 8)
        try:
            driver.get(self.CREATE_USER_URL)
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'form[action*="create-user-custom"]')))
            record = self.package_data.get(phone_number, {})
            first_name = record.get('first_name') or phone_number
            last_name = record.get('last_name') or ''
            referer = record.get('referer_phone') or ''
            driver.find_element(By.ID, 'username').clear(); driver.find_element(By.ID, 'username').send_keys(phone_number)
            driver.find_element(By.ID, 'first_name').clear(); driver.find_element(By.ID, 'first_name').send_keys(first_name)
            driver.find_element(By.ID, 'last_name').clear(); driver.find_element(By.ID, 'last_name').send_keys(last_name)
            try:
                driver.find_element(By.ID, 'referer').clear(); driver.find_element(By.ID, 'referer').send_keys(referer)
            except Exception:
                pass
            try:
                submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
                driver.execute_script("arguments[0].click();", submit)
            except Exception:
                driver.find_element(By.ID, 'last_name').submit()
            # Wait until either redirect or confirmation appears
            WebDriverWait(driver, 6).until(lambda d: 'create-user' not in d.current_url or 'success' in d.page_source.lower())
            return True
        except Exception as e:
            self.write_to_log(f"[UI] Create-user error: {e}")
            return False

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def write_to_log(self, message):
        """Write detailed log to file"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + '\n')
        except Exception as e:
            print(f"Error writing to log file: {e}")

    def toggle_theme(self):
        if not sv_ttk:
            return
        try:
            if self.current_theme.get() == 'light':
                sv_ttk.set_theme('dark')
                self.current_theme.set('dark')
            else:
                sv_ttk.set_theme('light')
                self.current_theme.set('light')
        except Exception:
            pass

    def merge_all_csvs(self):
        try:
            sheets_dir = os.path.join(os.path.dirname(__file__), 'sheets')
            if not os.path.isdir(sheets_dir):
                messagebox.showerror("Error", f"Sheets directory not found: {sheets_dir}")
                return
            files = [os.path.join(sheets_dir, f) for f in os.listdir(sheets_dir) if f.lower().endswith('.csv')]
            if not files:
                messagebox.showinfo("Merge CSVs", "No CSV files found in sheets/ directory.")
                return
            self.log(f"Merging {len(files)} CSV files from sheets/ ...")

            merged_frames = []
            for fp in files:
                try:
                    df = self._read_csv_with_header_detection(fp)
                    if df is None or df.empty:
                        continue
                    # Normalize columns similar to upload logic
                    df.columns = [str(col).strip().replace('"', '').lower().replace(' ', '') for col in df.columns]
                    # Keep a useful subset for future use
                    keep_cols = [
                        c for c in df.columns if c in {
                            'number','agentnumber','agent_no','agentno','phone','mobile','agent_phone',
                            'packagecost','package_cost','packageprice','price',
                            'due','references','referer','referrer','leaderreferences',
                            'agentname','name','fullname','full_name',
                            '1stpayment','firstpayment','payment1','payment_1',
                            '2ndpayment','secondpayment','payment2','payment_2',
                            '3rdpayment','thirdpayment','payment3','payment_3'
                        }
                    ]
                    pruned = df[keep_cols].copy() if keep_cols else df.copy()
                    pruned['source_file'] = os.path.basename(fp)
                    merged_frames.append(pruned)
                except Exception as e:
                    self.log(f"Failed to read {fp}: {e}")

            if not merged_frames:
                messagebox.showinfo("Merge CSVs", "No data to merge (all files empty or unreadable).")
                return

            merged = pd.concat(merged_frames, ignore_index=True)
            # Save output to sheets/migrate/
            migrate_dir = os.path.join(sheets_dir, 'migrate')
            os.makedirs(migrate_dir, exist_ok=True)
            out_path = os.path.join(migrate_dir, f"merged_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            merged.to_csv(out_path, index=False)
            self.log(f"Merged CSV saved to {out_path}")
            messagebox.showinfo("Merge CSVs", f"Merged CSV saved to:\n{out_path}")
        except Exception as e:
            self.log(f"Merge CSVs error: {e}")
            messagebox.showerror("Error", f"Failed to merge CSVs: {e}")

    def _read_csv_with_header_detection(self, file_path):
        try:
            header_idx = None
            def _normalize_header(val):
                try:
                    return str(val).strip().replace('"', '').lower().replace(' ', '').replace('\n', '').replace('\r', '')
                except Exception:
                    return ''
            probe_df = pd.read_csv(file_path, header=None, nrows=50, dtype=str, engine='python')
            number_hdr_candidates = [
                'number','agentnumber','agent_no','agentno','phone','mobile','agent_phone'
            ]
            cost_hdr_candidates = [
                'packagecost','package_cost','packageprice','price'
            ]
            for i in range(len(probe_df)):
                row_vals = probe_df.iloc[i].tolist()
                norm_vals = [_normalize_header(v) for v in row_vals]
                has_number = any(c in norm_vals for c in number_hdr_candidates)
                has_cost = any(c in norm_vals for c in cost_hdr_candidates)
                if has_number and has_cost:
                    header_idx = i
                    break
            df = pd.read_csv(file_path, header=header_idx if header_idx is not None else 0, quotechar='"', skipinitialspace=True)
            return df
        except Exception as e:
            self.log(f"Header detection read failed for {file_path}: {e}")
            try:
                return pd.read_csv(file_path)
            except Exception:
                return None

if __name__ == "__main__":
    import tkinter.ttk as ttk
    root = tk.Tk()
    BuyPackageGUI(root)
    root.mainloop() 