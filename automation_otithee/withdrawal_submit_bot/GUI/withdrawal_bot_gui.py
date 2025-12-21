import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import logging
import json
from urllib.parse import urljoin
import urllib3
from datetime import datetime
import config
# Use new config names for consistency
BASE_URL = config.ADMIN_BASE_URL
EMAIL = config.ADMIN_EMAIL_OR_MOBILE
PASSWORD = config.ADMIN_PASSWORD
GATEWAY_URL = config.GATEWAY_URL
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

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup
RESULTS_FOLDER = "results"
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Constants - use centralized config
ADMIN_LOGIN_URL = config.ADMIN_LOGIN_URL
WITHDRAWAL_URL = urljoin(BASE_URL, "/agent-ranking/agent/")

# Result files
FAILED_WITHDRAWALS_FILE = os.path.join(RESULTS_FOLDER, "failed_withdrawals.xlsx")
SUCCESS_WITHDRAWALS_FILE = os.path.join(RESULTS_FOLDER, "success_withdrawals.xlsx")

class WithdrawalBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Withdrawal Bot")
        self.root.geometry("900x750")
        self.root.minsize(800, 650)
        set_window_icon(self.root)
        self.file_path = None
        self.phone_numbers = []
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        self.logged_in = False
        self.user_id = None  # Add this line
        self.create_widgets()

    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Instruction label
        instruction = tk.Label(main_frame, text="Upload an Excel file with phone numbers or import directly.", fg="blue")
        instruction.pack(pady=5)
        
        # Button frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=10)
        
        # File selection
        self.upload_btn = tk.Button(button_frame, text="Upload Excel File", command=self.upload_file)
        self.upload_btn.pack(side=tk.LEFT, padx=5)
        
        # Import numbers button
        self.import_btn = tk.Button(button_frame, text="Direct Import Numbers", command=self.show_import_window)
        self.import_btn.pack(side=tk.LEFT, padx=5)

        # Progress bar
        self.progress = tk.DoubleVar()
        self.progress_bar = tk.ttk.Progressbar(main_frame, variable=self.progress, maximum=100)
        self.progress_bar.pack(fill=tk.X, padx=20, pady=10)

        # Log area (expandable but leaves room for buttons)
        log_frame = tk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=15, width=100, state='disabled')
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # Button frame at bottom (always visible)
        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Start button
        self.start_btn = tk.Button(bottom_frame, text="Start Processing", command=self.start_processing, state=tk.DISABLED)
        self.start_btn.pack(pady=5)

    def upload_file(self):
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = filedialog.askopenfilename(
            initialdir=current_dir,
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        if not file_path:
            return
        try:
            df = pd.read_excel(file_path)
            if len(df.columns) < 1:
                messagebox.showerror("Error", "Excel file must have at least one column for phone numbers.")
                return
            
            self.phone_numbers = []
            for phone in df.iloc[:, 0]:  # Get first column
                if pd.notna(phone):
                    phone_str = str(phone).strip()
                    if not phone_str.startswith('0'):
                        phone_str = '0' + phone_str
                    self.phone_numbers.append(phone_str)
            
            self.file_path = file_path
            self.log(f"Loaded {len(self.phone_numbers)} valid phone numbers.")
            self.start_btn.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read Excel file: {e}")

    def get_gateway_token(self):
        try:
            self.log("\n" + "="*50)
            self.log("🔑 GATEWAY LOGIN PROCESS")
            self.log("="*50)
            
            gateway_login_url = f"{GATEWAY_URL}/api/v1/auth/admin/login"
            
            # Update headers for gateway login
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            # Format login data according to API requirements
            login_data = {
                "email": EMAIL,
                "password": PASSWORD,
                "device_name": "withdrawal_bot"
            }
            
            self.log("Making gateway login request...")
            resp = self.session.post(gateway_login_url, json=login_data)
            
            if resp.status_code == 200:
                response_data = resp.json()
                self.log("\nGateway Response:")
                self.log(f"Status: {response_data.get('status')}")
                self.log(f"Message: {response_data.get('message')}")
                
                # Check for success in both possible formats
                if response_data.get("status") == "success" or response_data.get("success") == True:
                    # Get token from the correct path in response
                    token = response_data.get("access_token", {}).get("token")
                    if token:
                        self.log("✅ Successfully obtained gateway token")
                        return token
                    else:
                        self.log("❌ Token not found in gateway response")
                else:
                    self.log(f"❌ Gateway login failed: {response_data.get('message')}")
            else:
                self.log(f"❌ Gateway login failed with status code: {resp.status_code}")
            return None
        except Exception as e:
            self.log(f"❌ Error getting gateway token: {str(e)}")
            return None

    def admin_login(self):
        try:
            self.log("\n" + "="*50)
            self.log("🔐 ADMIN LOGIN PROCESS")
            self.log("="*50)
            
            self.log("Getting login page...")
            resp = self.session.get(ADMIN_LOGIN_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            csrf_token = soup.find("input", {"name": "_token"})
            
            if not csrf_token:
                self.log("❌ Failed to get CSRF token")
                return False
            
            login_data = {
                "_token": csrf_token["value"],
                "email": EMAIL,
                "password": PASSWORD,
                "remember": "on"
            }
            
            # Update headers for login request
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Origin': BASE_URL,
                'Referer': ADMIN_LOGIN_URL
            })
            
            self.log("Attempting login...")
            resp = self.session.post(ADMIN_LOGIN_URL, data=login_data, allow_redirects=True)
            
            # Log the response URL for debugging
            self.log(f"Redirected to: {resp.url}")
            
            # Check if we're still on the login page
            if ADMIN_LOGIN_URL in resp.url:
                self.log("❌ Login failed - redirected back to login page")
                self.logged_in = False
                return False
            
            # Verify login success by checking for admin dashboard elements
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Check for common admin dashboard elements
            admin_elements = [
                soup.find("div", {"class": "sidebar-menu"}),  # Admin sidebar
                soup.find("div", {"class": "main-header"}),   # Admin header
                soup.find("div", {"class": "content-wrapper"}) # Admin content
            ]
            
            if any(admin_elements):
                self.log("✅ Successfully logged in to admin panel")
                self.logged_in = True
                
                # Get user ID from the response
                user_info = soup.find("meta", {"name": "user-id"})  # Adjust selector based on actual HTML
                if user_info:
                    self.user_id = user_info.get("content")
                    self.log(f"Got user ID: {self.user_id}")
                else:
                    self.log("⚠️ Could not find user ID")
                
                # Get fresh gateway token
                gateway_token = self.get_gateway_token()
                if not gateway_token:
                    self.log("❌ Failed to get gateway token")
                    return False
                
                # Update headers for API requests
                self.session.headers.update({
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Authorization': f'Bearer {gateway_token}'
                })
                return True
            else:
                self.log("❌ Login failed - could not find admin dashboard elements")
                self.logged_in = False
                return False
            
        except Exception as e:
            self.log(f"❌ Login error: {str(e)}")
            self.logged_in = False
            return False

    def get_mother_payment_method(self, phone_number):
        try:
            url = f"{BASE_URL}/get-mother-payment-method/{phone_number}"
            resp = self.session.get(url)
            
            if resp.status_code == 200:
                self.log(f"Successfully retrieved mother payment method for {phone_number}")
                return True
            else:
                self.log(f"Failed to get mother payment method for {phone_number}")
                return False
        except Exception as e:
            self.log(f"Error getting mother payment method: {str(e)}")
            return False

    def get_custom_temporary_payment_method(self, phone_number):
        try:
            url = f"{BASE_URL}/custom-temporary-payment-method/{phone_number}"
            resp = self.session.get(url)
            
            if resp.status_code == 200:
                self.log(f"Successfully retrieved custom temporary payment method for {phone_number}")
                return True
            else:
                self.log(f"Failed to get custom temporary payment method for {phone_number}")
                return False
        except Exception as e:
            self.log(f"Error getting custom temporary payment method: {str(e)}")
            return False

    def process_withdrawal(self, phone_number):
        try:
            if not self.logged_in:
                self.log("Not logged in. Please login first")
                if not self.admin_login():
                    return False

            # Get the withdrawal page
            withdrawal_page_url = f"{WITHDRAWAL_URL}{phone_number}"
            resp = self.session.get(withdrawal_page_url)
            
            if ADMIN_LOGIN_URL in resp.url:
                self.log("Admin session expired, attempting to re-login")
                if not self.admin_login():
                    return False
                resp = self.session.get(withdrawal_page_url)

            soup = BeautifulSoup(resp.text, "html.parser")

            # Get user ID from the tooltip container
            user_id_div = soup.find("div", {"class": "tooltip-container col-8"})
            if user_id_div:
                user_id = user_id_div.get_text().strip().split()[0]  # Get first word and strip whitespace
                self.log(f"Found User ID: {user_id}")
            else:
                self.log("❌ Could not find user ID in withdrawal page")
                return False

            # Find the withdrawal form
            withdrawal_form = soup.find("form", {"id": "user_withdrawal_form"})
            if not withdrawal_form:
                self.log(f"Withdrawal form not found for phone number: {phone_number}")
                return False

            # Get available balance
            available_balance_elem = withdrawal_form.find("input", {"name": "available_balance"})
            if not available_balance_elem:
                self.log(f"Available balance not found for phone number: {phone_number}")
                return False

            available_balance = float(available_balance_elem["value"])
            self.log(f"\n{'='*50}")
            self.log(f"Processing Withdrawal for: {phone_number}")
            self.log(f"{'='*50}")
            self.log(f"Available Balance: {available_balance:.2f} Taka")
            
            # Calculate remaining balance and amount
            remaining_balance = 100  # Fixed remaining balance exactly 100
            withdrawal_amount = int(available_balance // 1) - remaining_balance  # Use floor division to ensure fixed integer
            
            # Check if we can maintain minimum balance
            if available_balance <= remaining_balance:
                self.log(f"❌ Insufficient balance for withdrawal")
                self.log(f"Minimum required balance: {remaining_balance} Taka")
                self.log(f"Available balance: {available_balance:.2f} Taka")
                self.log(f"{'='*50}\n")
                return False

            # Get payment method
            payment_method_select = withdrawal_form.find("select", {"id": "payment_methods"})
            if not payment_method_select:
                self.log(f"❌ Payment method select not found")
                self.log(f"{'='*50}\n")
                return False

            # Find bank payment method
            bank_option = None
            for option in payment_method_select.find_all("option"):
                if option.get("value") == "bank":
                    bank_option = option
                    break

            if not bank_option:
                self.log("❌ Bank payment method not found")
                self.log(f"{'='*50}\n")
                return False

            payment_method_id = bank_option.get("data-id")
            if not payment_method_id:
                self.log("❌ Payment method ID not found")
                self.log(f"{'='*50}\n")
                return False

            self.log(f"Payment Method ID: {payment_method_id}")

            # Prepare withdrawal payload
            payload = {
                "payment_method": "bank",
                "payment_method_id": int(payment_method_id),
                "amount": withdrawal_amount,
                "remaining_balance": remaining_balance
            }

            self.log(f"\nMaking withdrawal request...")
            self.log(f"Request Payload: {json.dumps(payload, indent=2)}")

            # Update headers for API request
            self.session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            })

            # Submit withdrawal request to gateway API
            # Remove this check since we're using the page's user_id
            # if not self.user_id:
            #     self.log("❌ No user ID available")
            #     return False

            gateway_url = f"{GATEWAY_URL}/api/v1/user/agent/make-withdrawal?user_id={user_id}&key=SDHFGS@24%54!*1"
            resp = self.session.post(gateway_url, json=payload)
            
            if resp.status_code == 200:
                try:
                    response_data = resp.json()
                    self.log(f"\nAPI Response:")
                    self.log(json.dumps(response_data, indent=2))
                    
                    if response_data.get("status") == 1:
                        self.record_success(phone_number, available_balance, withdrawal_amount)
                        self.log(f"{'='*50}\n")
                        return True
                    else:
                        error_message = response_data.get("message", "Unknown error")
                        error_details = response_data.get("errors", {})
                        if error_details:
                            error_message = f"{error_message} - Details: {error_details}"
                        self.record_failed(phone_number, available_balance, withdrawal_amount, error_message)
                        self.log(f"{'='*50}\n")
                        return False
                except json.JSONDecodeError as e:
                    self.log(f"❌ Invalid JSON response")
                    self.log(f"Error: {str(e)}")
                    self.log(f"Response: {resp.text}")
                    self.record_failed(phone_number, available_balance, withdrawal_amount, "Invalid response format")
                    self.log(f"{'='*50}\n")
                    return False
            else:
                self.log(f"❌ Request failed with status code: {resp.status_code}")
                self.log(f"Response: {resp.text}")
                self.record_failed(phone_number, available_balance, withdrawal_amount, f"HTTP Error: {resp.status_code}")
                self.log(f"{'='*50}\n")
                return False

        except Exception as e:
            error_text = str(e)
            self.log(f"❌ Error: {error_text}")
            self.record_failed(phone_number, available_balance, withdrawal_amount, error_text)
            self.log(f"{'='*50}\n")
            return False

    def record_success(self, phone_number, available_balance, withdrawal_amount):
        try:
            if not hasattr(self, 'success_wb'):
                from openpyxl import Workbook
                self.success_wb = Workbook()
                self.success_ws = self.success_wb.active
                self.success_ws.title = "Success"
                self.success_ws.append(["Phone Number", "Available Balance", "Withdrawal Amount"])
            
            self.success_ws.append([phone_number, available_balance, withdrawal_amount])
            self.success_wb.save(SUCCESS_WITHDRAWALS_FILE)
        except Exception as e:
            self.log(f"Error recording success: {str(e)}")

    def record_failed(self, phone_number, available_balance, withdrawal_amount, error_message):
        try:
            if not hasattr(self, 'failed_wb'):
                from openpyxl import Workbook
                self.failed_wb = Workbook()
                self.failed_ws = self.failed_wb.active
                self.failed_ws.title = "Failed"
                self.failed_ws.append(["Phone Number", "Available Balance", "Withdrawal Amount", "Error Message"])
            
            self.failed_ws.append([phone_number, available_balance, withdrawal_amount, error_message])
            self.failed_wb.save(FAILED_WITHDRAWALS_FILE)
        except Exception as e:
            self.log(f"Error recording failure: {str(e)}")

    def start_processing(self):
        self.start_btn.config(state=tk.DISABLED)
        self.upload_btn.config(state=tk.DISABLED)
        self.progress.set(0)
        threading.Thread(target=self.process_withdrawals, daemon=True).start()

    def process_withdrawals(self):
        if not self.admin_login():
            self.log("Failed to login. Exiting.")
            self.start_btn.config(state=tk.NORMAL)
            self.upload_btn.config(state=tk.NORMAL)
            return

        total = len(self.phone_numbers)
        success_count = 0
        
        for idx, phone_number in enumerate(self.phone_numbers):
            self.log(f"Processing phone number: {phone_number}")
            
            if self.process_withdrawal(phone_number):
                success_count += 1
            
            self.progress.set((idx + 1) / total * 100)
            time.sleep(2)  # Delay between requests

        self.log(f"Process completed. Success: {success_count}/{total}")
        self.start_btn.config(state=tk.NORMAL)
        self.upload_btn.config(state=tk.NORMAL)

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def show_import_window(self):
        ImportWindow(self.root, self.handle_imported_numbers)

    def handle_imported_numbers(self, numbers):
        self.phone_numbers = numbers
        self.log(f"Loaded {len(self.phone_numbers)} valid phone numbers.")
        self.start_btn.config(state=tk.NORMAL)

class ImportWindow:
    def __init__(self, parent, callback):
        self.window = tk.Toplevel(parent)
        self.window.title("Import Phone Numbers")
        self.window.geometry("400x300")
        self.callback = callback
        
        # Create text area
        self.text_area = scrolledtext.ScrolledText(self.window, height=10, width=40)
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Create import button
        self.import_btn = tk.Button(self.window, text="Import Numbers", command=self.import_numbers)
        self.import_btn.pack(pady=10)
        
        # Add instruction label
        instruction = tk.Label(self.window, text="Enter phone numbers (one per line)\nNumbers will automatically be prefixed with '0' if missing", fg="blue")
        instruction.pack(pady=5)

    def import_numbers(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter at least one phone number")
            return
            
        numbers = []
        for line in text.split('\n'):
            if not line.strip():
                continue
            number = line.strip()
            if not number.startswith('0'):
                number = '0' + number
            numbers.append(number)
        
        if not numbers:
            messagebox.showwarning("Warning", "No valid phone numbers found")
            return
            
        self.callback(numbers)
        self.window.destroy()

if __name__ == "__main__":
    import tkinter.ttk as ttk
    root = tk.Tk()
    WithdrawalBotGUI(root)
    root.mainloop()
