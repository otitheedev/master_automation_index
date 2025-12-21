#!/usr/bin/env python3
"""
Two-step Tkinter MySQL backup tool that works with local, Docker, and remote/VPS MySQL.

Connection behavior:
  - If a Unix socket path is provided, the app connects using that socket (mysql/mysqldump -S SOCKET),
    and Host/Port are ignored.
  - Otherwise it connects via Host and Port (mysql/mysqldump -h HOST -P PORT).
  - The password is passed via the MYSQL_PWD environment variable so it is not exposed on
    the command line but still works with both local and remote servers.

Step 1: Connect panel
  - Choose a connection preset (Local TCP, Local Socket, Docker, Remote/VPS) or fill fields manually.
  - Enter host, port, user, password and/or optional socket path.
  - Click "Connect & Load Databases".

Step 2: Database selection panel
  - Shows all databases as checkboxes.
  - Choose backup folder.
  - Click "Backup Selected" to dump each selected DB with mysqldump.

Requirements:
  - Python 3
  - Tkinter (usually included with Python on Linux)
  - mysql client + mysqldump (sudo apt install mysql-client)
"""

import os
import platform
import sqlite3
import stat
import subprocess
import threading
import tkinter as tk
import base64
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

# Add project root to path for icon_utils
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from icon_utils import set_window_icon


# Color scheme
COLOR_PRIMARY = "#2563eb"  # Blue
COLOR_PRIMARY_HOVER = "#1d4ed8"
COLOR_SECONDARY = "#10b981"  # Green
COLOR_SECONDARY_HOVER = "#059669"
COLOR_DANGER = "#ef4444"  # Red
COLOR_BG = "#f8fafc"  # Light gray
COLOR_CARD = "#ffffff"  # White
COLOR_BORDER = "#e2e8f0"  # Light border
COLOR_TEXT = "#1e293b"  # Dark gray
COLOR_TEXT_LIGHT = "#64748b"  # Medium gray
COLOR_SUCCESS = "#22c55e"  # Success green

# --- SQLite Database Manager ---
class DatabaseManager:
    """Manages SQLite database for storing connections, backup locations, and history."""
    
    def __init__(self, db_path=None):
        if db_path is None:
            # Cross-platform secure path for storing credentials
            # Linux: ~/.local/share/mysql_backup_tool/ (follows XDG Base Directory spec)
            # Windows: %LOCALAPPDATA%\mysql_backup_tool\ (user-specific, secure location)
            system = platform.system()
            
            if system == "Windows":
                # Windows: Use LOCALAPPDATA (user-specific, not synced)
                appdata = os.getenv("LOCALAPPDATA")
                if appdata:
                    db_dir = Path(appdata) / "mysql_backup_tool"
                else:
                    # Fallback to user home
                    db_dir = Path.home() / ".mysql_backup_tool"
            else:
                # Linux/Unix: Use XDG Base Directory spec (~/.local/share/)
                xdg_data_home = os.getenv("XDG_DATA_HOME")
                if xdg_data_home:
                    db_dir = Path(xdg_data_home) / "mysql_backup_tool"
                else:
                    # Fallback to ~/.local/share/
                    db_dir = Path.home() / ".local" / "share" / "mysql_backup_tool"
            
            # Create directory with secure permissions (700 = owner read/write/execute only)
            db_dir.mkdir(parents=True, exist_ok=True)
            
            # Set secure permissions on directory (Linux/Unix only)
            if system != "Windows":
                try:
                    os.chmod(db_dir, stat.S_IRWXU)  # 700: owner only
                except OSError:
                    pass  # Ignore if chmod fails
            
            db_path = db_dir / "backup_tool.db"
        
        self.db_path = db_path
        self.init_database()
        
        # Set secure file permissions on database file (Linux/Unix only)
        if platform.system() != "Windows":
            try:
                os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)  # 600: owner read/write only
            except OSError:
                pass  # Ignore if chmod fails (file might not exist yet)
    
    def get_database_path(self):
        """Get the path to the database file (for informational purposes)."""
        return str(self.db_path)
    
    def _ensure_secure_permissions(self):
        """Ensure database file has secure permissions (Linux/Unix only)."""
        if platform.system() != "Windows" and os.path.exists(self.db_path):
            try:
                # Set file permissions to 600 (owner read/write only)
                os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass  # Ignore if chmod fails
    
    def get_connection(self):
        """Get database connection."""
        # Ensure secure permissions before connecting
        self._ensure_secure_permissions()
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Saved connections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                host TEXT,
                port TEXT,
                socket_path TEXT,
                username TEXT,
                password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_favorite INTEGER DEFAULT 0
            )
        """)
        
        # Backup locations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_default INTEGER DEFAULT 0
            )
        """)
        
        # Backup history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_name TEXT,
                databases TEXT,
                backup_path TEXT,
                backup_size INTEGER,
                status TEXT,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                duration_seconds REAL
            )
        """)
        
        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Ensure secure permissions after database creation
        self._ensure_secure_permissions()
    
    def save_connection(self, name, host, port, socket_path, username, password, is_favorite=False):
        """Save a connection profile."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Simple base64 encoding for password (not secure, but better than plain text)
        encoded_password = base64.b64encode(password.encode()).decode() if password else ""
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO saved_connections 
                (name, host, port, socket_path, username, password, is_favorite, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (name, host, port, socket_path, username, encoded_password, 1 if is_favorite else 0))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_connections(self, favorites_only=False):
        """Get all saved connections."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if favorites_only:
            cursor.execute("SELECT * FROM saved_connections WHERE is_favorite = 1 ORDER BY last_used DESC")
        else:
            cursor.execute("SELECT * FROM saved_connections ORDER BY is_favorite DESC, last_used DESC")
        
        rows = cursor.fetchall()
        conn.close()
        
        connections = []
        for row in rows:
            # Decode password
            password = base64.b64decode(row[6]).decode() if row[6] else ""
            connections.append({
                'id': row[0],
                'name': row[1],
                'host': row[2] or "",
                'port': row[3] or "",
                'socket_path': row[4] or "",
                'username': row[5] or "",
                'password': password,
                'created_at': row[7],
                'last_used': row[8],
                'is_favorite': bool(row[9])
            })
        
        return connections
    
    def load_connection(self, name):
        """Load a connection by name."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM saved_connections WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            password = base64.b64decode(row[6]).decode() if row[6] else ""
            # Update last_used
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE saved_connections SET last_used = CURRENT_TIMESTAMP WHERE name = ?", (name,))
            conn.commit()
            conn.close()
            
            return {
                'name': row[1],
                'host': row[2] or "",
                'port': row[3] or "",
                'socket_path': row[4] or "",
                'username': row[5] or "",
                'password': password
            }
        return None
    
    def delete_connection(self, name):
        """Delete a saved connection."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM saved_connections WHERE name = ?", (name,))
        conn.commit()
        conn.close()
    
    def save_backup_location(self, name, path, is_default=False):
        """Save a backup location."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if is_default:
            # Remove default flag from other locations
            cursor.execute("UPDATE backup_locations SET is_default = 0")
        
        cursor.execute("""
            INSERT OR REPLACE INTO backup_locations 
            (name, path, is_default, last_used)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, path, 1 if is_default else 0))
        
        conn.commit()
        conn.close()
    
    def get_backup_locations(self):
        """Get all saved backup locations."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM backup_locations ORDER BY is_default DESC, last_used DESC")
        rows = cursor.fetchall()
        conn.close()
        
        locations = []
        for row in rows:
            locations.append({
                'id': row[0],
                'name': row[1],
                'path': row[2],
                'created_at': row[3],
                'last_used': row[4],
                'is_default': bool(row[5])
            })
        return locations
    
    def get_default_backup_location(self):
        """Get the default backup location."""
        locations = self.get_backup_locations()
        for loc in locations:
            if loc['is_default']:
                return loc['path']
        if locations:
            return locations[0]['path']
        return None
    
    def add_backup_history(self, connection_name, databases, backup_path, status, error_message=None, duration=None):
        """Add a backup record to history."""
        import time
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Calculate backup size
        backup_size = 0
        if os.path.exists(backup_path):
            if os.path.isdir(backup_path):
                for root, dirs, files in os.walk(backup_path):
                    for file in files:
                        backup_size += os.path.getsize(os.path.join(root, file))
            else:
                backup_size = os.path.getsize(backup_path)
        
        # Calculate start time
        duration_sec = duration or 0
        start_datetime = datetime.fromtimestamp(datetime.now().timestamp() - duration_sec)
        start_time_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO backup_history 
            (connection_name, databases, backup_path, backup_size, status, error_message, started_at, completed_at, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """, (
            connection_name,
            ", ".join(databases) if isinstance(databases, list) else databases,
            backup_path,
            backup_size,
            status,
            error_message,
            start_time_str,
            duration
        ))
        
        conn.commit()
        conn.close()
    
    def get_backup_history(self, limit=50):
        """Get backup history."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM backup_history 
            ORDER BY started_at DESC 
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                'id': row[0],
                'connection_name': row[1],
                'databases': row[2],
                'backup_path': row[3],
                'backup_size': row[4],
                'status': row[5],
                'error_message': row[6],
                'started_at': row[7],
                'completed_at': row[8],
                'duration_seconds': row[9]
            })
        return history
    
    def get_setting(self, key, default=None):
        """Get a setting value."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    
    def set_setting(self, key, value):
        """Set a setting value."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# Initialize database manager
