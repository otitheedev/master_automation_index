#!/usr/bin/env python3
"""
GUI for Change Referer Name automation tool.
Allows batch processing of referer name changes with CSV input/output.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# Add parent directory to path to import config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
import config

# Shared settings DB for remembering credentials across tools
try:
    from settings_db import get_setting, set_setting
except Exception:  # Fallback no-op if settings_db is not available
    def get_setting(key, default=None):
        return default

    def set_setting(key, value):
        pass

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

class ChangeRefererGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Change Referer Name - Batch Processor")
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
            text="🔄 Change Referer Name",
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
        
        # Load remembered values from shared settings DB (fallback to config defaults)
        saved_login_url = get_setting("otithee_accounting_login_url", config.ACCOUNTING_LOGIN_URL)
        saved_change_url = get_setting("otithee_accounting_change_referer_url", config.ACCOUNTING_CHANGE_REFERER_URL)
        saved_username = get_setting("otithee_accounting_username", config.ACCOUNTING_USERNAME)
        saved_password = get_setting("otithee_accounting_password", config.ACCOUNTING_PASSWORD)

        # Login URL
        tk.Label(config_frame, text="Login URL:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=5)
        login_url_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        login_url_entry.insert(0, saved_login_url)
        login_url_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        # Change Referer URL
        tk.Label(config_frame, text="Change Referer URL:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=5)
        referer_url_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        referer_url_entry.insert(0, saved_change_url)
        referer_url_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        # Username
        tk.Label(config_frame, text="Username:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=5)
        username_entry = tk.Entry(config_frame, width=50, font=("Segoe UI", 9))
        username_entry.insert(0, saved_username)
        username_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        # Password
        tk.Label(config_frame, text="Password:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=3, column=0, sticky="w", pady=5)
        password_entry = tk.Entry(config_frame, width=50, show="*", font=("Segoe UI", 9))
        password_entry.insert(0, saved_password)
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
        
        # Input CSV
        tk.Label(file_frame, text="Input CSV:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=5)
        input_entry = tk.Entry(file_frame, textvariable=self.input_file_var, width=40, font=("Segoe UI", 9))
        input_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        tk.Button(
            file_frame,
            text="Browse...",
            command=lambda: self.browse_file(self.input_file_var, "CSV files", [("CSV files", "*.csv"), ("All files", "*.*")]),
            bg="#4a90e2",
            fg="white",
            font=("Segoe UI", 9),
            padx=15,
            pady=5,
            cursor="hand2"
        ).grid(row=0, column=2, pady=5)
        
        # Output CSV
        tk.Label(file_frame, text="Output CSV:", bg="#f5f7fa", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=5)
        output_entry = tk.Entry(file_frame, textvariable=self.output_file_var, width=40, font=("Segoe UI", 9))
        output_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
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
        ).grid(row=1, column=2, pady=5)
        
        file_frame.columnconfigure(1, weight=1)
        
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
        self.referer_url_entry = referer_url_entry
        self.username_entry = username_entry
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
        opts = Options()
        if self.headless_var.get():
            opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.set_window_size(*config.BROWSER_WINDOW_SIZE)
        return driver
    
    def login(self, driver, login_url, username, password):
        """Login to the system."""
        wait = WebDriverWait(driver, config.PAGE_WAIT)
        driver.get(login_url)
        
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
        
        try:
            pwd_elem = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
        except:
            raise RuntimeError("Password input not found. Update selector.")
        
        user_elem.clear()
        user_elem.send_keys(username)
        pwd_elem.clear()
        pwd_elem.send_keys(password)
        
        try:
            submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"], button')))
            driver.execute_script("arguments[0].click();", submit_btn)
        except TimeoutException:
            try:
                pwd_elem.submit()
            except Exception:
                pass
        
        try:
            wait.until(lambda d: d.current_url != login_url)
        except TimeoutException:
            try:
                WebDriverWait(driver, config.PAGE_WAIT).until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
            except TimeoutException:
                raise RuntimeError("Login appears to have failed or took too long.")
    
    def submit_one(self, driver, entrepreneur_num, referer_num, change_referer_url):
        """Submit one referer change."""
        short_wait = WebDriverWait(driver, config.SHORT_WAIT)
        wait = WebDriverWait(driver, config.POPULATE_WAIT)
        
        driver.get(change_referer_url)
        
        wait.until(EC.presence_of_element_located((By.ID, "entrepreneurNumber")))
        ent = driver.find_element(By.ID, "entrepreneurNumber")
        ref = driver.find_element(By.ID, "entrepreneurReferer")
        
        entrepreneur_num = "0" + str(entrepreneur_num).lstrip("0")
        referer_num = "0" + str(referer_num).lstrip("0")
        
        ent.clear()
        ent.send_keys(entrepreneur_num)
        
        try:
            wait.until(lambda d: len(d.find_element(By.ID, "entrepreneurNumber").get_attribute("value") or "") >= 10)
        except TimeoutException:
            pass
        
        loader_loc = (By.ID, "loadingIndicator")
        populated = False
        
        try:
            short_wait.until(EC.visibility_of_element_located(loader_loc))
            wait.until(EC.invisibility_of_element_located(loader_loc))
            populated = True
        except TimeoutException:
            try:
                wait.until(
                    lambda d: (
                        (d.find_elements(By.ID, "entrepreneurReferer") and (d.find_element(By.ID, "entrepreneurReferer").get_attribute("value") or "").strip() != "")
                        or (d.find_elements(By.ID, "entrepreneurName") and (d.find_element(By.ID, "entrepreneurName").get_attribute("value") or "").strip() != "")
                    )
                )
                populated = True
            except TimeoutException:
                try:
                    wait.until(EC.invisibility_of_element_located(loader_loc))
                    populated = True
                except TimeoutException:
                    return False, f"Timeout waiting for AJAX population after entering entrepreneurNumber {entrepreneur_num}"
        
        try:
            wait.until(EC.presence_of_element_located((By.ID, "entrepreneurReferer")))
            wait.until(EC.element_to_be_clickable((By.ID, "entrepreneurReferer")))
        except TimeoutException:
            return False, f"Timeout waiting for entrepreneurReferer to become ready for {entrepreneur_num}"
        
        ref = driver.find_element(By.ID, "entrepreneurReferer")
        ref.clear()
        ref.send_keys(referer_num)
        
        try:
            submit_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "form#entrepreneurForm button[type='submit'], form#entrepreneurForm button")
            ))
        except TimeoutException:
            return False, "Timeout waiting for submit button to become clickable"
        
        driver.execute_script("arguments[0].click();", submit_btn)
        
        try:
            wait.until(
                lambda d: (
                    (d.find_elements(By.ID, "outputResponse") and (d.find_element(By.ID, "outputResponse").get_attribute("value") or "").strip() != "")
                    or any(el.is_displayed() and (el.text or "").strip() for el in d.find_elements(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success"))
                )
            )
        except TimeoutException:
            return False, "Timeout waiting for response after submit"
        
        if driver.find_elements(By.ID, "outputResponse"):
            out_val = (driver.find_element(By.ID, "outputResponse").get_attribute("value") or "").strip()
            if out_val:
                return True, out_val
        
        flashes = driver.find_elements(By.CSS_SELECTOR, ".alert, .toast, .text-danger, .text-success")
        for f in flashes:
            if f.is_displayed() and (f.text or "").strip():
                return True, f.text.strip()[:1000]
        
        return True, "Submitted — no textual response captured"
    
    def process_worker(self):
        """Worker thread for processing."""
        try:
            input_file = self.input_file_var.get().strip()
            output_file = self.output_file_var.get().strip()
            login_url = self.login_url_entry.get().strip()
            change_referer_url = self.referer_url_entry.get().strip()
            username = self.username_entry.get().strip()
            password = self.password_entry.get().strip()
            
            if not input_file or not os.path.exists(input_file):
                self.root.after(0, lambda: messagebox.showerror("Error", "Please select a valid input CSV file."))
                self.root.after(0, self.reset_ui)
                return
            
            if not output_file:
                output_file = os.path.join(os.path.dirname(input_file), "results.csv")
                self.output_file_var.set(output_file)
            
            if not username or not password:
                self.root.after(0, lambda: messagebox.showerror("Error", "Please enter username and password."))
                self.root.after(0, self.reset_ui)
                return

            # Remember latest credentials/URLs in shared settings DB (best-effort)
            try:
                set_setting("otithee_accounting_login_url", login_url)
                set_setting("otithee_accounting_change_referer_url", change_referer_url)
                set_setting("otithee_accounting_username", username)
                # Store password as-is; DB is local and already used for other credentials.
                set_setting("otithee_accounting_password", password)
            except Exception:
                pass
            
            self.root.after(0, lambda: self.log(f"Reading input file: {input_file}"))
            df = pd.read_csv(input_file, dtype=str).fillna("")
            
            if not {"entrepreneurNumber", "refererNumber"}.issubset(df.columns):
                self.root.after(0, lambda: messagebox.showerror("Error", "CSV must contain columns: entrepreneurNumber, refererNumber"))
                self.root.after(0, self.reset_ui)
                return
            
            self.root.after(0, lambda: self.log(f"Found {len(df)} records to process"))
            self.root.after(0, lambda: self.log("Setting up browser..."))
            
            self.driver = self.setup_driver()
            
            self.root.after(0, lambda: self.log("Logging in..."))
            self.login(self.driver, login_url, username, password)
            self.root.after(0, lambda: self.log("Login successful!"))
            
            results = []
            total = len(df)
            
            for idx, row in df.iterrows():
                if not self.is_running:
                    self.root.after(0, lambda: self.log("Processing stopped by user"))
                    break
                
                ent = row['entrepreneurNumber']
                ref = row['refererNumber']
                
                self.root.after(0, lambda e=ent, r=ref, i=idx+1, t=total: self.progress_var.set(f"Processing {i}/{t}: {e} -> {r}"))
                
                try:
                    ok, resp = self.submit_one(self.driver, ent, ref, change_referer_url)
                    status = "ok" if ok else "failed"
                    self.root.after(0, lambda e=ent, r=ref, s=status: self.log(f"[{s.upper()}] {e} -> {r}"))
                except Exception as e:
                    status = "error"
                    resp = str(e)
                    self.root.after(0, lambda e=ent, err=str(e): self.log(f"[ERROR] {e}: {err}"))
                
                results.append({
                    "entrepreneurNumber": "0" + str(ent).lstrip("0"),
                    "refererNumber": "0" + str(ref).lstrip("0"),
                    "status": status,
                    "response": resp
                })
            
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
    app = ChangeRefererGUI(root)
    root.mainloop()

