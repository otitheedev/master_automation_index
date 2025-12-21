import os
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import subprocess
import importlib.util
from datetime import datetime
from PIL import Image, ImageTk
import sv_ttk
import json
import traceback

# Add project root to path for icon_utils
try:
    # Get absolute path of current file
    current_file = os.path.abspath(__file__)
    # Get directory containing this file (automation_otithee/)
    current_dir = os.path.dirname(current_file)
    # Go up one level to project root
    project_root = os.path.dirname(current_dir)
    # Add to path if not already there
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from icon_utils import set_window_icon
except ImportError:
    # Fallback if icon_utils not found - create a no-op function
    def set_window_icon(window):
        try:
            # Try to find icon.ico in project root
            current_file = os.path.abspath(__file__)
            current_dir = os.path.dirname(current_file)
            project_root = os.path.dirname(current_dir)
            icon_path = os.path.join(project_root, "icon.ico")
            if os.path.exists(icon_path):
                window.iconbitmap(icon_path)
        except:
            pass  # Silently fail if icon can't be loaded

class ModernButton(tk.Button):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.default_bg = kwargs.get('bg', '#4a90e2')
        self.hover_bg = '#357abd'
        self.active_bg = '#2c6aa0'
        
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<Button-1>', self.on_click)
        
    def on_enter(self, e):
        self['bg'] = self.hover_bg
        
    def on_leave(self, e):
        self['bg'] = self.default_bg
        
    def on_click(self, e):
        self['bg'] = self.active_bg
        self.after(100, lambda: self.configure(bg=self.default_bg))

class ToolCard(tk.Frame):
    def __init__(self, parent, title, description, command, icon=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg=parent['bg'], padx=15, pady=15, cursor='hand2')
        
        # Card container with shadow effect
        self.card_frame = tk.Frame(
            self,
            bg='white',
            highlightthickness=1,
            highlightbackground='#e0e0e0',
            cursor='hand2'
        )
        self.card_frame.pack(fill='both', expand=True)
        
        # Icon (if provided)
        if icon:
            self.icon_label = tk.Label(
                self.card_frame,
                text=icon,
                font=('Segoe UI', 24),
                bg='white',
                fg='#4a90e2'
            )
            self.icon_label.pack(pady=(15, 5))
        
        # Title
        self.title_label = tk.Label(
            self.card_frame,
            text=title,
            font=('Segoe UI', 14, 'bold'),
            bg='white',
            fg='#333333'
        )
        self.title_label.pack(pady=(0, 5))
        
        # Description
        self.desc_label = tk.Label(
            self.card_frame,
            text=description,
            font=('Segoe UI', 10),
            bg='white',
            fg='#666666',
            wraplength=220,
            justify='center'
        )
        self.desc_label.pack(pady=(0, 15))
        
        # Store the command for card click
        self.command = command
        
        # Add hover effect to entire card
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        self.bind('<Button-1>', self.on_card_click)
        
        # Make the card frame clickable too
        self.card_frame.bind('<Enter>', self.on_enter)
        self.card_frame.bind('<Leave>', self.on_leave)
        self.card_frame.bind('<Button-1>', self.on_card_click)
        
        # Make all child widgets clickable
        for child in self.card_frame.winfo_children():
            child.bind('<Button-1>', self.on_card_click)
            child.bind('<Enter>', self.on_enter)
            child.bind('<Leave>', self.on_leave)
        
    def on_enter(self, e):
        self.card_frame.configure(highlightbackground='#4a90e2', highlightthickness=2)
        
    def on_leave(self, e):
        self.card_frame.configure(highlightbackground='#e0e0e0', highlightthickness=1)
        
    def on_card_click(self, e):
        """Handle card click to launch the tool"""
        if self.command:
            self.command()

class IndexGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Otithee Automation Suite")
        self.root.geometry("1100x1000")
        self.root.minsize(900, 850)
        
        # Set window icon
        set_window_icon(self.root)
        
        # Get the base directory of this script (for resolving relative paths)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Set theme colors
        self.bg_color = "#f8f9fa"
        self.accent_color = "#4a90e2"
        self.text_color = "#333333"
        
        # Configure root window
        self.root.configure(bg=self.bg_color)
        
        # Apply Sun Valley theme
        sv_ttk.set_theme("light")
        
        # Create main frame with responsive padding
        self.main_frame = tk.Frame(self.root, bg=self.bg_color)
        self.main_frame.pack(expand=True, fill='both', padx=40, pady=40)
        
        # Create header
        self.create_header()
        
        # Create tools section
        self.create_tools_section()
        
        # Create status bar
        self.create_status_bar()
        
        # Bind window resize event
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Store original window size
        self.original_width = 1100
        self.original_height = 1000

    def create_header(self):
        header_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        header_frame.pack(fill='x', pady=(0, 30))
        
        # Logo/Title container
        title_container = tk.Frame(header_frame, bg=self.bg_color)
        title_container.pack(side='left')
        
        # Title with gradient effect
        title_label = tk.Label(
            title_container,
            text="Otithee",
            font=("Segoe UI", 32, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title_label.pack(side='left')
        
        subtitle_label = tk.Label(
            title_container,
            text="Automation Suite",
            font=("Segoe UI", 32, "bold"),
            bg=self.bg_color,
            fg=self.text_color
        )
        subtitle_label.pack(side='left', padx=(5, 0))
        
        # Version and status
        version_label = tk.Label(
            header_frame,
            text="v4.0.0",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg='#666666'
        )
        version_label.pack(side='right', pady=(0, 5))
        
        status_label = tk.Label(
            header_frame,
            text="All Systems Operational",
            font=("Segoe UI", 10),
            bg=self.bg_color,
            fg='#28a745'
        )
        status_label.pack(side='right', padx=(0, 20))

    def create_tools_section(self):
        tools_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        tools_frame.pack(expand=True, fill='both')
        
        # Section title
        section_label = tk.Label(
            tools_frame,
            text="Available Tools",
            font=("Segoe UI", 16, "bold"),
            bg=self.bg_color,
            fg=self.text_color
        )
        section_label.pack(anchor='w', pady=(0, 20))
        
        # Tools grid with responsive layout
        tools_grid = tk.Frame(tools_frame, bg=self.bg_color)
        tools_grid.pack(expand=True, fill='both')
        
        # Configure grid for 3x2 layout (3 rows, 2 columns)
        tools_grid.grid_columnconfigure(0, weight=1)
        tools_grid.grid_columnconfigure(1, weight=1)
        tools_grid.grid_rowconfigure(0, weight=1)
        tools_grid.grid_rowconfigure(1, weight=1)
        tools_grid.grid_rowconfigure(2, weight=1)
        
        # Create tool cards with responsive sizing
        card_width = 280
        card_height = 240  # Slightly smaller to fit 3 rows
        
        # Row 1
        ToolCard(
            tools_grid,
            "Profile Info Scraper",
            "Extract and analyze agent profile information with advanced data processing",
            lambda: self.launch_tool("profile_info_get/GUI/scraper_gui.py"),
            icon="👤",
            width=card_width,
            height=card_height
        ).grid(row=0, column=0, padx=15, pady=15, sticky='nsew')
        
        ToolCard(
            tools_grid,
            "Buy Package Bot",
            "Automate package purchases for agents with intelligent cost and due amount handling",
            lambda: self.launch_tool("buy_package_bot/GUI/buy_package_bot.py"),
            icon="🛒",
            width=card_width,
            height=card_height
        ).grid(row=0, column=1, padx=15, pady=15, sticky='nsew')
        
        # Row 2
        ToolCard(
            tools_grid,
            "Withdrawal Submit Bot",
            "Automate withdrawal request submissions with intelligent validation",
            lambda: self.launch_tool("withdrawal_submit_bot/GUI/withdrawal_bot_gui.py"),
            icon="💸",
            width=card_width,
            height=card_height
        ).grid(row=1, column=0, padx=15, pady=15, sticky='nsew')
        
        ToolCard(
            tools_grid,
            "Withdrawal Complete Bot",
            "Streamline withdrawal completion process with automated verification",
            lambda: self.launch_tool("withdrawal_complete_bot/GUI/withdrawal_complete_bot_gui.py"),
            icon="✅",
            width=card_width,
            height=card_height
        ).grid(row=1, column=1, padx=15, pady=15, sticky='nsew')
        
        # Row 3 - New tools
        ToolCard(
            tools_grid,
            "Change Referer Name",
            "Batch process to change referer names for multiple agents using Selenium automation",
            lambda: self.launch_tool("change_refer_name/GUI/change_referer_gui.py"),
            icon="🔄",
            width=card_width,
            height=card_height
        ).grid(row=2, column=0, padx=15, pady=15, sticky='nsew')
        
        ToolCard(
            tools_grid,
            "Number & Name Change",
            "Automate changing agent numbers and names with batch processing capabilities",
            lambda: self.launch_tool("number_and_name_change/GUI/change_number_gui.py"),
            icon="📝",
            width=card_width,
            height=card_height
        ).grid(row=2, column=1, padx=15, pady=15, sticky='nsew')

    def create_status_bar(self):
        status_frame = tk.Frame(self.root, bg='#f0f0f0', height=30)
        status_frame.pack(fill='x', side='bottom')
        
        # Left side - Status indicators
        status_container = tk.Frame(status_frame, bg='#f0f0f0')
        status_container.pack(side='left', padx=10)
        
        # System status
        system_status = tk.Label(
            status_container,
            text="● System Status: Online",
            fg='#28a745',
            bg='#f0f0f0',
            font=('Segoe UI', 9)
        )
        system_status.pack(side='left', padx=(0, 20))
        
        # Right side - Time and date
        time_container = tk.Frame(status_frame, bg='#f0f0f0')
        time_container.pack(side='right', padx=10)
        
        self.time_label = tk.Label(
            time_container,
            text="",
            bg='#f0f0f0',
            fg='#666666',
            font=('Segoe UI', 9)
        )
        self.time_label.pack(side='right')
        
        # Update time
        self.update_time()

    def update_time(self):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=f"Current Time: {current_time}")
        self.root.after(1000, self.update_time)

    def on_window_resize(self, event):
        # Only handle main window resize events
        if event.widget == self.root:
            # Calculate scale factors
            width_scale = self.root.winfo_width() / self.original_width
            height_scale = self.root.winfo_height() / self.original_height
            
            # Update font sizes based on scale
            self.update_font_sizes(min(width_scale, height_scale))
            
            # Update card sizes for better responsiveness
            self.update_card_sizes(width_scale, height_scale)

    def update_font_sizes(self, scale):
        # Update font sizes for all widgets based on scale
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button)):
                current_font = widget['font']
                if isinstance(current_font, str):
                    # Parse font string and update size
                    font_parts = current_font.split()
                    if len(font_parts) >= 2:
                        try:
                            size = int(font_parts[-2])
                            new_size = int(size * scale)
                            font_parts[-2] = str(new_size)
                            widget['font'] = ' '.join(font_parts)
                        except ValueError:
                            pass

    def update_card_sizes(self, width_scale, height_scale):
        """Update card sizes based on window resize"""
        # Find all ToolCard instances and update their sizes
        for widget in self.root.winfo_children():
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    if hasattr(child, 'winfo_children'):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, ToolCard):
                                # Update card dimensions
                                new_width = int(280 * min(width_scale, height_scale))
                                new_height = int(240 * min(width_scale, height_scale))
                                grandchild.configure(width=new_width, height=new_height)

    def launch_tool(self, tool_path):
        try:
            # Resolve path relative to this script's directory, not current working directory
            if os.path.isabs(tool_path):
                abs_path = tool_path
            else:
                abs_path = os.path.join(self.base_dir, tool_path)
            
            # Normalize the path (resolve .. and .)
            abs_path = os.path.normpath(abs_path)
            
            # Check if file exists
            if not os.path.exists(abs_path):
                self.show_error(f"Tool not found: {abs_path}\n\nExpected at: {tool_path}")
                return
            
            # Change to the tool's directory temporarily to handle relative imports
            original_cwd = os.getcwd()
            tool_dir = os.path.dirname(abs_path)
            
            try:
                # Change to tool directory for relative imports
                os.chdir(tool_dir)
                
                # Import the module
                spec = importlib.util.spec_from_file_location("tool_module", abs_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Create new window for the tool
                tool_window = tk.Toplevel(self.root)
                tool_window.title(os.path.basename(tool_path))
                
                # Set window icon and style
                set_window_icon(tool_window)
                tool_window.configure(bg=self.bg_color)
                
                # Initialize the tool's GUI
                if hasattr(module, 'ScraperGUI'):
                    module.ScraperGUI(tool_window)
                elif hasattr(module, 'WithdrawalBotGUI'):
                    module.WithdrawalBotGUI(tool_window)
                elif hasattr(module, 'WithdrawalCompleteBotGUI'):
                    module.WithdrawalCompleteBotGUI(tool_window)
                elif hasattr(module, 'BuyPackageGUI'):
                    module.BuyPackageGUI(tool_window)
                elif hasattr(module, 'ChangeRefererGUI'):
                    module.ChangeRefererGUI(tool_window)
                elif hasattr(module, 'ChangeNumberGUI'):
                    module.ChangeNumberGUI(tool_window)
                else:
                    # If no GUI class found, try to run as a script in a separate process
                    # Close the empty window we created
                    tool_window.destroy()
                    
                    # Launch the script as a subprocess
                    if sys.platform == "win32":
                        # Windows - open in new console window
                        subprocess.Popen(
                            [sys.executable, abs_path],
                            cwd=tool_dir,
                            creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0
                        )
                    else:
                        # Linux/Mac - run in background
                        subprocess.Popen(
                            [sys.executable, abs_path],
                            cwd=tool_dir,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                    messagebox.showinfo(
                        "Script Launched",
                        f"Script '{os.path.basename(tool_path)}' has been launched in a separate process.\n\n"
                        f"Check the console/terminal for output."
                    )
            finally:
                # Restore original working directory
                os.chdir(original_cwd)
            
        except Exception as e:
            error_msg = f"Error launching tool: {str(e)}\n\n{traceback.format_exc()}"
            self.show_error(error_msg)

    def show_error(self, message):
        messagebox.showerror("Error", message)

if __name__ == "__main__":
    root = tk.Tk()
    app = IndexGUI(root)
    root.mainloop() 