db_manager = DatabaseManager()

def create_tooltip(widget, text):
    """Create a tooltip for a widget."""
    def on_enter(event):
        tooltip = tk.Toplevel()
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        label = tk.Label(
            tooltip,
            text=text,
            background="#1e293b",
            foreground="white",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9),
            padx=8,
            pady=4,
        )
        label.pack()
        widget.tooltip = tooltip

    def on_leave(event):
        if hasattr(widget, 'tooltip'):
            widget.tooltip.destroy()
            del widget.tooltip

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

def create_styled_button(parent, text, command, color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HOVER, width=None):
    """Create a styled button with hover effects."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=color,
        fg="white",
        font=("TkDefaultFont", 10, "bold"),
        relief="flat",
        borderwidth=0,
        padx=20,
        pady=10,
        cursor="hand2",
        width=width,
        activebackground=hover_color,
        activeforeground="white",
    )
    
    def on_enter(e):
        btn.config(bg=hover_color)
    
    def on_leave(e):
        btn.config(bg=color)
    
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn

def create_card_frame(parent, title=None, padding=15):
    """Create a styled card frame with optional title."""
    card = tk.Frame(
        parent,
        bg=COLOR_CARD,
        relief="flat",
        borderwidth=1,
        highlightbackground=COLOR_BORDER,
        highlightthickness=1,
    )
    
    if title:
        title_frame = tk.Frame(card, bg=COLOR_CARD)
        title_frame.pack(fill="x", padx=padding, pady=(padding, 5))
        title_label = tk.Label(
            title_frame,
            text=title,
            font=("TkDefaultFont", 12, "bold"),
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            anchor="w",
        )
        title_label.pack(fill="x")
    
    return card

def set_busy(is_busy: bool, text: str = ""):
    """Enable/disable UI and show/hide the loading spinner."""
    if is_busy:
        status_var.set(text)
        progress_bar.start(10)
        progress_frame.pack(fill="x", side="bottom", padx=0, pady=0)
        root.config(cursor="watch")
        # Disable main action buttons
        try:
            test_btn.config(state="disabled")
            connect_btn.config(state="disabled")
            if 'btn_backup' in globals():
                btn_backup.config(state="disabled")
        except:
            pass
    else:
        status_var.set("")
        progress_bar.stop()
        progress_frame.pack_forget()
        root.config(cursor="")
        # Enable main action buttons
        try:
            test_btn.config(state="normal")
            connect_btn.config(state="normal")
            if 'btn_backup' in globals():
                btn_backup.config(state="normal")
        except:
            pass


def choose_backup_folder():
    """Open a folder selection dialog and store the chosen path."""
    # Use last used location if available
    last_location = db_manager.get_default_backup_location()
    initial_dir = last_location if last_location and os.path.exists(last_location) else None
    
    folder = filedialog.askdirectory(initialdir=initial_dir)
    if folder:
        backup_dir_var.set(folder)
        # Save as backup location
        db_manager.save_backup_location("Last Used", folder, is_default=True)


def _connect_worker(host: str, port: str, sock: str, user: str, password: str):
    """Background worker: connect to MySQL and fetch database list."""
    # Build mysql command to list databases
    cmd = ["mysql"]
    if sock:
        cmd.extend(["-S", sock])
    else:
        # Force TCP so mysql does not try the local socket first
        cmd.extend(["--protocol=TCP", f"-h{host}", f"-P{port}"])
    cmd.extend(
        [
            f"-u{user}",
            "-e",
            "SHOW DATABASES;",
        ]
    )

    env = os.environ.copy()
    if password:
        # Avoid passing password directly on command line to prevent warnings
        env["MYSQL_PWD"] = password

    try:
        print(f"[DEBUG] mysql connect cmd: {' '.join(cmd)}")
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )
        print(f"[DEBUG] mysql connect return code: {proc.returncode}")
        if proc.stderr:
            print(f"[DEBUG] mysql connect stderr:\n{proc.stderr}")
    except FileNotFoundError:
        def _show_missing():
            set_busy(False)
            messagebox.showerror(
                "Error",
                "mysql client not found. Install it with:\n\nsudo apt install mysql-client",
            )

        root.after(0, _show_missing)
        return
    except Exception as e:  # pylint: disable=broad-except
        def _show_unexpected():
            set_busy(False)
            messagebox.showerror("Error", f"Unexpected error:\n{e}")

        root.after(0, _show_unexpected)
        return

    if proc.returncode != 0:
        def _show_failed():
            set_busy(False)
            friendly = _make_friendly_error(proc.stderr)
            messagebox.showerror(
                "Connection Failed", f"{friendly}mysql error:\n{proc.stderr}"
            )

        root.after(0, _show_failed)
        return

    lines = proc.stdout.strip().splitlines()
    if not lines:
        def _no_db():
            set_busy(False)
            messagebox.showerror("Error", "No databases found.")

        root.after(0, _no_db)
        return

    db_names = [line.strip() for line in lines[1:] if line.strip()]
    # Skip system databases that are not meant to be dumped or often restricted
    skip_dbs = {"information_schema", "performance_schema"}
    db_names = [name for name in db_names if name not in skip_dbs]
    if not db_names:
        def _no_db2():
            set_busy(False)
            messagebox.showerror("Error", "No databases returned from server.")

        root.after(0, _no_db2)
        return

    def _apply_result():
        # Clear old checkboxes
        for widget in db_list_canvas_frame.winfo_children():
            widget.destroy()
        db_vars.clear()

        # Add checkboxes for each database with better styling
        for i, db_name in enumerate(db_names):
            var = tk.BooleanVar(value=True)
            db_vars[db_name] = var
            
            # Create a frame for each checkbox with better styling
            check_frame = tk.Frame(
                db_list_canvas_frame,
                bg=COLOR_CARD,
                relief="flat",
            )
            check_frame.pack(fill="x", padx=2, pady=2)
            
            check_btn = tk.Checkbutton(
                check_frame,
                text=f"  {db_name}",
                variable=var,
                anchor="w",
                bg=COLOR_CARD,
                fg=COLOR_TEXT,
                selectcolor=COLOR_CARD,
                activebackground=COLOR_CARD,
                activeforeground=COLOR_TEXT,
                font=("TkDefaultFont", 10),
                padx=8,
                pady=6,
                cursor="hand2",
            )
            check_btn.pack(fill="x", anchor="w")
            
            # Add hover effect
            def on_enter(e, frame=check_frame):
                frame.config(bg=COLOR_BG)
                check_btn.config(bg=COLOR_BG, activebackground=COLOR_BG)
            
            def on_leave(e, frame=check_frame):
                frame.config(bg=COLOR_CARD)
                check_btn.config(bg=COLOR_CARD, activebackground=COLOR_CARD)
            
            check_frame.bind("<Enter>", on_enter)
            check_frame.bind("<Leave>", on_leave)
            check_btn.bind("<Enter>", on_enter)
            check_btn.bind("<Leave>", on_leave)

        # Update scroll region
        root.after(100, update_scroll_region)

        # Update connection info with better formatting
        if sock:
            conn_text = f"✓ Connected: {user}@{sock}"
        else:
            conn_text = f"✓ Connected: {user}@{host}:{port}"
        connection_label.config(
            text=conn_text,
            fg=COLOR_SUCCESS,
            font=("TkDefaultFont", 10, "bold")
        )

        connect_frame.pack_forget()
        backup_frame.pack(padx=15, pady=15, fill="both", expand=True)
        
        # Resize window to accommodate backup panel and ensure backup button is visible
        root.update_idletasks()
        current_width = root.winfo_width()
        
        # Calculate required height for backup panel
        backup_frame.update_idletasks()
        required_height = backup_frame.winfo_reqheight() + 100  # Add padding for header and margins
        
        # Set new height (minimum 750, or required height if larger)
        new_height = max(750, required_height, 800)
        root.geometry(f"{current_width}x{new_height}")
        
        # Ensure window is visible and bring to front
        root.update()
        root.lift()
        # Don't force focus - let user click where they want to type
        
        # Ensure backup button is visible by scrolling if needed
        try:
            if 'btn_backup' in globals():
                btn_backup.update_idletasks()
        except:
            pass
        
        set_busy(False)

    root.after(0, _apply_result)


def connect_and_load_databases():
    """Start background connection and DB loading with spinner."""
    server = server_var.get().strip()
    user = user_var.get().strip()
    password = password_var.get().strip()

    host, port, sock = parse_server(server)
    port_override = port_override_var.get().strip()
    if port_override and not sock:
        port = port_override

    if sock:
        if not user:
            messagebox.showerror(
                "Error",
                "Please fill Username (and Password if needed) for socket connections.",
            )
            return
    else:
        if not (host and port and user):
            messagebox.showerror(
                "Error",
                "Please fill Server (host[:port]) and Username (and Password if needed).",
            )
            return

    set_busy(True, "Connecting to MySQL and loading databases...")
    threading.Thread(
        target=_connect_worker,
        args=(host, port, sock, user, password),
        daemon=True,
    ).start()


def _backup_worker(
    host: str,
    port: str,
    sock: str,
    user: str,
    password: str,
    backup_dir: str,
    selected_dbs: list[str],
    connection_name: str = None,
):
    """Background worker: backup all selected databases using mysqldump."""
    import time
    start_time = time.time()
    errors = []

    # Create a dated subfolder for this backup run, e.g. "19 Dec 2025 - 12:00 PM DB"
    run_folder_name = datetime.now().strftime("%d %b %Y - %I:%M %p DB")
    run_dir = os.path.join(backup_dir, run_folder_name)
    os.makedirs(run_dir, exist_ok=True)

    for db_name in selected_dbs:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_file = os.path.join(run_dir, f"{db_name}-backup-{timestamp}.sql")

        cmd = ["mysqldump"]
        if sock:
            cmd.extend(["-S", sock])
        else:
            # Force TCP so mysqldump does not try the local socket first
            cmd.extend(["--protocol=TCP", f"-h{host}", f"-P{port}"])
        cmd.extend(
            [
                f"-u{user}",
                db_name,
            ]
        )

        env = os.environ.copy()
        if password:
            # Avoid passing password directly on command line to prevent warnings
            env["MYSQL_PWD"] = password

        try:
            print(f"[DEBUG] mysqldump cmd ({db_name}): {' '.join(cmd)}")
            with open(backup_file, "w", encoding="utf-8") as f:
                proc = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    env=env,
                )
            print(f"[DEBUG] mysqldump return code ({db_name}): {proc.returncode}")
            if proc.stderr:
                print(f"[DEBUG] mysqldump stderr ({db_name}):\n{proc.stderr}")

            if proc.returncode != 0:
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                errors.append(f"{db_name}: {proc.stderr.strip()}")
        except FileNotFoundError:
            def _no_dump():
                set_busy(False)
                messagebox.showerror(
                    "Error",
                    "mysqldump not found. Install it with:\n\nsudo apt install mysql-client",
                )

            root.after(0, _no_dump)
            return
        except Exception as e:  # pylint: disable=broad-except
            errors.append(f"{db_name}: {e}")

    def _finish():
        duration = time.time() - start_time
        set_busy(False)
        
        # Save backup history
        conn_name = connection_name or f"{user}@{host}:{port}" if not sock else f"{user}@{sock}"
        status = "success" if not errors else "failed"
        error_msg = "\n".join(errors) if errors else None
        
        try:
            db_manager.add_backup_history(
                conn_name,
                selected_dbs,
                run_dir,
                status,
                error_msg,
                duration
            )
        except Exception as e:
            print(f"Error saving backup history: {e}")
        
        if errors:
            msg = "Some backups failed:\n\n" + "\n\n".join(errors)
            messagebox.showerror("Backup Completed with Errors", msg)
        else:
            messagebox.showinfo(
                "Success",
                f"Backup completed for {len(selected_dbs)} databases.\n\nSaved in:\n{run_dir}",
            )

    root.after(0, _finish)


def backup_selected_databases():
    """Validate inputs and start background backup with spinner."""
    server = server_var.get().strip()
    user = user_var.get().strip()
    password = password_var.get().strip()
    backup_dir = backup_dir_var.get().strip()

    host, port, sock = parse_server(server)
    port_override = port_override_var.get().strip()
    if port_override and not sock:
        port = port_override

    if not backup_dir:
        messagebox.showerror("Error", "Please choose a backup folder.")
        return

    if not os.path.isdir(backup_dir):
        messagebox.showerror("Error", "Backup folder does not exist.")
        return

    selected_dbs = [name for name, var in db_vars.items() if var.get()]
    if not selected_dbs:
        messagebox.showerror("Error", "Please select at least one database.")
        return

    set_busy(True, f"Backing up {len(selected_dbs)} database(s)...")
    threading.Thread(
        target=_backup_worker,
        args=(host, port, sock, user, password, backup_dir, selected_dbs, current_connection_name),
        daemon=True,
    ).start()


def _make_friendly_error(raw_err: str) -> str:
    """Return a short friendly explanation prefix for common MySQL errors."""
    msg = raw_err.lower()
    if "access denied" in msg:
        return (
            "Access denied: check username/password and that this user is allowed "
            "to connect from this host.\n\n"
        )
    if "can't connect to mysql server" in msg or "connection refused" in msg:
        return (
            "Connection failed: check Host/Port (or Docker/VPS mapping) and firewall rules.\n\n"
        )
    if "can't connect to local mysql server through socket" in msg or "no such file or directory" in msg:
        return (
            "Socket error: check the Unix socket path or try using Host/Port instead.\n\n"
        )
    return ""


def parse_server(server: str) -> tuple[str, str, str]:
    """
    Adminer-like server parsing:
      - If value starts with '/', treat as Unix socket path.
      - If contains host:port and port is numeric, split.
      - Otherwise treat as host with default port 3306.
    Returns (host, port, socket_path). Only one of (host, socket_path) is non-empty.
    """
    s = server.strip()
    if not s:
        return "localhost", "3306", ""
    if s.startswith("/"):
        return "", "", s
    if ":" in s:
        host, rest = s.split(":", 1)
        if rest.isdigit():
            return host or "localhost", rest, ""
        # Non-numeric part after colon: assume it's a socket path like host:/path
        if rest.startswith("/"):
            return "", "", rest
    return s, "3306", ""


# --- Tkinter UI setup ---
root = tk.Tk()
root.title("MySQL Multi-Database Backup Tool")
root.geometry("750x750")
root.configure(bg=COLOR_BG)
root.minsize(700, 700)  # Set minimum window size
set_window_icon(root)

# Prevent accidental app closure - show confirmation dialog
def on_closing():
    """Handle window close event."""
    if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
        root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# Note: Removed focus handlers that were interfering with text input
# The window will still function normally without forced focus

# Shared variables (Adminer-like login fields)
system_var = tk.StringVar(value="MySQL")
server_var = tk.StringVar(value="localhost")
port_override_var = tk.StringVar()  # optional explicit port
user_var = tk.StringVar(value="root")
password_var = tk.StringVar()
database_var = tk.StringVar()  # optional, for future use
backup_dir_var = tk.StringVar()

db_vars: dict[str, tk.BooleanVar] = {}
status_var = tk.StringVar(value="")
current_connection_name = None  # Track current connection profile name

padx = 12
pad_y = 8

# --- Header ---
header_frame = tk.Frame(root, bg=COLOR_PRIMARY, height=60)
header_frame.pack(fill="x")
header_frame.pack_propagate(False)

header_label = tk.Label(
    header_frame,
    text="🗄️  MySQL Multi-Database Backup",
    font=("TkDefaultFont", 16, "bold"),
    bg=COLOR_PRIMARY,
    fg="white",
    pady=15,
)
header_label.pack()

# --- Connect panel ---
connect_frame = create_card_frame(root, title="📡 Connection Settings", padding=20)
connect_frame.pack(padx=15, pady=15, fill="both", expand=True)

# Connection presets
presets_frame = tk.Frame(connect_frame, bg=COLOR_CARD)
presets_frame.pack(fill="x", pady=(0, 15))

preset_label = tk.Label(
    presets_frame,
    text="Quick Presets:",
    font=("TkDefaultFont", 9, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT_LIGHT,
    anchor="w",
)
preset_label.pack(side="left", padx=(0, 10))

def apply_preset(preset_type):
    """Apply connection preset values."""
    if preset_type == "local":
        server_var.set("localhost")
        port_override_var.set("3306")
        user_var.set("root")
    elif preset_type == "socket":
        server_var.set("/var/run/mysqld/mysqld.sock")
        port_override_var.set("")
        user_var.set("root")
    elif preset_type == "docker":
        server_var.set("localhost")
        port_override_var.set("3306")
        user_var.set("root")
    elif preset_type == "remote":
        server_var.set("")
        port_override_var.set("3306")
        user_var.set("")

preset_buttons_frame = tk.Frame(presets_frame, bg=COLOR_CARD)
preset_buttons_frame.pack(side="left", fill="x", expand=True)

for preset_name, preset_type in [("Local", "local"), ("Socket", "socket"), ("Docker", "docker"), ("Remote", "remote")]:
    btn = tk.Button(
        preset_buttons_frame,
        text=preset_name,
        command=lambda pt=preset_type: apply_preset(pt),
        bg=COLOR_BG,
        fg=COLOR_TEXT,
        font=("TkDefaultFont", 8),
        relief="flat",
        borderwidth=1,
        padx=10,
        pady=4,
        cursor="hand2",
        activebackground=COLOR_BORDER,
    )
    btn.pack(side="left", padx=2)

# Form fields
form_frame = tk.Frame(connect_frame, bg=COLOR_CARD)
form_frame.pack(fill="x", pady=5)

# System field (hidden but kept for compatibility)
system_combo = ttk.Combobox(
    form_frame,
    textvariable=system_var,
    values=["MySQL"],
    state="readonly",
    width=20,
)

# Server field
server_label = tk.Label(
    form_frame,
    text="Server:",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT,
    anchor="w",
)
server_label.grid(row=0, column=0, sticky="w", padx=padx, pady=pad_y)

server_entry = tk.Entry(
    form_frame,
    textvariable=server_var,
    font=("TkDefaultFont", 10),
    relief="solid",
    borderwidth=1,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    highlightcolor=COLOR_PRIMARY,
    width=35,
    bg="white",
    fg=COLOR_TEXT,
)
server_entry.grid(row=0, column=1, sticky="ew", padx=padx, pady=pad_y)
create_tooltip(server_entry, "Enter host:port or Unix socket path (e.g., localhost:3306 or /var/run/mysqld/mysqld.sock)")

server_hint = tk.Label(
    form_frame,
    text="💡 Examples: localhost, 127.0.0.1:3306, /var/run/mysqld/mysqld.sock",
    font=("TkDefaultFont", 8),
    bg=COLOR_CARD,
    fg=COLOR_TEXT_LIGHT,
    anchor="w",
)
server_hint.grid(row=1, column=1, sticky="w", padx=padx, pady=(0, pad_y))

# Port field
port_label = tk.Label(
    form_frame,
    text="Port:",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT,
    anchor="w",
)
port_label.grid(row=2, column=0, sticky="w", padx=padx, pady=pad_y)

port_entry = tk.Entry(
    form_frame,
    textvariable=port_override_var,
    font=("TkDefaultFont", 10),
    relief="solid",
    borderwidth=1,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    highlightcolor=COLOR_PRIMARY,
    width=15,
    bg="white",
    fg=COLOR_TEXT,
)
port_entry.grid(row=2, column=1, sticky="w", padx=padx, pady=pad_y)
create_tooltip(port_entry, "Optional: Override port (default: 3306)")

# Username field
user_label = tk.Label(
    form_frame,
    text="Username:",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT,
    anchor="w",
)
user_label.grid(row=3, column=0, sticky="w", padx=padx, pady=pad_y)

user_entry = tk.Entry(
    form_frame,
    textvariable=user_var,
    font=("TkDefaultFont", 10),
    relief="solid",
    borderwidth=1,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    highlightcolor=COLOR_PRIMARY,
    width=35,
    bg="white",
    fg=COLOR_TEXT,
)
user_entry.grid(row=3, column=1, sticky="ew", padx=padx, pady=pad_y)

# Password field
password_label = tk.Label(
    form_frame,
    text="Password:",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT,
    anchor="w",
)
password_label.grid(row=4, column=0, sticky="w", padx=padx, pady=pad_y)

password_entry = tk.Entry(
    form_frame,
    textvariable=password_var,
    show="*",
    font=("TkDefaultFont", 10),
    relief="solid",
    borderwidth=1,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    highlightcolor=COLOR_PRIMARY,
    width=35,
    bg="white",
    fg=COLOR_TEXT,
)
password_entry.grid(row=4, column=1, sticky="ew", padx=padx, pady=pad_y)

form_frame.columnconfigure(1, weight=1)

# Buttons
button_row = 5


def test_connection():
    """Quick connection test without loading database list."""
    server = server_var.get().strip()
    user = user_var.get().strip()
    password = password_var.get().strip()
    host, port, sock = parse_server(server)
    port_override = port_override_var.get().strip()
    if port_override and not sock:
        port = port_override

    if sock:
        if not user:
            messagebox.showerror(
                "Error",
                "Please fill Username (and Password if needed) for socket connections.",
            )
            return
    else:
        if not (host and port and user):
            messagebox.showerror(
                "Error",
                "Please fill Server (host[:port]) and Username (and Password if needed).",
            )
            return

    cmd = ["mysql"]
    if sock:
        cmd.extend(["-S", sock])
    else:
        # Force TCP so mysql does not try the local socket first
        cmd.extend(["--protocol=TCP", f"-h{host}", f"-P{port}"])
    cmd.extend([f"-u{user}", "-e", "SELECT 1;"])

    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password

    set_busy(True, "Testing connection...")

    def _worker():
        try:
            print(f"[DEBUG] mysql test cmd: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                env=env,
            )
            print(f"[DEBUG] mysql test return code: {proc.returncode}")
            if proc.stderr:
                print(f"[DEBUG] mysql test stderr:\n{proc.stderr}")
        except FileNotFoundError:
            def _show():
                set_busy(False)
                messagebox.showerror(
                    "Error",
                    "mysql client not found. Install it with:\n\nsudo apt install mysql-client",
                )

            root.after(0, _show)
            return
        except Exception as e:  # pylint: disable=broad-except
            def _show_unexpected():
                set_busy(False)
                messagebox.showerror("Error", f"Unexpected error:\n{e}")

            root.after(0, _show_unexpected)
            return

        def _finish():
            set_busy(False)
            if proc.returncode == 0:
                messagebox.showinfo("Connection OK", "Successfully connected to MySQL.")
            else:
                friendly = _make_friendly_error(proc.stderr)
                messagebox.showerror(
                    "Connection Failed", f"{friendly}mysql error:\n{proc.stderr}"
                )

        root.after(0, _finish)

    threading.Thread(target=_worker, daemon=True).start()


def save_current_connection():
    """Save current connection settings as a profile."""
    server = server_var.get().strip()
    user = user_var.get().strip()
    password = password_var.get().strip()
    
    host, port, sock = parse_server(server)
    port_override = port_override_var.get().strip()
    if port_override and not sock:
        port = port_override
    
    # Ask for connection name
    name = simpledialog.askstring(
        "Save Connection",
        "Enter a name for this connection:",
        initialvalue=f"{user}@{host or 'socket'}"
    )
    
    if not name:
        return
    
    if db_manager.save_connection(name, host, port, sock, user, password):
        messagebox.showinfo("Success", f"Connection '{name}' saved successfully!")
        refresh_connection_dropdown()
    else:
        messagebox.showerror("Error", f"Connection '{name}' already exists!")


def load_saved_connection():
    """Show dialog to load a saved connection."""
    connections = db_manager.get_connections()
    
    if not connections:
        messagebox.showinfo("No Saved Connections", "No saved connections found. Save a connection first.")
        return
    
    # Create dialog window
    dialog = create_dialog(root, "Load Saved Connection", 500, 400, grab=True)
    
    # Header
    header = tk.Label(
        dialog,
        text="📋 Saved Connections",
        font=("TkDefaultFont", 14, "bold"),
        bg=COLOR_BG,
        fg=COLOR_TEXT,
        pady=10
    )
    header.pack()
    
    # List frame with scrollbar
    list_frame = tk.Frame(dialog, bg=COLOR_BG)
    list_frame.pack(fill="both", expand=True, padx=15, pady=10)
    
    canvas = tk.Canvas(list_frame, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg=COLOR_CARD)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    def load_connection(conn):
        """Load a connection into the form."""
        global current_connection_name
        current_connection_name = conn['name']
        
        if conn['socket_path']:
            server_var.set(conn['socket_path'])
            port_override_var.set("")
        else:
            server_var.set(conn['host'] or "localhost")
            port_override_var.set(conn['port'] or "3306")
        
        user_var.set(conn['username'])
        password_var.set(conn['password'])
        dialog.destroy()
    
    def delete_connection(conn_name):
        """Delete a saved connection."""
        if messagebox.askyesno("Confirm Delete", f"Delete connection '{conn_name}'?"):
            db_manager.delete_connection(conn_name)
            refresh_connection_dropdown()
            dialog.destroy()
            load_saved_connection()  # Refresh the list
    
    # Add connection items
    for i, conn in enumerate(connections):
        item_frame = tk.Frame(scrollable_frame, bg=COLOR_CARD, relief="flat")
        item_frame.pack(fill="x", padx=5, pady=5)
        
        # Connection info
        info_frame = tk.Frame(item_frame, bg=COLOR_CARD)
        info_frame.pack(fill="x", padx=10, pady=8)
        
        name_label = tk.Label(
            info_frame,
            text=f"⭐ {conn['name']}" if conn['is_favorite'] else f"  {conn['name']}",
            font=("TkDefaultFont", 11, "bold"),
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            anchor="w"
        )
        name_label.pack(fill="x")
        
        if conn['socket_path']:
            details = f"Socket: {conn['socket_path']} | User: {conn['username']}"
        else:
            details = f"{conn['host']}:{conn['port']} | User: {conn['username']}"
        
        details_label = tk.Label(
            info_frame,
            text=details,
            font=("TkDefaultFont", 9),
            bg=COLOR_CARD,
            fg=COLOR_TEXT_LIGHT,
            anchor="w"
        )
        details_label.pack(fill="x")
        
        # Buttons
        btn_frame = tk.Frame(item_frame, bg=COLOR_CARD)
        btn_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        load_btn = tk.Button(
            btn_frame,
            text="Load",
            command=lambda c=conn: load_connection(c),
            bg=COLOR_PRIMARY,
            fg="white",
            font=("TkDefaultFont", 9, "bold"),
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2"
        )
        load_btn.pack(side="left", padx=(0, 5))
        
        delete_btn = tk.Button(
            btn_frame,
            text="Delete",
            command=lambda n=conn['name']: delete_connection(n),
            bg=COLOR_DANGER,
            fg="white",
            font=("TkDefaultFont", 9, "bold"),
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2"
        )
        delete_btn.pack(side="left")
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Close button
    close_btn = tk.Button(
        dialog,
        text="Close",
        command=dialog.destroy,
        bg=COLOR_TEXT_LIGHT,
        fg="white",
        font=("TkDefaultFont", 10, "bold"),
        relief="flat",
        padx=20,
        pady=8,
        cursor="hand2"
    )
    close_btn.pack(pady=10)


def show_backup_history():
    """Show backup history dialog."""
    history = db_manager.get_backup_history(limit=100)
    
    dialog = create_dialog(root, "Backup History", 900, 600, grab=False)
    
    # Header
    header = tk.Label(
        dialog,
        text="📊 Backup History",
        font=("TkDefaultFont", 14, "bold"),
        bg=COLOR_BG,
        fg=COLOR_TEXT,
        pady=10
    )
    header.pack()
    
    # Treeview for history
    tree_frame = tk.Frame(dialog, bg=COLOR_BG)
    tree_frame.pack(fill="both", expand=True, padx=15, pady=10)
    
    columns = ("Date", "Connection", "Databases", "Status", "Size", "Duration")
    tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)
    
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=150)
    
    tree.column("Date", width=180)
    tree.column("Connection", width=150)
    tree.column("Databases", width=200)
    tree.column("Status", width=100)
    tree.column("Size", width=120)
    tree.column("Duration", width=100)
    
    scrollbar_tree = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar_tree.set)
    
    def format_size(size_bytes):
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def format_duration(seconds):
        """Format seconds to human readable."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"
    
    # Populate tree
    for record in history:
        status = record['status']
        status_display = "✅ Success" if status == "success" else "❌ Failed"
        
        tree.insert("", "end", values=(
            record['started_at'],
            record['connection_name'],
            record['databases'],
            status_display,
            format_size(record['backup_size']),
            format_duration(record['duration_seconds'])
        ))
    
    tree.pack(side="left", fill="both", expand=True)
    scrollbar_tree.pack(side="right", fill="y")
    
    # Close button
    close_btn = tk.Button(
        dialog,
        text="Close",
        command=dialog.destroy,
        bg=COLOR_TEXT_LIGHT,
        fg="white",
        font=("TkDefaultFont", 10, "bold"),
        relief="flat",
        padx=20,
        pady=8,
        cursor="hand2"
    )
    close_btn.pack(pady=10)


