#!/usr/bin/env python3
"""
GUI for Number & Name Change automation tool.
Allows batch processing of agent number and name changes with Excel/CSV input/output.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import threading
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import config

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

class ChangeNumberGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Number & Name Change - Batch Processor")
        self.root.geometry("850x800")
        self.root.minsize(800, 700)
        set_window_icon(self.root)
        self.root.configure(bg="#f5f7fa")
        
        # Variables
        self.input_file_var = tk.StringVar()
        self.output_file_var = tk.StringVar()
        self.headless_var = tk.BooleanVar(value=config.HEADLESS_MODE)
        self.is_running = False
        self.driver = None
        
        # Create UI
        self.create_ui()
        
    def create_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#4a90e2", height=60)
        header_frame.pack(fill="x")
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="📝 Number & Name Change",
            font=("Segoe UI", 18, "bold"),
            bg="#4a90e2",
            fg="white",
            pady=15
        )
        title_label.pack()
        
        # Main container
        main_frame = tk.Frame(self.root, bg="#f5f7fa", padx=30, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Configuration section
        config_frame = tk.LabelFrame(
            main_frame,
            text="Configuration",
            font=("Segoe UI", 11, "bold"),
            bg="#f5f7fa",
            fg="#333",
            padx=15,
            pady=15
        )
        config_frame.pack(fill="x", pady=(0, 15))
        
        # Login URL
        tk.Label(config_frame, text="Login URL:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=5)
        login_url_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        login_url_entry.insert(0, config.ADMIN_LOGIN_URL)
        login_url_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        # Base URL
        tk.Label(config_frame, text="Base URL:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=5)
        base_url_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        base_url_entry.insert(0, config.ADMIN_BASE_URL)
        base_url_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        # Email/Mobile
        tk.Label(config_frame, text="Email/Mobile:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=5)
        email_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        email_entry.insert(0, config.ADMIN_EMAIL_OR_MOBILE)
        email_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        # Password
        tk.Label(config_frame, text="Password:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=3, column=0, sticky="w", pady=5)
        password_entry = tk.Entry(config_frame, width=50, show="*", font=("Segoe UI", 9))
        password_entry.insert(0, config.ADMIN_PASSWORD)
        password_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        
        config_frame.columnconfigure(1, weight=1)
        
        # File selection section
        file_frame = tk.LabelFrame(
            main_frame,
            text="File Selection",
            font=("Segoe UI", 11, "bold"),
            bg="#f5f7fa",
            fg="#333",
            padx=15,
            pady=15
        )
        file_frame.pack(fill="x", pady=(0, 15))
        
        # Input file (Excel or CSV)
        tk.Label(file_frame, text="Input File:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=5)
        tk.Label(file_frame, text="(Excel/CSV with: now, new, first_name, last_name)", bg="#f5f7fa", font=("Segoe UI", 8), fg="#666").grid(row=0, column=1, sticky="w", padx=10)
        input_entry = tk.Entry(file_frame, textvariable=self.input_file_var, width=40, font=("Segoe UI", 9))
        input_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        tk.Button(
            file_frame,
            text="Browse...",
            command=lambda: self.browse_file(self.input_file_var, "Data files", [("Excel files", "*.xlsx"), ("CSV files", "*.csv"), ("All files", "*.*")]),
            bg="#4a90e2",
            fg="white",
            font=("Segoe UI", 9),
            padx=15,
            pady=5,
            cursor="hand2"
        ).grid(row=1, column=2, pady=5)
        
        # Output CSV
        tk.Label(file_frame, text="Output CSV:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=5)
        output_entry = tk.Entry(file_frame, textvariable=self.output_file_var, width=40, font=("Segoe UI", 9))
        output_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        tk.Button(
            file_frame,
            text="Browse...",
            command=lambda: self.browse_save_file(self.output_file_var, "CSV files", [("CSV files", "*.csv"), ("All files", "*.*")]),
            bg="#4a90e2",
            fg="white",
            font=("Segoe UI", 9),
            padx=15,
            pady=5,
            cursor="hand2"
        ).grid(row=3, column=2, pady=5)
        
        file_frame.columnconfigure(0, weight=1)
        
        # Options
        options_frame = tk.Frame(main_frame, bg="#f5f7fa")
        options_frame.pack(fill="x", pady=(0, 15))
        
        headless_check = tk.Checkbutton(
            options_frame,
            text="Run in headless mode (no browser window)",
            variable=self.headless_var,
            bg="#f5f7fa",
            font=("Segoe UI", 10)
        )
        headless_check.pack(anchor="w")
        
        # Store entries for access in worker
        self.login_url_entry = login_url_entry
        self.base_url_entry = base_url_entry
        self.email_entry = email_entry
        self.password_entry = password_entry
        
        # Progress section
        progress_frame = tk.LabelFrame(
            main_frame,
            text="Progress",
            font=("Segoe UI", 11, "bold"),
            bg="#f5f7fa",
            fg="#333",
            padx=15,
            pady=15
        )
        progress_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = tk.Label(
            progress_frame,
            textvariable=self.progress_var,
            bg="#f5f7fa",
            font=("Segoe UI", 10),
            anchor="w"
        )
        self.progress_label.pack(fill="x", pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=(0, 10))
        
        # Log area
        log_frame = tk.Frame(progress_frame, bg="white", relief="sunken", borderwidth=1)
        log_frame.pack(fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(
            log_frame,
            height=8,
            font=("Consolas", 9),
            bg="white",
            fg="#333",
            yscrollcommand=scrollbar.set,
            wrap="word"
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#f5f7fa")
        button_frame.pack(fill="x")
        
        self.start_btn = tk.Button(
            button_frame,
            text="🚀 Start Processing",
            command=self.start_processing,
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            cursor="hand2"
        )
        self.start_btn.pack(side="left", padx=(0, 10))
        
        self.stop_btn = tk.Button(
            button_frame,
            text="⏹ Stop",
            command=self.stop_processing,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=10,
            cursor="hand2",
            state="disabled"
        )
        self.stop_btn.pack(side="left")
        
    def browse_file(self, var, filetype, filetypes):
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = filedialog.askopenfilename(
            title=f"Select {filetype}",
            initialdir=current_dir,
            filetypes=filetypes
        )
        if filename:
            var.set(filename)
    
    def browse_save_file(self, var, filetype, filetypes):
        # Get current directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = filedialog.asksaveasfilename(
            title=f"Save {filetype}",
            initialdir=current_dir,
            defaultextension=".csv",
            filetypes=filetypes
        )
        if filename:
            var.set(filename)
    
    def log(self, message):
        """Add message to log area."""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()
    
    def setup_driver(self):
        """Setup Selenium WebDriver."""
        options = Options()
        if self.headless_var.get():
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    
    def process_worker(self):
        """Worker thread for processing."""
        try:
            input_file = self.input_file_var.get().strip()
            output_file = self.output_file_var.get().strip()
            login_url = self.login_url_entry.get().strip()
            base_url = self.base_url_entry.get().strip()
            email = self.email_entry.get().strip()
            password = self.password_entry.get().strip()
            
            if not input_file or not os.path.exists(input_file):
                self.root.after(0, lambda: messagebox.showerror("Error", "Please select a valid input file."))
                self.root.after(0, self.reset_ui)
                return
            
            if not output_file:
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                output_file = os.path.join(os.path.dirname(input_file), f"{base_name}_results.csv")
                self.output_file_var.set(output_file)
            
            if not email or not password:
                self.root.after(0, lambda: messagebox.showerror("Error", "Please enter email/mobile and password."))
                self.root.after(0, self.reset_ui)
                return
            
            target_url = f"{base_url}/agent-ranking/agent/edit/"
            
            self.root.after(0, lambda: self.log(f"Reading input file: {input_file}"))
            
            # Read file (Excel or CSV)
            try:
                if input_file.endswith('.xlsx'):
                    data = pd.read_excel(input_file, engine='openpyxl')
                else:
                    data = pd.read_csv(input_file, encoding="utf-8")
            except UnicodeDecodeError:
                data = pd.read_csv(input_file, encoding="cp1252")
            
            # Validate columns
            required_cols = ["now", "new", "first_name", "last_name"]
            for col in required_cols:
                if col not in data.columns:
                    self.root.after(0, lambda c=col: messagebox.showerror("Error", f"CSV must contain '{c}' column."))
                    self.root.after(0, self.reset_ui)
                    return
            
            self.root.after(0, lambda: self.log(f"Found {len(data)} records to process"))
            self.root.after(0, lambda: self.log("Setting up browser..."))
            
            self.driver = self.setup_driver()
            wait = WebDriverWait(self.driver, config.PAGE_WAIT)
            
            # Login
            self.root.after(0, lambda: self.log("Logging in..."))
            self.driver.get(login_url)
            time.sleep(2)
            
            self.driver.find_element(By.NAME, "email").send_keys(email)
            self.driver.find_element(By.NAME, "password").send_keys(password)
            
            login_button = self.driver.find_element(By.XPATH, "//button[contains(@class, 'auth-form-btn')]")
            login_button.click()
            time.sleep(3)
            
            if self.driver.current_url == login_url:
                raise RuntimeError("Login failed! Check credentials or selectors.")
            
            self.root.after(0, lambda: self.log("Login successful!"))
            
            results = []
            total = len(data)
            
            for idx, row in data.iterrows():
                if not self.is_running:
                    self.root.after(0, lambda: self.log("Processing stopped by user"))
                    break
                
                now_number = str(row["now"]).strip()
                new_number = str(row["new"]).strip()
                first_name = str(row["first_name"]).strip()
                last_name = str(row["last_name"]).strip()
                
                # Ensure phone numbers start with 0
                if not now_number.startswith("0"):
                    now_number = "0" + now_number
                if not new_number.startswith("0"):
                    new_number = "0" + new_number
                
                self.root.after(0, lambda n=now_number, i=idx+1, t=total: self.progress_var.set(f"Processing {i}/{t}: {n}"))
                
                url = f"{target_url}{now_number}"
                self.driver.get(url)
                time.sleep(2)
                
                try:
                    # Enable and fill username, first_name, last_name
                    for field_id in ["username", "first_name", "last_name"]:
                        checkbox = self.driver.find_element(By.ID, f"edit_{field_id}")
                        if not checkbox.is_selected():
                            checkbox.click()
                        input_field = self.driver.find_element(By.ID, field_id)
                        input_field.clear()
                        if field_id == "username":
                            input_field.send_keys(new_number)
                        elif field_id == "first_name":
                            input_field.send_keys(first_name)
                        elif field_id == "last_name":
                            input_field.send_keys(last_name)
                    
                    # Wait until jQuery-enabled submit button is clickable
                    submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn.btn-primary")))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
                    self.driver.execute_script("arguments[0].click();", submit_button)
                    time.sleep(2)
                    
                    results.append({"now": now_number, "new": new_number, "status": "Success"})
                    self.root.after(0, lambda n=now_number: self.log(f"✅ Updated {n} successfully."))
                    
                except Exception as e:
                    error_msg = str(e)
                    results.append({"now": now_number, "new": new_number, "status": f"Failed: {error_msg}"})
                    self.root.after(0, lambda n=now_number, e=error_msg: self.log(f"❌ Failed to update {n}: {e}"))
            
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            pd.DataFrame(results).to_csv(output_file, index=False, encoding="utf-8-sig")
            
            self.root.after(0, lambda: self.log(f"\n✅ Processing complete! Results saved to: {output_file}"))
            self.root.after(0, lambda: messagebox.showinfo("Success", f"Processing complete!\n\nResults saved to:\n{output_file}"))
            self.root.after(0, self.reset_ui)
            
        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n\n{traceback.format_exc()}"
            self.root.after(0, lambda: self.log(f"\n❌ {error_msg}"))
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.root.after(0, self.reset_ui)
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
    
    def start_processing(self):
        """Start the processing in a background thread."""
        if self.is_running:
            return
        
        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress_bar.start(10)
        self.log_text.delete("1.0", "end")
        self.log("🚀 Starting processing...")
        
        threading.Thread(target=self.process_worker, daemon=True).start()
    
    def stop_processing(self):
        """Stop the processing."""
        self.is_running = False
        self.log("⏹ Stopping processing...")
    
    def reset_ui(self):
        """Reset UI to initial state."""
        self.is_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.progress_bar.stop()
        self.progress_var.set("Ready")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChangeNumberGUI(root)
    root.mainloop()

