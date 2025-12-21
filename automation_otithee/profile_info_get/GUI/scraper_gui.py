import sys
import os
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import datetime
import subprocess
import platform
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
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
# Use new config names for consistency
LOGIN_URL = config.ADMIN_LOGIN_URL
TARGET_URL = config.ADMIN_TARGET_URL
EMAIL_OR_MOBILE = config.ADMIN_EMAIL_OR_MOBILE
PASSWORD = config.ADMIN_PASSWORD

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
        self.import_btn = tk.Button(self.window, text="Direct Import Numbers", command=self.import_numbers)
        self.import_btn.pack(pady=10)
        
        # Add instruction label
        instruction = tk.Label(self.window, text="Enter phone numbers (one per line)\nNumbers will automatically be prefixed with '0' if missing", fg="blue")
        instruction.pack(pady=5)

    def import_numbers(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter at least one phone number")
            return
            
        # Split by newlines and clean up
        numbers = [num.strip() for num in text.split('\n') if num.strip()]
        # Process numbers: keep if starts with 0, add 0 if doesn't start with 0
        valid_numbers = []
        for num in numbers:
            # If number doesn't start with 0, add it
            if not num.startswith('0'):
                num = '0' + num
            # Validate the number
            if self.validate_phone(num):
                valid_numbers.append(num)
        
        if not valid_numbers:
            messagebox.showwarning("Warning", "No valid phone numbers found")
            return
            
        self.callback(valid_numbers)
        self.window.destroy()

    def validate_phone(self, phone):
        # Remove '0' prefix for validation if present
        phone_to_validate = phone[1:] if phone.startswith('0') else phone
        return bool(re.fullmatch(r'\d{8,15}', phone_to_validate))

class ScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Otithee Agent Scraper")
        self.root.geometry("900x750")
        self.root.minsize(800, 650)
        set_window_icon(self.root)
        self.file_path = None
        self.phone_numbers = []
        self.scraped_data = []
        self.error_numbers = []
        self.columns = [
            'Name', 'Phone', 'Rank', 'Created Time', 'Due Account',
            'Status (Active/Inactive)', 'Available Balance (TK)', 'User ID', 'Referer Phone',
            'Referer Name', 'Referer ID',
            'Withdrawal Id', 'Amount', 'After VAT/TAX', 'Payment Method', 'Status', 'Created At'
        ]
        self.create_widgets()

    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Instruction label
        instruction = tk.Label(main_frame, text="Upload an Excel file with a 'Phone Number' column or import numbers directly.", fg="blue")
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
        self.start_btn = tk.Button(bottom_frame, text="Start Scraping", command=self.start_scraping, state=tk.DISABLED)
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
            df = pd.read_excel(file_path, dtype={'Phone Number': str})
            if 'Phone Number' not in df.columns:
                messagebox.showerror("Error", "Excel file must have a 'Phone Number' column.")
                return
            self.phone_numbers = [str(p).strip().split('.')[0] for p in df['Phone Number'] if pd.notna(p)]
            valid_numbers = [p for p in self.phone_numbers if self.validate_phone(p)]
            self.phone_numbers = valid_numbers
            self.file_path = file_path
            self.log(f"Loaded {len(self.phone_numbers)} valid phone numbers.")
            self.start_btn.config(state=tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read Excel file: {e}")

    def validate_phone(self, phone):
        # Accepts 8-15 digit numbers, can be improved for your needs
        return bool(re.fullmatch(r'\d{8,15}', phone))

    def start_scraping(self):
        self.start_btn.config(state=tk.DISABLED)
        self.upload_btn.config(state=tk.DISABLED)
        self.progress.set(0)
        self.scraped_data = []
        self.error_numbers = []
        threading.Thread(target=self.scrape_all, daemon=True).start()

    def scrape_all(self):
        self.log("Starting scraping...")
        os.makedirs('results', exist_ok=True)
        session = requests.Session()
        try:
            login_page = session.get(LOGIN_URL)
            soup = BeautifulSoup(login_page.text, 'html.parser')
            csrf_token = soup.find('input', {'name': '_token'})['value']
            login_data = {
                'email': EMAIL_OR_MOBILE,
                'password': PASSWORD,
                '_token': csrf_token,
            }
            login_response = session.post(LOGIN_URL, data=login_data)
            if login_response.status_code == 200 and "dashboard" in login_response.text:
                self.log("Successfully logged in!")
                self.log("LOGIN URL " + LOGIN_URL)
                self.log("TARGET URL " + TARGET_URL)

            else:
                self.log("Login failed! Check credentials or CSRF token.")
                self.start_btn.config(state=tk.NORMAL)
                self.upload_btn.config(state=tk.NORMAL)
                return
        except Exception as e:
            self.log(f"Login error: {e}")
            self.start_btn.config(state=tk.NORMAL)
            self.upload_btn.config(state=tk.NORMAL)
            return

        total = len(self.phone_numbers)
        for idx, phone_number in enumerate(self.phone_numbers):
            try:
                data = self.extract_data(phone_number, session)
                if data:
                    self.scraped_data.append(data)
                    self.log(f"[{idx+1}/{total}] Success: {phone_number} | Name: {data.get('Name')} | Referer Phone: {data.get('Referer Phone')}")
                else:
                    # Only add to error_numbers, not to scraped_data
                    err_row = {'Phone Number': phone_number, 'Error': 'No data found'}
                    self.error_numbers.append(err_row)
                    self.log(f"[{idx+1}/{total}] Failed to scrape data for {phone_number}")
            except Exception as e:
                # Only add to error_numbers, not to scraped_data
                err_row = {'Phone Number': phone_number, 'Error': str(e)}
                self.error_numbers.append(err_row)
                self.log(f"[{idx+1}/{total}] Error: {phone_number} | {e}")
            self.progress.set((idx+1)/total*100)
        self.save_results()
        self.log("Scraping finished.")
        self.start_btn.config(state=tk.NORMAL)
        self.upload_btn.config(state=tk.NORMAL)

    def extract_data(self, phone_number, session):
        # Ensure phone_number starts with 0
        if not phone_number.startswith('0'):
            phone_number = '0' + phone_number
        url = f"{TARGET_URL}{phone_number}"
        response = session.get(url)
        if response.status_code != 200:
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main card body with profile information
        card_body = soup.find('div', class_='card-body')
        if card_body is None:
            return None
            
        # Extract name and phone from the h3 title
        h3 = card_body.find('h3', class_='card-title')
        if not h3:
            return None
            
        title_text = h3.get_text(" ", strip=True)
        # Parse name and phone from format like "MD SHAMSUL ALAM (01713010369)"
        if '(' in title_text and ')' in title_text:
            name = title_text.split('(')[0].strip()
            phone = title_text.split('(')[1].split(')')[0].strip()
        else:
            name = title_text
            phone = phone_number
            
        # Extract rank from badge
        rank = None
        badge = h3.find('span', class_='badge')
        if badge:
            # Get text and remove any nested elements (like edit icons)
            rank_text = badge.get_text(" ", strip=True)
            # Remove any remaining HTML tags and clean up
            rank = re.sub(r'\s+', ' ', rank_text).strip()
            # Remove edit icon text if present
            if 'mdi-pencil-box-outline' in str(badge) or 'mdi-pencil' in str(badge):
                # Remove the last word if it's just an icon
                rank = rank.split()[:-1] if len(rank.split()) > 1 else rank
                rank = ' '.join(rank) if isinstance(rank, list) else rank
            
        # Check for due account status - search for "Due Account" in any badge or text
        due_account = 'No'
        # Look for "Due Account" text anywhere in the card body
        card_body_text = card_body.get_text(" ", strip=True)
        if 'Due Account' in card_body_text:
            # Also check if there's a badge with Due Account
            due_account_badges = card_body.find_all('span', class_='badge')
            for badge in due_account_badges:
                if 'Due Account' in badge.get_text():
                    due_account = 'Yes'
                    break
            # If not found in badge, check in regular text
            if due_account == 'No' and 'Due Account' in card_body_text:
                # Check if it's mentioned as "Yes" or has a positive indicator
                due_account = 'Yes'
            
        # Extract created time
        created_time = None
        p_text = card_body.find('p', class_='card-text text-muted')
        if p_text:
            full_text = p_text.get_text(" ", strip=True)
            if "Account Created:" in full_text:
                # Extract text after "Account Created:" and before "|" or end of string
                created_part = full_text.split("Account Created:")[1]
                if "|" in created_part:
                    created_time = created_part.split("|")[0].strip()
                else:
                    created_time = created_part.strip()
                
        # Extract other information from the row structure
        available_balance = None
        user_id = None
        referer_id = None
        referer_phone = None
        referer_name = None
        
        # Find all row elements with col-4 and col-8 structure
        rows = card_body.find_all('div', class_='row mb-2')
        for row in rows:
            label_divs = row.find_all('div', class_=lambda x: x and 'col-4' in x and 'fw-bold' in x)
            value_divs = row.find_all('div', class_=lambda x: x and 'col-8' in x)
            
            for label, value in zip(label_divs, value_divs):
                label_text = label.get_text(strip=True)
                value_text = value.get_text(" ", strip=True)
                
                if "Avaliable Points:" in label_text or "Avaliable Balance:" in label_text:
                    # Extract balance amount, remove currency symbol and extra text
                    # Look for number with decimal points
                    balance_match = re.search(r'(\d+\.?\d*)', value_text)
                    if balance_match:
                        available_balance = balance_match.group(1)
                        
                elif "User ID:" in label_text:
                    # Extract user ID number (may be in tooltip container)
                    # Get all text and find the first number
                    user_id_match = re.search(r'(\d+)', value_text)
                    if user_id_match:
                        user_id = user_id_match.group(1)
                        
                elif "Referer:" in label_text and referer_phone is None:
                    # Extract referer information
                    # The format is: "01942756229 (Afia konok) ID: 2268"
                    # Look for phone number pattern (8+ digits, usually 11 digits)
                    phone_match = re.search(r'(\d{8,})', value_text)
                    if phone_match:
                        referer_phone = phone_match.group(1)
                        
                    # Extract referer name from parentheses (first parentheses group)
                    name_match = re.search(r'\(([^)]+)\)', value_text)
                    if name_match:
                        referer_name = name_match.group(1).strip()
                        
                    # Extract referer ID (look for "ID: " followed by digits)
                    id_match = re.search(r'ID:\s*(\d+)', value_text)
                    if id_match:
                        referer_id = id_match.group(1)
        
        # Extract Status (Active/Inactive) from profile info
        status_active = None
        # Look for a row with label 'Status:'
        for row in rows:
            label_divs = row.find_all('div', class_=lambda x: x and 'col-4' in x and 'fw-bold' in x)
            value_divs = row.find_all('div', class_=lambda x: x and 'col-8' in x)
            for label, value in zip(label_divs, value_divs):
                label_text = label.get_text(strip=True)
                value_text = value.get_text(" ", strip=True)
                if label_text == 'Status:':
                    # Try to extract 'Active' or 'Inactive' from the value
                    if 'Active' in value_text:
                        status_active = 'Active'
                    elif 'Inactive' in value_text:
                        status_active = 'Inactive'
        # Extract withdrawal info (always target latest row using table id and tr/td class/id)
        withdrawal_id = amount = after_vat_tax = payment_method = status = created_at = None
        withdrawal_table = soup.find('table', id='withdrawal_history_table')
        if withdrawal_table:
            # Find the first row with the class 'withdrawal_row' (latest withdrawal)
            first_row = withdrawal_table.find('tr', class_='withdrawal_row')
            if first_row:
                # Extract each cell by its class (id is optional)
                # Withdrawal ID - try by class first, then by id
                withdrawal_id_cell = first_row.find('td', class_='withdrawal_id')
                if not withdrawal_id_cell:
                    withdrawal_id_cell = first_row.find('td', id=lambda x: x and 'withdrawal_' in x)
                
                amount_cell = first_row.find('td', class_='withdrawal_amount')
                after_vat_tax_cell = first_row.find('td', class_='withdrawal_after_vat')
                payment_method_cell = first_row.find('td', class_='withdrawal_payment_method')
                status_cell = first_row.find('td', class_='withdrawal_status')
                created_at_cell = first_row.find('td', class_='withdrawal_created_at')

                if withdrawal_id_cell:
                    withdrawal_id = withdrawal_id_cell.get_text(strip=True)
                if amount_cell:
                    amount = amount_cell.get_text(strip=True)
                if after_vat_tax_cell:
                    after_vat_tax = after_vat_tax_cell.get_text(strip=True)
                if payment_method_cell:
                    payment_method = payment_method_cell.get_text(strip=True)
                if status_cell:
                    # Status might be in a badge, extract text from badge if present
                    badge_in_status = status_cell.find('span', class_='badge')
                    if badge_in_status:
                        status = badge_in_status.get_text(strip=True)
                    else:
                        status = status_cell.get_text(strip=True)
                if created_at_cell:
                    created_at = created_at_cell.get_text(strip=True)


        return {
            'Name': name,
            'Phone': phone,
            'Rank': rank,
            'Created Time': created_time,
            'Due Account': due_account,
            'Status (Active/Inactive)': status_active,
            'Available Balance (TK)': available_balance,
            'User ID': user_id,
            'Referer Phone': referer_phone,
            'Referer Name': referer_name,
            'Referer ID': referer_id,
            'Withdrawal Id': withdrawal_id,
            'Amount': amount,
            'After VAT/TAX': after_vat_tax,
            'Payment Method': payment_method,
            'Status': status,
            'Created At': created_at
        }

    def save_results(self):
        # Create filename with date and time: profiles_22-07-25_1430.xlsx
        current_date = datetime.datetime.now()
        date_str = current_date.strftime('%d-%m-%y')  # 22-07-25
        time_str = current_date.strftime('%H%M')      # 1430 (2:30 PM)
        
        filename_base = f"scrap_{date_str}_{time_str}"
        
        # Save successful scraped data
        if self.scraped_data:
            df_scraped = pd.DataFrame(self.scraped_data, columns=self.columns)
            output_file = os.path.join('results', f'{filename_base}.xlsx')
            df_scraped.to_excel(output_file, index=False)
            self.log(f"Scraped data saved to {output_file}")
        else:
            self.log("No successful data to save")
        
        # Save error numbers separately
        if self.error_numbers:
            df_errors = pd.DataFrame(self.error_numbers)
            error_file = os.path.join('results', f'errors_{date_str}_{time_str}.xlsx')
            df_errors.to_excel(error_file, index=False)
            self.log(f"Error phone numbers saved to {error_file}")
        
        # Auto open the folder containing the saved file
        try:
            if self.scraped_data:
                folder_path = os.path.abspath(os.path.dirname(output_file))
            elif self.error_numbers:
                folder_path = os.path.abspath(os.path.dirname(error_file))
            else:
                folder_path = os.path.abspath('results')
            
            # Cross-platform folder opening
            if platform.system() == 'Windows':
                os.startfile(folder_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.Popen(['open', folder_path])
            else:  # Linux and other Unix-like systems
                subprocess.Popen(['xdg-open', folder_path])
        except Exception as e:
            self.log(f"Could not open folder: {e}")

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

if __name__ == "__main__":
    import tkinter.ttk as ttk
    root = tk.Tk()
    ScraperGUI(root)
    root.mainloop() 