def show_backup_locations():
    """Show backup location manager dialog."""
    locations = db_manager.get_backup_locations()
    
    dialog = create_dialog(root, "Backup Locations", 600, 400, grab=True)
    
    # Header
    header = tk.Label(
        dialog,
        text="📁 Backup Locations",
        font=("TkDefaultFont", 14, "bold"),
        bg=COLOR_BG,
        fg=COLOR_TEXT,
        pady=10
    )
    header.pack()
    
    # List frame
    list_frame = tk.Frame(dialog, bg=COLOR_BG)
    list_frame.pack(fill="both", expand=True, padx=15, pady=10)
    
    canvas = tk.Canvas(list_frame, bg=COLOR_CARD, highlightthickness=1, highlightbackground=COLOR_BORDER)
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg=COLOR_CARD)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    def use_location(path):
        """Use selected backup location."""
        backup_dir_var.set(path)
        db_manager.save_backup_location("Last Used", path, is_default=True)
        dialog.destroy()
    
    def delete_location(loc_id, loc_name):
        """Delete a backup location."""
        if messagebox.askyesno("Confirm Delete", f"Delete location '{loc_name}'?"):
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM backup_locations WHERE id = ?", (loc_id,))
            conn.commit()
            conn.close()
            dialog.destroy()
            show_backup_locations()  # Refresh
    
    # Add location items
    for loc in locations:
        item_frame = tk.Frame(scrollable_frame, bg=COLOR_CARD, relief="flat")
        item_frame.pack(fill="x", padx=5, pady=5)
        
        info_frame = tk.Frame(item_frame, bg=COLOR_CARD)
        info_frame.pack(fill="x", padx=10, pady=8)
        
        name_text = f"⭐ {loc['name']}" if loc['is_default'] else loc['name']
        name_label = tk.Label(
            info_frame,
            text=name_text,
            font=("TkDefaultFont", 11, "bold"),
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            anchor="w"
        )
        name_label.pack(fill="x")
        
        path_label = tk.Label(
            info_frame,
            text=loc['path'],
            font=("TkDefaultFont", 9),
            bg=COLOR_CARD,
            fg=COLOR_TEXT_LIGHT,
            anchor="w"
        )
        path_label.pack(fill="x")
        
        # Buttons
        btn_frame = tk.Frame(item_frame, bg=COLOR_CARD)
        btn_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        use_btn = tk.Button(
            btn_frame,
            text="Use",
            command=lambda p=loc['path']: use_location(p),
            bg=COLOR_PRIMARY,
            fg="white",
            font=("TkDefaultFont", 9, "bold"),
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2"
        )
        use_btn.pack(side="left", padx=(0, 5))
        
        delete_btn = tk.Button(
            btn_frame,
            text="Delete",
            command=lambda lid=loc['id'], ln=loc['name']: delete_location(lid, ln),
            bg=COLOR_DANGER,
            fg="white",
            font=("TkDefaultFont", 9, "bold"),
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2"
        )
        delete_btn.pack(side="left")
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Close button
    close_btn = tk.Button(
        dialog,
        text="Close",
        command=dialog.destroy,
        bg=COLOR_TEXT_LIGHT,
        fg="white",
        font=("TkDefaultFont", 10, "bold"),
        relief="flat",
        padx=20,
        pady=8,
        cursor="hand2"
    )
    close_btn.pack(pady=10)


