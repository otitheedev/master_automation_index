import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
from pathlib import Path

# Add project root to path
current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from icon_utils import set_window_icon

# Import the download bot functions
sys.path.insert(0, current_dir)
try:
    from downloadBot import create_driver, login, collect_invoice_links, download_invoices
except ImportError as e:
    # Fallback if import fails
    print(f"Warning: Could not import from downloadBot: {e}")
    def create_driver():
        raise NotImplementedError("downloadBot module not available")
    def login(*args):
        raise NotImplementedError("downloadBot module not available")
    def collect_invoice_links(*args):
        raise NotImplementedError("downloadBot module not available")
    def download_invoices(*args):
        raise NotImplementedError("downloadBot module not available")

DOWNLOAD_DIR = str(Path(__file__).resolve().parent / "downloads")


class DownloadBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Download PDF Bot (ACC)")
        self.root.geometry("800x850")
        self.root.minsize(700, 750)
        
        # Set window icon
        set_window_icon(self.root)
        
        self.root.configure(bg="#f5f7fa")
        
        self.driver = None
        self.is_running = False
        
        # Credential variables
        self.username_var = tk.StringVar(value="needyamin@otithee.com")
        self.password_var = tk.StringVar(value="*#r@@t2025#")
        
        self.create_widgets()
    
    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#4a90e2", height=80)
        header_frame.pack(fill='x', padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(
            header_frame,
            text="📥 Download PDF Bot (ACC)",
            font=("Segoe UI", 20, "bold"),
            bg="#4a90e2",
            fg="white"
        )
        title_label.pack(pady=20)
        
        # Main container
        main_frame = tk.Frame(self.root, bg="#f5f7fa")
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Info section
        info_frame = tk.Frame(main_frame, bg="white", relief="flat", bd=1, highlightthickness=1, highlightbackground="#ddd")
        info_frame.pack(fill='x', pady=(0, 15))
        
        info_text = tk.Label(
            info_frame,
            text=f"Downloads will be saved to:\n{DOWNLOAD_DIR}",
            font=("Segoe UI", 10),
            bg="white",
            fg="#666",
            justify="left",
            padx=15,
            pady=10
        )
        info_text.pack(anchor='w')
        
        # Credentials section
        cred_frame = tk.Frame(main_frame, bg="white", relief="flat", bd=1, highlightthickness=1, highlightbackground="#ddd")
        cred_frame.pack(fill='x', pady=(0, 15))
        
        cred_title = tk.Label(
            cred_frame,
            text="Login Credentials",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#333",
            padx=15,
            pady=(10, 5)
        )
        cred_title.pack(anchor='w')
        
        # Username field
        username_frame = tk.Frame(cred_frame, bg="white")
        username_frame.pack(fill='x', padx=15, pady=(0, 8))
        
        tk.Label(
            username_frame,
            text="Username/Email:",
            font=("Segoe UI", 10),
            bg="white",
            fg="#666",
            width=15,
            anchor='w'
        ).pack(side='left')
        
        username_entry = tk.Entry(
            username_frame,
            textvariable=self.username_var,
            font=("Segoe UI", 10),
            width=40,
            relief="solid",
            bd=1
        )
        username_entry.pack(side='left', fill='x', expand=True, padx=(10, 0))
        
        # Password field
        password_frame = tk.Frame(cred_frame, bg="white")
        password_frame.pack(fill='x', padx=15, pady=(0, 10))
        
        tk.Label(
            password_frame,
            text="Password:",
            font=("Segoe UI", 10),
            bg="white",
            fg="#666",
            width=15,
            anchor='w'
        ).pack(side='left')
        
        password_entry = tk.Entry(
            password_frame,
            textvariable=self.password_var,
            font=("Segoe UI", 10),
            width=40,
            show="*",
            relief="solid",
            bd=1
        )
        password_entry.pack(side='left', fill='x', expand=True, padx=(10, 0))
        
        # Log area
        log_label = tk.Label(
            main_frame,
            text="Activity Log:",
            font=("Segoe UI", 11, "bold"),
            bg="#f5f7fa",
            fg="#333"
        )
        log_label.pack(anchor='w', pady=(0, 5))
        
        log_frame = tk.Frame(main_frame, bg="white", relief="flat", bd=1, highlightthickness=1, highlightbackground="#ddd")
        log_frame.pack(fill='both', expand=True, pady=(0, 15))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            wrap=tk.WORD,
            padx=10,
            pady=10
        )
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.log_text.configure(state='disabled')
        
        # Button frame
        button_frame = tk.Frame(main_frame, bg="#f5f7fa")
        button_frame.pack(fill='x')
        
        self.start_button = tk.Button(
            button_frame,
            text="▶ Start Download",
            font=("Segoe UI", 11, "bold"),
            bg="#28a745",
            fg="white",
            padx=20,
            pady=10,
            command=self.start_download,
            cursor="hand2"
        )
        self.start_button.pack(side='left', padx=(0, 10))
        
        self.stop_button = tk.Button(
            button_frame,
            text="⏹ Stop",
            font=("Segoe UI", 11),
            bg="#dc3545",
            fg="white",
            padx=20,
            pady=10,
            command=self.stop_download,
            cursor="hand2",
            state='disabled'
        )
        self.stop_button.pack(side='left')
        
        self.close_button = tk.Button(
            button_frame,
            text="Close",
            font=("Segoe UI", 11),
            bg="#6c757d",
            fg="white",
            padx=20,
            pady=10,
            command=self.root.destroy,
            cursor="hand2"
        )
        self.close_button.pack(side='right')
    
    def log(self, message):
        """Thread-safe logging"""
        def _log():
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        
        self.root.after(0, _log)
    
    def start_download(self):
        if self.is_running:
            return
        
        self.is_running = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
        # Clear log
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
        # Run in background thread
        thread = threading.Thread(target=self.run_download, daemon=True)
        thread.start()
    
    def stop_download(self):
        self.is_running = False
        self.log("Stopping download process...")
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
    
    def run_download(self):
        import io
        import contextlib
        
        # Redirect stdout to capture print statements
        class LogRedirect:
            def __init__(self, log_func):
                self.log_func = log_func
                self.buffer = io.StringIO()
            
            def write(self, text):
                if text.strip():
                    self.log_func(text.strip())
            
            def flush(self):
                pass
        
        log_redirect = LogRedirect(self.log)
        old_stdout = sys.stdout
        
        try:
            sys.stdout = log_redirect
            
            self.log(f"Downloads will be saved to: {DOWNLOAD_DIR}")
            self.log("Creating browser driver...")
            self.driver = create_driver()
            
            if not self.is_running:
                return
            
            self.log("Logging in...")
            username = self.username_var.get().strip()
            password = self.password_var.get().strip()
            if not username or not password:
                self.log("Error: Username and password are required.")
                self.root.after(0, lambda: messagebox.showerror("Error", "Please enter username and password."))
                return
            login(self.driver, username=username, password=password)
            
            if not self.is_running:
                return
            
            self.log("Collecting invoice links...")
            hrefs = collect_invoice_links(self.driver)
            
            if not hrefs:
                self.log("No invoice links found on the page.")
                self.root.after(0, lambda: messagebox.showwarning("No Links", "No invoice links found on the page."))
                return
            
            if not self.is_running:
                return
            
            self.log(f"Found {len(hrefs)} invoice links.")
            download_invoices(self.driver, hrefs)
            
            if self.is_running:
                self.log("All invoice downloads triggered.")
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Download process completed!\n\n{len(hrefs)} invoices downloaded to:\n{DOWNLOAD_DIR}"))
        except Exception as e:
            self.log(f"Error: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred:\n{str(e)}"))
        finally:
            sys.stdout = old_stdout
            if self.driver:
                try:
                    self.driver.quit()
                    self.log("Browser closed.")
                except:
                    pass
            self.is_running = False
            self.root.after(0, lambda: self.start_button.config(state='normal'))
            self.root.after(0, lambda: self.stop_button.config(state='disabled'))

if __name__ == "__main__":
    root = tk.Tk()
    app = DownloadBotGUI(root)
    root.mainloop()

