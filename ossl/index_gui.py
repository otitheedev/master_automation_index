import os
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import subprocess
import importlib.util
import traceback
from datetime import datetime

# Add project root to path for icon_utils
# Get absolute path of current file
try:
    current_file = os.path.abspath(__file__)
except NameError:
    # Fallback if __file__ is not defined
    current_file = os.path.abspath(sys.argv[0])

# Get directory containing this file (ossl/)
current_dir = os.path.dirname(current_file)
# Go up one level to project root
project_root = os.path.dirname(current_dir)

# Add to path if not already there
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import icon utility (with fallback if not found)
try:
    from icon_utils import set_window_icon
except ImportError as e:
    # Fallback if icon_utils not found - create a no-op function
    def set_window_icon(window):
        try:
            # Try to find icon.ico in project root
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
            child.bind('<Enter>', self.on_enter)
            child.bind('<Leave>', self.on_leave)
            child.bind('<Button-1>', self.on_card_click)
    
    def on_enter(self, e):
        self.card_frame.configure(
            highlightbackground='#4a90e2',
            highlightthickness=2
        )
    
    def on_leave(self, e):
        self.card_frame.configure(
            highlightbackground='#e0e0e0',
            highlightthickness=1
        )
    
    def on_card_click(self, e):
        if self.command:
            self.command()

class IndexGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OSSL Automation Suite")
        
        # Window configuration
        self.original_width = 1000
        self.original_height = 700
        self.root.geometry(f"{self.original_width}x{self.original_height}")
        self.root.minsize(900, 600)
        
        # Set window icon
        set_window_icon(self.root)
        
        # Color scheme
        self.bg_color = '#f5f7fa'
        self.text_color = '#333333'
        self.accent_color = '#4a90e2'
        
        self.root.configure(bg=self.bg_color)
        
        # Store base directory
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Create UI components
        self.create_header()
        self.create_tools_section()
        self.create_status_bar()
        
        # Bind window resize event
        self.root.bind('<Configure>', self.on_window_resize)
    
    def create_header(self):
        header_frame = tk.Frame(self.root, bg=self.bg_color, height=100)
        header_frame.pack(fill='x', padx=20, pady=(20, 10))
        header_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text="OSSL Automation Suite",
            font=("Segoe UI", 28, "bold"),
            bg=self.bg_color,
            fg=self.text_color
        )
        title_label.pack(pady=(10, 5))
        
        # Subtitle
        subtitle_label = tk.Label(
            header_frame,
            text="Centralized tool launcher for OSSL automation scripts",
            font=("Segoe UI", 12),
            bg=self.bg_color,
            fg='#666666'
        )
        subtitle_label.pack()
    
    def create_tools_section(self):
        tools_frame = tk.Frame(self.root, bg=self.bg_color)
        tools_frame.pack(expand=True, fill='both', padx=20, pady=10)
        
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
        
        # Configure grid for 2x2 layout (2 rows, 2 columns)
        tools_grid.grid_columnconfigure(0, weight=1)
        tools_grid.grid_columnconfigure(1, weight=1)
        tools_grid.grid_rowconfigure(0, weight=1)
        tools_grid.grid_rowconfigure(1, weight=1)
        
        # Create tool cards with responsive sizing
        card_width = 300
        card_height = 250
        
        # Row 1
        ToolCard(
            tools_grid,
            "Download PDF Bot (ACC)",
            "Automate PDF downloads from ACC system with intelligent file management",
            lambda: self.launch_tool_gui("Download PDF Bot (ACC)/downloadBot_gui.py", "DownloadBotGUI"),
            icon="📥",
            width=card_width,
            height=card_height
        ).grid(row=0, column=0, padx=15, pady=15, sticky='nsew')
        
        ToolCard(
            tools_grid,
            "Employee Create BOT",
            "Automate employee creation with batch processing and data validation",
            lambda: self.launch_tool_gui("Employee Create BOT/automation.py", "EmployeeImporterApp"),
            icon="👥",
            width=card_width,
            height=card_height
        ).grid(row=0, column=1, padx=15, pady=15, sticky='nsew')
        
        # Row 2
        ToolCard(
            tools_grid,
            "Testing Report All",
            "Generate comprehensive testing reports with automated data collection",
            lambda: self.launch_tool_gui("Testing Report All/testing.py", "QATestingApp"),
            icon="📊",
            width=card_width,
            height=card_height
        ).grid(row=1, column=0, padx=15, pady=15, sticky='nsew')
        
        # Placeholder for future tools (if needed)
        # ToolCard(
        #     tools_grid,
        #     "Future Tool",
        #     "Description of future tool",
        #     lambda: self.launch_tool("path/to/tool.py"),
        #     icon="🔮",
        #     width=card_width,
        #     height=card_height
        # ).grid(row=1, column=1, padx=15, pady=15, sticky='nsew')
    
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
            pass  # Can add responsive behavior here if needed
    
    def launch_tool_gui(self, tool_path, gui_class_name):
        """Launch a tool GUI class directly in a new window"""
        try:
            # Resolve absolute path relative to base directory
            abs_path = os.path.join(self.base_dir, tool_path)
            
            # Check if file exists
            if not os.path.exists(abs_path):
                messagebox.showerror(
                    "File Not Found",
                    f"Tool script not found at:\n{abs_path}\n\nPlease ensure the file exists."
                )
                return
            
            # Get the directory of the tool script
            tool_dir = os.path.dirname(abs_path)
            original_cwd = os.getcwd()
            
            try:
                # Change to tool directory for relative imports
                os.chdir(tool_dir)
                
                # Import the module
                spec = importlib.util.spec_from_file_location("tool_module", abs_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load module from {abs_path}")
                
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Create new window for the tool
                tool_window = tk.Toplevel(self.root)
                tool_window.title(os.path.basename(tool_path).replace('.py', ''))
                
                # Set window icon
                set_window_icon(tool_window)
                
                # Get the GUI class
                gui_class = getattr(module, gui_class_name, None)
                if gui_class is None:
                    raise AttributeError(f"GUI class '{gui_class_name}' not found in module")
                
                # Initialize the tool's GUI
                gui_class(tool_window)
                
            finally:
                # Restore original working directory
                os.chdir(original_cwd)
            
        except Exception as e:
            error_msg = f"Error launching tool GUI: {str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("Error", error_msg)

if __name__ == "__main__":
    root = tk.Tk()
    app = IndexGUI(root)
    root.mainloop()