def refresh_connection_dropdown():
    """Refresh connection dropdown if it exists."""
    pass  # Placeholder for future dropdown implementation

def create_dialog(parent, title, width, height, grab=True):
    """Create a properly configured dialog window."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.configure(bg=COLOR_BG)
    dialog.transient(parent)
    if grab:
        dialog.grab_set()
    
    # Center the dialog
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
    y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")
    
    # Ensure dialog only closes itself, not the main app
    def on_dialog_close():
        if grab:
            dialog.grab_release()
        dialog.destroy()
    
    dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)
    
    return dialog


# Connection management buttons
conn_mgmt_frame = tk.Frame(connect_frame, bg=COLOR_CARD)
conn_mgmt_frame.pack(fill="x", pady=(10, 0))

save_conn_btn = tk.Button(
    conn_mgmt_frame,
    text="💾 Save Connection",
    command=save_current_connection,
    bg=COLOR_SECONDARY,
    fg="white",
    font=("TkDefaultFont", 9, "bold"),
    relief="flat",
    padx=15,
    pady=6,
    cursor="hand2",
    activebackground=COLOR_SECONDARY_HOVER,
)
save_conn_btn.pack(side="left", padx=(0, 5))

load_conn_btn = tk.Button(
    conn_mgmt_frame,
    text="📂 Load Connection",
    command=load_saved_connection,
    bg=COLOR_PRIMARY,
    fg="white",
    font=("TkDefaultFont", 9, "bold"),
    relief="flat",
    padx=15,
    pady=6,
    cursor="hand2",
    activebackground=COLOR_PRIMARY_HOVER,
)
load_conn_btn.pack(side="left", padx=(0, 5))

history_btn = tk.Button(
    conn_mgmt_frame,
    text="📊 Backup History",
    command=show_backup_history,
    bg=COLOR_TEXT_LIGHT,
    fg="white",
    font=("TkDefaultFont", 9, "bold"),
    relief="flat",
    padx=15,
    pady=6,
    cursor="hand2",
    activebackground=COLOR_TEXT,
)
history_btn.pack(side="left")

# Button frame
button_frame = tk.Frame(connect_frame, bg=COLOR_CARD)
button_frame.pack(fill="x", pady=(15, 0))

test_btn = create_styled_button(
    button_frame,
    "🔍 Test Connection",
    test_connection,
    color=COLOR_TEXT_LIGHT,
    hover_color=COLOR_TEXT,
    width=18,
)
test_btn.pack(side="left", padx=(0, 10))

connect_btn = create_styled_button(
    button_frame,
    "🚀 Connect & Load Databases",
    connect_and_load_databases,
    color=COLOR_PRIMARY,
    hover_color=COLOR_PRIMARY_HOVER,
    width=25,
)
connect_btn.pack(side="left")


# --- Backup panel (shown after successful connection) ---
backup_frame = create_card_frame(root, title="💾 Backup Configuration", padding=20)

# Connection status
status_card = tk.Frame(backup_frame, bg=COLOR_BG, relief="flat", borderwidth=1)
status_card.pack(fill="x", pady=(0, 15))

connection_label = tk.Label(
    status_card,
    text="Connected:",
    anchor="w",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_BG,
    fg=COLOR_TEXT,
    pady=10,
    padx=15,
)
connection_label.pack(fill="x")

# Backup folder selection
folder_card = create_card_frame(backup_frame, padding=15)
folder_card.pack(fill="x", pady=(0, 15))

folder_label = tk.Label(
    folder_card,
    text="📁 Backup Destination:",
    font=("TkDefaultFont", 10, "bold"),
    bg=COLOR_CARD,
    fg=COLOR_TEXT,
    anchor="w",
)
folder_label.pack(anchor="w", pady=(0, 8))

folder_frame = tk.Frame(folder_card, bg=COLOR_CARD)
folder_frame.pack(fill="x")

backup_entry = tk.Entry(
    folder_frame,
    textvariable=backup_dir_var,
    font=("TkDefaultFont", 10),
    relief="solid",
    borderwidth=1,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    highlightcolor=COLOR_PRIMARY,
    bg="white",
    fg=COLOR_TEXT,
)
backup_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

browse_btn = create_styled_button(
    folder_frame,
    "📂 Browse",
    choose_backup_folder,
    color=COLOR_SECONDARY,
    hover_color=COLOR_SECONDARY_HOVER,
    width=12,
)
browse_btn.pack(side="left", padx=(0, 5))

locations_btn = tk.Button(
    folder_frame,
    text="📋 Locations",
    command=show_backup_locations,
    bg=COLOR_TEXT_LIGHT,
    fg="white",
    font=("TkDefaultFont", 9, "bold"),
    relief="flat",
    padx=12,
    pady=8,
    cursor="hand2",
    activebackground=COLOR_TEXT,
)
locations_btn.pack(side="left")

# Database selection
db_card = create_card_frame(backup_frame, title="🗃️  Select Databases", padding=15)
db_card.pack(fill="both", expand=True, pady=(0, 15))

# Select all/none buttons
select_frame = tk.Frame(db_card, bg=COLOR_CARD)
select_frame.pack(fill="x", pady=(0, 10))

def select_all_databases():
    """Select all databases."""
    for var in db_vars.values():
        var.set(True)

def deselect_all_databases():
    """Deselect all databases."""
    for var in db_vars.values():
        var.set(False)

select_all_btn = tk.Button(
    select_frame,
    text="✓ Select All",
    command=select_all_databases,
    bg=COLOR_BG,
    fg=COLOR_TEXT,
    font=("TkDefaultFont", 9),
    relief="flat",
    padx=12,
    pady=4,
    cursor="hand2",
    activebackground=COLOR_BORDER,
)
select_all_btn.pack(side="left", padx=(0, 5))

deselect_all_btn = tk.Button(
    select_frame,
    text="✗ Deselect All",
    command=deselect_all_databases,
    bg=COLOR_BG,
    fg=COLOR_TEXT,
    font=("TkDefaultFont", 9),
    relief="flat",
    padx=12,
    pady=4,
    cursor="hand2",
    activebackground=COLOR_BORDER,
)
deselect_all_btn.pack(side="left")

# Scrollable database list
db_list_container = tk.Frame(db_card, bg=COLOR_CARD)
db_list_container.pack(fill="both", expand=True)

# Canvas and scrollbar for database list
db_canvas = tk.Canvas(
    db_list_container,
    bg=COLOR_BG,
    highlightthickness=1,
    highlightbackground=COLOR_BORDER,
    relief="flat",
)
db_scrollbar = ttk.Scrollbar(
    db_list_container,
    orient="vertical",
    command=db_canvas.yview,
)
db_list_canvas_frame = tk.Frame(db_canvas, bg=COLOR_BG)

def update_scroll_region(event=None):
    """Update the scroll region of the canvas."""
    db_canvas.update_idletasks()
    db_canvas.configure(scrollregion=db_canvas.bbox("all"))

db_list_canvas_frame.bind("<Configure>", update_scroll_region)

db_canvas_window = db_canvas.create_window((0, 0), window=db_list_canvas_frame, anchor="nw")
db_canvas.configure(yscrollcommand=db_scrollbar.set)

def configure_canvas_width(event):
    """Configure canvas width to match the frame."""
    canvas_width = event.width
    db_canvas.itemconfig(db_canvas_window, width=canvas_width)

db_canvas.bind("<Configure>", configure_canvas_width)

db_canvas.pack(side="left", fill="both", expand=True)
db_scrollbar.pack(side="right", fill="y")

# Bind mouse wheel to canvas (Windows/Mac)
def _on_mousewheel(event):
    db_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

# Bind mouse wheel to canvas (Linux)
def _on_mousewheel_linux(event):
    if event.num == 4:
        db_canvas.yview_scroll(-1, "units")
    elif event.num == 5:
        db_canvas.yview_scroll(1, "units")

db_canvas.bind_all("<MouseWheel>", _on_mousewheel)
db_canvas.bind_all("<Button-4>", _on_mousewheel_linux)
db_canvas.bind_all("<Button-5>", _on_mousewheel_linux)

# Backup button
backup_button_frame = tk.Frame(backup_frame, bg=COLOR_CARD)
backup_button_frame.pack(fill="x", pady=(10, 0))

btn_backup = create_styled_button(
    backup_button_frame,
    "💾 Backup Selected Databases",
    backup_selected_databases,
    color=COLOR_SECONDARY,
    hover_color=COLOR_SECONDARY_HOVER,
    width=30,
)
btn_backup.pack()

# --- Loading spinner / status area (hidden by default, shown via set_busy) ---
progress_frame = tk.Frame(root, bg=COLOR_BG, relief="flat", borderwidth=1)
progress_frame.pack(fill="x", side="bottom", padx=0, pady=0)

progress_inner = tk.Frame(progress_frame, bg=COLOR_BG)
progress_inner.pack(fill="x", padx=15, pady=10)

progress_bar = ttk.Progressbar(
    progress_inner,
    mode="indeterminate",
    length=200,
    style="TProgressbar",
)
progress_bar.pack(side="left", padx=(0, 10))

status_label = tk.Label(
    progress_inner,
    textvariable=status_var,
    font=("TkDefaultFont", 10),
    bg=COLOR_BG,
    fg=COLOR_TEXT,
    anchor="w",
)
status_label.pack(side="left", fill="x", expand=True)

# Configure ttk style for progress bar
style = ttk.Style()
style.theme_use("default")
style.configure(
    "TProgressbar",
    background=COLOR_PRIMARY,
    troughcolor=COLOR_BORDER,
    borderwidth=0,
    lightcolor=COLOR_PRIMARY,
    darkcolor=COLOR_PRIMARY,
)

# Auto-load last used backup location
def auto_load_settings():
    """Auto-load last used settings on startup."""
    # Load default backup location
    default_location = db_manager.get_default_backup_location()
    if default_location and os.path.exists(default_location):
        backup_dir_var.set(default_location)
    
    # Optionally load last used connection (commented out by default)
    # Uncomment if you want to auto-load last connection
    # last_connections = db_manager.get_connections(favorites_only=True)
    # if last_connections:
    #     conn = last_connections[0]
    #     if conn['socket_path']:
    #         server_var.set(conn['socket_path'])
    #     else:
    #         server_var.set(conn['host'] or "localhost")
    #         port_override_var.set(conn['port'] or "3306")
    #     user_var.set(conn['username'])
    #     password_var.set(conn['password'])

# Initialize settings
root.after(100, auto_load_settings)

root.mainloop()



