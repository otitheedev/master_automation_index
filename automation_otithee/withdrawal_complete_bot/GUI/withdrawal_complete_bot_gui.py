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
from datetime import datetime
import urllib3
import config
# Use new config names for consistency
BASE_URL = config.ADMIN_BASE_URL
EMAIL_OR_MOBILE = config.ADMIN_EMAIL_OR_MOBILE
PASSWORD = config.ADMIN_PASSWORD
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

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup
RESULTS_FOLDER = "results"
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Status values
STATUS_SUCCESS = "6"

class WithdrawalBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Withdrawal Completion Bot")
        self.root.geometry("900x750")
        self.root.minsize(800, 650)
        set_window_icon(self.root)
        self.file_path = None
        self.withdrawals = []
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })
        self.create_widgets()

    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Instruction label
        instruction = tk.Label(main_frame, text="Upload an Excel file with withdrawal IDs or import directly.", fg="blue")
        instruction.pack(pady=5)
        
        # Button frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=10)
        
        # File selection
        self.upload_btn = tk.Button(button_frame, text="Upload Excel File", command=self.upload_file)
        self.upload_btn.pack(side=tk.LEFT, padx=5)
        
        # Import numbers button
        self.import_btn = tk.Button(button_frame, text="Direct Import Withdrawals", command=self.show_import_window)
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
            required_columns = ['WD ID']
            if not all(col in df.columns for col in required_columns):
                messagebox.showerror("Error", "Excel file must have 'WD ID' column.")
                return
            
            self.withdrawals = []
            for _, row in df.iterrows():
                if pd.notna(row['WD ID']):
                    self.withdrawals.append({
                        'wd_id': str(row['WD ID'])
                    })
            
            self.file_path = file_path
            self.log(f"Loaded {len(self.withdrawals)} valid withdrawals.")
            self.start_btn.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read Excel file: {e}")

    def login(self):
        try:
            self.log("Getting login page...")
            resp = self.session.get(f"{BASE_URL}/login")
            soup = BeautifulSoup(resp.text, "html.parser")
            csrf_token = soup.find("input", {"name": "_token"})
            
            if not csrf_token:
                self.log("Failed to get CSRF token")
                return False
            
            login_data = {
                "_token": csrf_token["value"],
                "email": EMAIL_OR_MOBILE,
                "password": PASSWORD,
                "remember": "on"
            }
            
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': BASE_URL,
                'Referer': f"{BASE_URL}/login"
            })
            
            self.log("Attempting login...")
            resp = self.session.post(
                f"{BASE_URL}/login",
                data=login_data,
                allow_redirects=True
            )
            
            if resp.url == f"{BASE_URL}/login":
                self.log("Login failed - redirected back to login page")
                return False
            
            self.log("Successfully logged in")
            return True
            
        except Exception as e:
            self.log(f"Login error: {str(e)}")
            return False

    def complete_withdrawal(self, wd_id):
        try:
            url = f"{BASE_URL}/edit-user-withdrawals/{wd_id}"
            self.log(f"Accessing withdrawal page for ID: {wd_id}")
            
            resp = self.session.get(url)
            if resp.status_code != 200:
                self.log(f"Failed to access page. Status code: {resp.status_code}")
                return False
                
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find the main form
            main_form = None
            for form in soup.find_all("form"):
                if form.find("select", {"name": "status"}):
                    main_form = form
                    break
            
            if not main_form:
                self.log("Failed to find withdrawal form on page")
                return False
                
            csrf_token = main_form.find("input", {"name": "_token"})
            if not csrf_token:
                self.log("Failed to get CSRF token from withdrawal form")
                return False
            
            # Collect form inputs
            form_inputs = {}
            for input_elem in main_form.find_all(["input", "select", "textarea"]):
                input_name = input_elem.get("name")
                if not input_name:
                    continue
                
                if input_elem.name == "select":
                    selected_option = input_elem.find("option", {"selected": True})
                    input_value = selected_option.get("value", "") if selected_option else ""
                elif input_elem.get("type") in ["checkbox", "radio"]:
                    input_value = input_elem.get("value", "") if input_elem.get("checked") else ""
                else:
                    input_value = input_elem.get("value", "")
                
                if input_name:
                    form_inputs[input_name] = input_value
            
            # Set our values
            form_inputs["_token"] = csrf_token["value"]
            # Keep original note value from form
            form_inputs["transaction_id"] = f"TRX-{wd_id}"
            form_inputs["transaction_time"] = datetime.now().strftime("%Y-%m-%d")
            form_inputs["transaction_by"] = "MD MILON 2.0"
            form_inputs["status"] = STATUS_SUCCESS
            
            # Submit form
            submission_url = f"{BASE_URL}/update-user-withdrawals/{wd_id}"
            resp = self.session.post(submission_url, data=form_inputs, allow_redirects=True)
            
            if resp.status_code in [200, 302]:
                self.log(f"Successfully updated withdrawal for ID: {wd_id}")
                return True
            else:
                self.log(f"Form submission failed. Status code: {resp.status_code}")
                return False
                
        except Exception as e:
            self.log(f"Error during form submission: {str(e)}")
            return False

    def start_processing(self):
        self.start_btn.config(state=tk.DISABLED)
        self.upload_btn.config(state=tk.DISABLED)
        self.progress.set(0)
        threading.Thread(target=self.process_withdrawals, daemon=True).start()

    def process_withdrawals(self):
        if not self.login():
            self.log("Failed to login. Exiting.")
            self.start_btn.config(state=tk.NORMAL)
            self.upload_btn.config(state=tk.NORMAL)
            return

        total = len(self.withdrawals)
        success_count = 0
        
        for idx, withdrawal in enumerate(self.withdrawals):
            wd_id = withdrawal["wd_id"]
            
            self.log(f"Processing withdrawal ID: {wd_id}")
            
            if self.complete_withdrawal(wd_id):
                success_count += 1
            
            self.progress.set((idx + 1) / total * 100)
            time.sleep(1)  # Small delay between requests

        self.log(f"Process completed. Success: {success_count}/{total}")
        self.start_btn.config(state=tk.NORMAL)
        self.upload_btn.config(state=tk.NORMAL)

    def log(self, message):
        self.log_area.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Format different types of messages
        if "Loaded" in message:
            formatted_message = f"\n{'='*50}\n📋 {message}\n{'='*50}\n"
        elif "login" in message.lower():
            formatted_message = f"🔐 [{timestamp}] {message}\n"
        elif "Processing" in message:
            formatted_message = f"\n{'='*50}\n🔄 [{timestamp}] {message}\n{'='*50}\n"
        elif "Accessing" in message:
            formatted_message = f"📡 [{timestamp}] {message}\n"
        elif "Successfully updated" in message:
            formatted_message = f"✅ [{timestamp}] {message}\n"
        elif "Process completed" in message:
            formatted_message = f"\n{'='*50}\n📊 [{timestamp}] {message}\n{'='*50}\n"
        else:
            formatted_message = f"ℹ️ [{timestamp}] {message}\n"
            
        self.log_area.insert(tk.END, formatted_message)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def show_import_window(self):
        ImportWindow(self.root, self.handle_imported_withdrawals)

    def handle_imported_withdrawals(self, withdrawals):
        self.withdrawals = withdrawals
        self.log(f"Loaded {len(self.withdrawals)} valid withdrawals.")
        self.start_btn.config(state=tk.NORMAL)

class ImportWindow:
    def __init__(self, parent, callback):
        self.window = tk.Toplevel(parent)
        self.window.title("Import Withdrawals")
        self.window.geometry("400x300")
        self.callback = callback
        
        # Create text area
        self.text_area = scrolledtext.ScrolledText(self.window, height=10, width=40)
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Create import button
        self.import_btn = tk.Button(self.window, text="Import Withdrawals", command=self.import_withdrawals)
        self.import_btn.pack(pady=10)
        
        # Add instruction label
        instruction = tk.Label(self.window, text="Enter withdrawal IDs (one per line)", fg="blue")
        instruction.pack(pady=5)

    def import_withdrawals(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter at least one withdrawal ID")
            return
            
        withdrawals = []
        for line in text.split('\n'):
            if not line.strip():
                continue
            wd_id = line.strip()
            withdrawals.append({
                'wd_id': wd_id
            })
        
        if not withdrawals:
            messagebox.showwarning("Warning", "No valid withdrawal IDs found")
            return
            
        self.callback(withdrawals)
        self.window.destroy()

if __name__ == "__main__":
    import tkinter.ttk as ttk
    root = tk.Tk()
    WithdrawalBotGUI(root)
    root.mainloop() 