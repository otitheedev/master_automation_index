import tkinter as tk
from tkinter import messagebox, filedialog, ttk, simpledialog
import webbrowser, sqlite3, time
from datetime import datetime, timedelta
import pytz, os
import sys
import json
import re
import shutil
from pathlib import Path
import urllib.request
import urllib.parse
import hashlib
import uuid
import subprocess  # For MP3 playback
from playsound import playsound
import threading
import ftplib
from urllib.parse import urlparse
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# Windows-only sound module (not available on Linux/Mac)
try:
    import winsound
except ImportError:
    winsound = None


APP_NAME = "DailyDashboard"
SETTINGS_FILE = "settings.json"

def settings_path() -> str:
    return os.path.join(get_app_data_dir(), SETTINGS_FILE)

DEFAULT_SETTINGS = {
    "theme": "light",  # light | dark
    "sync_enabled": False,
    "sync_type": "http",  # http | ftp | s3
    "sync_server_url": "http://127.0.0.1:8765",
    "sync_user": "default",
    "sync_token": "",
    "sync_interval_sec": 60,
    "sync_conflict": "prefer_newer",  # prefer_local | prefer_server | prefer_newer
    # FTP settings
    "sync_ftp_host": "",
    "sync_ftp_port": 21,
    "sync_ftp_user": "",
    "sync_ftp_pass": "",
    "sync_ftp_path": "/",
    # S3 settings
    "sync_s3_bucket": "",
    "sync_s3_key": "taskmask.db",
    "sync_s3_region": "us-east-1",
    "sync_s3_access_key": "",
    "sync_s3_secret_key": "",
}

def load_settings() -> dict:
    try:
        os.makedirs(get_app_data_dir(), exist_ok=True)
        p = settings_path()
        if not os.path.exists(p):
            return dict(DEFAULT_SETTINGS)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return merged
    except Exception as e:
        print(f"Settings load warning: {e}")
        return dict(DEFAULT_SETTINGS)

def save_settings(settings: dict) -> None:
    try:
        os.makedirs(get_app_data_dir(), exist_ok=True)
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Settings save warning: {e}")

# ----------- OPTIONAL SERVER SYNC (DB FILE LEVEL) -----------
sync_in_progress = False
last_sync_message = ""

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _join_url(base: str, path: str, query: dict) -> str:
    base = base.rstrip("/")
    url = f"{base}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return url

def http_get_json(url: str, headers: dict | None = None, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data)

def http_download_bytes(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def http_post_bytes(url: str, body: bytes, headers: dict | None = None, timeout: int = 30) -> dict:
    hdrs = {"Content-Type": "application/octet-stream"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, method="POST", headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data) if data else {"ok": True}

def sync_ftp() -> str:
    """FTP sync. Returns human message."""
    host = (settings.get("sync_ftp_host") or "").strip()
    port = int(settings.get("sync_ftp_port") or 21)
    user = (settings.get("sync_ftp_user") or "").strip()
    password = (settings.get("sync_ftp_pass") or "").strip()
    remote_path = (settings.get("sync_ftp_path") or "/").strip().rstrip("/")
    conflict = settings.get("sync_conflict", "prefer_newer")
    
    if not host or not user:
        return "FTP sync: missing host or username"
    
    remote_file = f"{remote_path}/taskmask.db"
    local_exists = os.path.exists(DB_NAME)
    local_mtime = os.path.getmtime(DB_NAME) if local_exists else 0
    local_sha = sha256_file(DB_NAME) if local_exists else ""
    
    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=10)
        ftp.login(user, password)
        
        # Check if remote file exists and get its mtime
        server_exists = False
        server_mtime = 0
        server_sha = ""
        try:
            size = ftp.size(remote_file)
            if size is not None and size > 0:
                server_exists = True
                # Get modification time (MDTM may not be supported by all servers)
                try:
                    mdtm = ftp.voidcmd(f"MDTM {remote_file}")
                    # MDTM response: "213 20250115120000"
                    if mdtm.startswith("213"):
                        time_str = mdtm.split()[1]
                        server_mtime = datetime.strptime(time_str, "%Y%m%d%H%M%S").timestamp()
                except:
                    # If MDTM fails, use current time as fallback
                    server_mtime = time.time()
        except:
            pass
        
        # If server has nothing, upload local (if any)
        if not server_exists:
            if not local_exists:
                ftp.quit()
                return "FTP sync: nothing to upload/download"
            with open(DB_NAME, "rb") as f:
                ftp.storbinary(f"STOR {remote_file}", f)
            ftp.quit()
            return "FTP sync: uploaded (server was empty)"
        
        # Download remote file to compare
        tmp_remote = DB_NAME + ".remote.tmp"
        with open(tmp_remote, "wb") as f:
            ftp.retrbinary(f"RETR {remote_file}", f.write)
        server_sha = sha256_file(tmp_remote)
        
        # If identical, nothing to do
        if local_exists and local_sha and server_sha and local_sha == server_sha:
            os.remove(tmp_remote)
            ftp.quit()
            return "FTP sync: up-to-date"
        
        # Decide direction
        direction = "download"
        if conflict == "prefer_local":
            direction = "upload"
        elif conflict == "prefer_server":
            direction = "download"
        else:  # prefer_newer
            direction = "upload" if local_mtime >= server_mtime else "download"
        
        if direction == "download":
            os.replace(tmp_remote, DB_NAME)
            ftp.quit()
            init_db()
            return "FTP sync: downloaded server DB"
        else:
            os.remove(tmp_remote)
            if not local_exists:
                ftp.quit()
                return "FTP sync: local DB missing"
            with open(DB_NAME, "rb") as f:
                ftp.storbinary(f"STOR {remote_file}", f)
            ftp.quit()
            return "FTP sync: uploaded local DB"
    except Exception as e:
        return f"FTP sync error: {e}"

def sync_s3() -> str:
    """S3 sync. Returns human message."""
    if not S3_AVAILABLE:
        return "S3 sync: boto3 not installed. Run: pip install boto3"
    
    bucket = (settings.get("sync_s3_bucket") or "").strip()
    key = (settings.get("sync_s3_key") or "taskmask.db").strip()
    region = (settings.get("sync_s3_region") or "us-east-1").strip()
    access_key = (settings.get("sync_s3_access_key") or "").strip()
    secret_key = (settings.get("sync_s3_secret_key") or "").strip()
    conflict = settings.get("sync_conflict", "prefer_newer")
    
    if not bucket or not access_key or not secret_key:
        return "S3 sync: missing bucket, access key, or secret key"
    
    local_exists = os.path.exists(DB_NAME)
    local_mtime = os.path.getmtime(DB_NAME) if local_exists else 0
    local_sha = sha256_file(DB_NAME) if local_exists else ""
    
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # Check if remote file exists
        server_exists = False
        server_mtime = 0
        server_sha = ""
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            server_exists = True
            server_mtime = head["LastModified"].timestamp()
        except ClientError as e:
            if e.response["Error"]["Code"] != "404":
                raise
        
        # If server has nothing, upload local (if any)
        if not server_exists:
            if not local_exists:
                return "S3 sync: nothing to upload/download"
            s3.upload_file(DB_NAME, bucket, key)
            return "S3 sync: uploaded (server was empty)"
        
        # Download remote file to compare
        tmp_remote = DB_NAME + ".remote.tmp"
        s3.download_file(bucket, key, tmp_remote)
        server_sha = sha256_file(tmp_remote)
        
        # If identical, nothing to do
        if local_exists and local_sha and server_sha and local_sha == server_sha:
            os.remove(tmp_remote)
            return "S3 sync: up-to-date"
        
        # Decide direction
        direction = "download"
        if conflict == "prefer_local":
            direction = "upload"
        elif conflict == "prefer_server":
            direction = "download"
        else:  # prefer_newer
            direction = "upload" if local_mtime >= server_mtime else "download"
        
        if direction == "download":
            os.replace(tmp_remote, DB_NAME)
            init_db()
            return "S3 sync: downloaded server DB"
        else:
            os.remove(tmp_remote)
            if not local_exists:
                return "S3 sync: local DB missing"
            s3.upload_file(DB_NAME, bucket, key)
            return "S3 sync: uploaded local DB"
    except NoCredentialsError:
        return "S3 sync: invalid credentials"
    except Exception as e:
        return f"S3 sync error: {e}"

def sync_http() -> str:
    """HTTP sync (original). Returns human message."""
    server = (settings.get("sync_server_url") or "").strip()
    user = (settings.get("sync_user") or "default").strip() or "default"
    token = (settings.get("sync_token") or "").strip()
    conflict = settings.get("sync_conflict", "prefer_newer")

    if not server:
        return "HTTP sync: missing server URL"

    headers = {}
    if token:
        headers["X-Token"] = token

    meta_url = _join_url(server, "/api/meta", {"user": user})
    db_url = _join_url(server, "/api/db", {"user": user})

    local_exists = os.path.exists(DB_NAME)
    local_mtime = os.path.getmtime(DB_NAME) if local_exists else 0
    local_sha = sha256_file(DB_NAME) if local_exists else ""

    try:
        server_meta = http_get_json(meta_url, headers=headers, timeout=10)
    except Exception:
        server_meta = {"exists": False}

    server_exists = bool(server_meta.get("exists"))
    server_mtime = float(server_meta.get("mtime", 0) or 0)
    server_sha = str(server_meta.get("sha256", "") or "")

    # If server has nothing, upload local (if any)
    if not server_exists:
        if not local_exists:
            return "HTTP sync: nothing to upload/download"
        with open(DB_NAME, "rb") as f:
            body = f.read()
        resp = http_post_bytes(db_url, body, headers=headers, timeout=30)
        return "HTTP sync: uploaded (server was empty)" if resp.get("ok", True) else "HTTP sync: upload failed"

    # If identical, nothing to do
    if local_exists and local_sha and server_sha and local_sha == server_sha:
        return "HTTP sync: up-to-date"

    # Decide direction
    direction = "download"
    if conflict == "prefer_local":
        direction = "upload"
    elif conflict == "prefer_server":
        direction = "download"
    else:  # prefer_newer
        direction = "upload" if local_mtime >= server_mtime else "download"

    if direction == "download":
        data = http_download_bytes(db_url, headers=headers, timeout=30)
        tmp = DB_NAME + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, DB_NAME)
        init_db()
        return "HTTP sync: downloaded server DB"
    else:
        if not local_exists:
            return "HTTP sync: local DB missing"
        with open(DB_NAME, "rb") as f:
            body = f.read()
        resp = http_post_bytes(db_url, body, headers=headers, timeout=30)
        return "HTTP sync: uploaded local DB" if resp.get("ok", True) else "HTTP sync: upload failed"

def sync_once() -> str:
    """One sync attempt. Routes to appropriate sync method based on sync_type."""
    sync_type = settings.get("sync_type", "http").lower()
    if sync_type == "ftp":
        return sync_ftp()
    elif sync_type == "s3":
        return sync_s3()
    else:  # http
        return sync_http()

def sync_once_async():
    global sync_in_progress, last_sync_message
    if sync_in_progress:
        return
    sync_in_progress = True
    status_var.set("Sync: running...")

    def _run():
        global sync_in_progress, last_sync_message
        try:
            msg = sync_once()
            last_sync_message = msg
        except Exception as e:
            last_sync_message = f"Sync error: {e}"
        finally:
            sync_in_progress = False
            # Refresh UI on main thread
            def _done():
                try:
                    refresh_links()
                    refresh_notes()
                    load_todo_data_from_db()
                    refresh_todo_tree()
                    update_status_bar()
                    status_var.set(f"{last_sync_message}")
                except Exception:
                    pass
            root.after(0, _done)

    threading.Thread(target=_run, daemon=True).start()

def schedule_auto_sync():
    if settings.get("sync_enabled"):
        interval = int(settings.get("sync_interval_sec") or 60)
        interval = max(10, interval)
        sync_once_async()
        root.after(interval * 1000, schedule_auto_sync)

def _resource_base_dir() -> str:
    """Best-effort base folder for resources (icon/assets) for script vs onefile executable."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.getcwd()

def resource_path(*parts: str) -> str:
    return os.path.join(_resource_base_dir(), *parts)

def get_app_data_dir() -> str:
    """Returns a writable per-user folder (Windows: %APPDATA%\\DailyDashboard)."""
    appdata = os.environ.get("APPDATA")
    base = appdata if appdata else str(Path.home())
    return os.path.join(base, APP_NAME)

def get_db_path() -> str:
    """
    DB location strategy:
    - If a 'portable.txt' file exists next to task.py, keep DB in ./database (portable mode).
    - Otherwise use %APPDATA%\\DailyDashboard\\database\\taskmask.db
    - One-time migration from legacy hardcoded folder if present.
    """
    portable_flag = os.path.join(os.getcwd(), "portable.txt")
    if os.path.exists(portable_flag):
        db_dir = os.path.join(os.getcwd(), "database")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "taskmask.db")

    app_dir = get_app_data_dir()
    db_dir = os.path.join(app_dir, "database")
    os.makedirs(db_dir, exist_ok=True)
    new_db = os.path.join(db_dir, "taskmask.db")

    # Legacy migration (old hardcoded path)
    legacy_db = os.path.join(r"C:\YAMiN\database", "taskmask.db")
    try:
        if not os.path.exists(new_db) and os.path.exists(legacy_db):
            shutil.copy2(legacy_db, new_db)
    except Exception as e:
        print(f"DB migration warning: {e}")

    return new_db

DB_NAME = get_db_path()
os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)

# Global set to track overdue tasks that have already played sound
overdue_sound_played = set()

# Global variables for blinking effect
blinking_tasks = set()  # Track which tasks are currently blinking
blink_state = True  # Toggle for blinking effect

# In-memory todo model (uuid -> row), rendered in a Treeview (table)
todo_data: dict[str, dict] = {}  # uuid -> {task, done, deadline, done_at, created_at}

# Global icon path
ICON_PATH = resource_path("icon.ico")

# Import shared icon utility
from icon_utils import set_window_icon as set_icon_shared

# ----------- TASK LISTBOX FORMATTING -----------
DEADLINE_RAW_FMT = "%Y-%m-%d %H:%M"
DEADLINE_DISPLAY_FMT = "%d %B %y, %I:%M %p"
_DEADLINE_RAW_RE = re.compile(r"⏰\s*\[(?P<raw>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]")

TS_FMT = "%Y-%m-%d %H:%M:%S"
CREATED_DISPLAY_FMT = "%d %b %Y, %I:%M %p"  # e.g. 15 Feb 2025, 10:00 PM
_CREATED_SUFFIX_RE = re.compile(r"\s*\(\d{2}\s+[A-Za-z]{3}\s+\d{4},\s+\d{2}:\d{2}\s+(?:AM|PM)\)\s*$")

def now_ts() -> str:
    return datetime.now().strftime(TS_FMT)

def parse_todo_listbox_item(item: str) -> tuple[str, bool, str]:
    """Return (task_text, done, deadline_raw_or_empty)."""
    done = item.startswith("✅")
    base = item[2:].strip() if len(item) >= 2 else item.strip()
    task_part = base.split("⏰")[0].strip()
    # Remove created-at suffix displayed as "(15 Feb 2025, 10:00 PM)"
    task_part = _CREATED_SUFFIX_RE.sub("", task_part).strip()

    m = _DEADLINE_RAW_RE.search(item)
    deadline_raw = m.group("raw") if m else ""
    return task_part, done, deadline_raw

def _deadline_status(deadline_raw: str) -> tuple[datetime | None, timedelta | None, bool]:
    if not deadline_raw:
        return None, None, False
    try:
        dt = datetime.strptime(deadline_raw, DEADLINE_RAW_FMT)
    except ValueError:
        return None, None, False
    delta = dt - datetime.now()
    return dt, delta, delta.total_seconds() <= 0

def _format_created_display(created_at: str) -> str:
    try:
        dt = datetime.strptime(created_at, TS_FMT)
        return dt.strftime(CREATED_DISPLAY_FMT)
    except Exception:
        return ""

def format_todo_listbox_item(task_text: str, done: bool, deadline_raw: str, created_at: str | None = None) -> str:
    checkbox = "✅" if done else "☐"
    task_text = task_text.strip()
    created_disp = _format_created_display(created_at or "")
    created_suffix = f" ({created_disp})" if created_disp else ""

    if not deadline_raw:
        return f"{checkbox} {task_text}{created_suffix}"

    dt, delta, is_overdue = _deadline_status(deadline_raw)
    if not dt or not delta:
        return f"{checkbox} {task_text}{created_suffix} ⏰ [{deadline_raw}]"

    pretty = dt.strftime(DEADLINE_DISPLAY_FMT)
    if is_overdue:
        return f"{checkbox} {task_text}{created_suffix} ⏰ [{deadline_raw}] {pretty} (OVERDUE!)"

    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        left = f"{days} days left"
    elif hours > 0:
        left = f"{hours} hours left"
    else:
        left = f"{minutes} min left"
    return f"{checkbox} {task_text}{created_suffix} ⏰ [{deadline_raw}] {pretty} ({left})"

# ----------- TODO TREEVIEW (TABLE) -----------
def _format_deadline_display(deadline_raw: str) -> str:
    if not deadline_raw:
        return ""
    try:
        dt = datetime.strptime(deadline_raw, DEADLINE_RAW_FMT)
        return dt.strftime(DEADLINE_DISPLAY_FMT)
    except Exception:
        return deadline_raw

def _format_time_left(deadline_raw: str, done: bool) -> tuple[str, str]:
    """
    Returns (time_left_text, tag) where tag controls row coloring.
    tag in {"done","overdue","soon","today","future","none"}
    """
    if done:
        return ("Done", "done")
    if not deadline_raw:
        return ("", "none")
    dt, delta, is_overdue = _deadline_status(deadline_raw)
    if not dt or not delta:
        return ("", "none")
    if is_overdue:
        return ("OVERDUE", "overdue")
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        return (f"{days}d {hours}h left", "future")
    if hours > 0:
        tag = "soon" if hours < 2 else "today"
        return (f"{hours}h {minutes}m left", tag)
    return (f"{minutes}m left", "soon")

def todo_tree_row_values(uuid_val: str) -> tuple[str, str, str, str, str]:
    row = todo_data.get(uuid_val, {})
    done = bool(row.get("done"))
    task = str(row.get("task") or "")
    created = _format_created_display(str(row.get("created_at") or ""))
    deadline_raw = str(row.get("deadline") or "")
    deadline = _format_deadline_display(deadline_raw)
    left, _tag = _format_time_left(deadline_raw, done)
    status = "✅" if done else "☐"
    return (status, task, created, deadline, left)

def refresh_todo_tree(selection_uuid: str | None = None):
    """Rebuild the todo Treeview from todo_data and keep selection if possible."""
    if "todo_tree" not in globals():
        return
    # Preserve order by order_index
    ordered = sorted(todo_data.items(), key=lambda kv: kv[1].get("order_index", 0))
    todo_tree.delete(*todo_tree.get_children())
    for idx, (uuid_val, row) in enumerate(ordered):
        row["order_index"] = idx
        todo_data[uuid_val] = row
        values = todo_tree_row_values(uuid_val)
        deadline_raw = str(row.get("deadline") or "")
        left, tag = _format_time_left(deadline_raw, bool(row.get("done")))
        todo_tree.insert("", "end", iid=uuid_val, values=values, tags=(tag,))
    _configure_todo_tree_tags()
    if selection_uuid and selection_uuid in todo_data:
        try:
            todo_tree.selection_set(selection_uuid)
            todo_tree.see(selection_uuid)
        except Exception:
            pass

def _configure_todo_tree_tags():
    try:
        todo_tree.tag_configure("done", foreground="#1e7e34")
        todo_tree.tag_configure("overdue", foreground="#b02a37")
        todo_tree.tag_configure("soon", foreground="#d9831f")
        todo_tree.tag_configure("today", foreground="#0b5ed7")
        todo_tree.tag_configure("future", foreground="#111")
        todo_tree.tag_configure("none", foreground="#111")
    except Exception:
        pass

def get_selected_todo_uuid() -> str | None:
    if "todo_tree" not in globals():
        return None
    sel = todo_tree.selection()
    return sel[0] if sel else None

def apply_todo_item_style(index: int, done: bool, deadline_raw: str):
    """Set listbox item fg/bg based on done + deadline urgency (keeps selected highlight handled elsewhere)."""
    # Legacy listbox styling (todo UI is now a Treeview table). Keep safe no-op.
    # This function is deprecated as we now use Treeview instead of Listbox
    # Styling is handled directly in refresh_todo_tree()
    pass

def set_window_icon(window):
    """Set icon for a window if icon file exists - uses shared icon utility"""
    set_icon_shared(window)

def center_window_relative_to_parent(child_window, width, height):
    """Center a child window relative to the main root window"""
    child_window.update_idletasks()
    # Get parent window (root) position and size
    root_x = root.winfo_x()
    root_y = root.winfo_y()
    root_width = root.winfo_width()
    root_height = root.winfo_height()
    
    # Calculate center position relative to parent
    center_x = root_x + (root_width // 2) - (width // 2)
    center_y = root_y + (root_height // 2) - (height // 2)
    
    # Ensure window stays on screen
    screen_width = child_window.winfo_screenwidth()
    screen_height = child_window.winfo_screenheight()
    center_x = max(0, min(center_x, screen_width - width))
    center_y = max(0, min(center_y, screen_height - height))
    
    child_window.geometry(f"{width}x{height}+{center_x}+{center_y}")

def create_scrolled_listbox(parent, **kwargs):
    frame = tk.Frame(parent, bg="white")
    frame.pack(fill="both", expand=True, padx=kwargs.pop('padx', 0), pady=kwargs.pop('pady', 0))
    
    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")
    
    listbox = tk.Listbox(frame, **kwargs)
    listbox.pack(side="left", fill="both", expand=True)
    
    scrollbar.config(command=listbox.yview)
    listbox.config(yscrollcommand=scrollbar.set)
    
    return listbox

def add_placeholder(entry, placeholder):
    placeholder_color = '#aaa'
    default_color = entry['fg']

    def on_focus_in(event):
        if entry.get() == placeholder:
            entry.delete(0, tk.END)
            entry.config(fg=default_color)

    def on_focus_out(event):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg=placeholder_color)

    entry.insert(0, placeholder)
    entry.config(fg=placeholder_color)
    entry.bind('<FocusIn>', on_focus_in)
    entry.bind('<FocusOut>', on_focus_out)

# ----------- DATABASE SETUP -----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Create todos table with new schema
    c.execute('''CREATE TABLE IF NOT EXISTS todos 
                 (id INTEGER PRIMARY KEY, 
                  uuid TEXT,
                  task TEXT, 
                  done INTEGER,
                  deadline TEXT,
                  done_at TEXT,
                  order_index INTEGER DEFAULT 0,
                  created_at TEXT)''')
    
    # Check if deadline column exists, if not add it
    c.execute("PRAGMA table_info(todos)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'deadline' not in columns:
        c.execute("ALTER TABLE todos ADD COLUMN deadline TEXT")

    if 'uuid' not in columns:
        c.execute("ALTER TABLE todos ADD COLUMN uuid TEXT")
    if 'done_at' not in columns:
        c.execute("ALTER TABLE todos ADD COLUMN done_at TEXT")
    if 'order_index' not in columns:
        c.execute("ALTER TABLE todos ADD COLUMN order_index INTEGER DEFAULT 0")
    
    if 'created_at' not in columns:
        c.execute("ALTER TABLE todos ADD COLUMN created_at TEXT")
        # Update existing rows with current timestamp
        c.execute("UPDATE todos SET created_at = datetime('now') WHERE created_at IS NULL")

    # Archive table for completed tasks (auto-moved after 12h)
    c.execute('''CREATE TABLE IF NOT EXISTS archive_todos
                 (id INTEGER PRIMARY KEY,
                  uuid TEXT UNIQUE,
                  task TEXT,
                  done_at TEXT,
                  deadline TEXT,
                  created_at TEXT,
                  archived_at TEXT)''')
    
    # Create notes table with new schema
    c.execute('''CREATE TABLE IF NOT EXISTS notes 
                 (id INTEGER PRIMARY KEY,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  order_index INTEGER DEFAULT 0)''')
    
    # Check if order_index column exists, if not add it
    c.execute("PRAGMA table_info(notes)")
    note_columns = [column[1] for column in c.fetchall()]
    
    if 'order_index' not in note_columns:
        c.execute("ALTER TABLE notes ADD COLUMN order_index INTEGER DEFAULT 0")
    
    # Create links table with new schema
    c.execute('''CREATE TABLE IF NOT EXISTS links 
                 (id INTEGER PRIMARY KEY, 
                  name TEXT, 
                  url TEXT,
                  order_index INTEGER DEFAULT 0)''')
    
    # Check if order_index column exists, if not add it
    c.execute("PRAGMA table_info(links)")
    link_columns = [column[1] for column in c.fetchall()]
    
    if 'order_index' not in link_columns:
        c.execute("ALTER TABLE links ADD COLUMN order_index INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()

def load_todos():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT uuid, task, done, deadline, done_at, created_at, order_index FROM todos ORDER BY order_index ASC, created_at ASC")
    todos = c.fetchall()
    conn.close()
    return todos

def load_todo_data_from_db():
    """Populate in-memory todo_data from DB rows (used at startup / after restore/sync)."""
    todo_data.clear()
    for uuid_val, task, done, deadline, done_at, created_at, order_index in load_todos():
        uuid_val = uuid_val or str(uuid.uuid4())
        todo_data[uuid_val] = {
            "task": task or "",
            "done": bool(done),
            "deadline": deadline or "",
            "done_at": done_at or "",
            "created_at": created_at or now_ts(),
            "order_index": int(order_index or 0),
        }

def persist_todos_to_db(todo_order: list[str]):
    """Persist all todos in the given order_index order (simple & reliable)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM todos")
    for idx, uuid_val in enumerate(todo_order):
        row = todo_data.get(uuid_val)
        if not row:
            continue
        c.execute(
            "INSERT INTO todos (uuid, task, done, deadline, done_at, created_at, order_index) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                uuid_val,
                row.get("task", ""),
                1 if row.get("done") else 0,
                row.get("deadline", ""),
                row.get("done_at", ""),
                row.get("created_at", now_ts()),
                idx,
            ),
        )
    conn.commit()
    conn.close()

def save_todos(todo_listbox):
    # Backward-compatible stub (todo_listbox no longer the primary UI).
    # If old code paths call this, keep DB consistent by reloading UI from DB later.
    try:
        # Best effort: persist current in-memory model in its current order.
        if "todo_tree" in globals():
            order = list(todo_tree.get_children())
        else:
            order = sorted(todo_data.keys(), key=lambda u: todo_data[u].get("order_index", 0))
        persist_todos_to_db(order)
    except Exception as e:
        print(f"save_todos warning: {e}")

def load_links():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, name, url, order_index FROM links ORDER BY order_index ASC")
    links = c.fetchall()
    conn.close()
    return links

def save_link(name, url):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT MAX(order_index) FROM links")
    max_order = c.fetchone()[0] or 0
    c.execute("INSERT INTO links (name, url, order_index) VALUES (?, ?, ?)", (name, url, max_order + 1))
    conn.commit()
    conn.close()

def delete_link(link_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()

def update_link_order(link_id, new_order):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE links SET order_index = ? WHERE id = ?", (new_order, link_id))
    conn.commit()
    conn.close()

def save_note(title, content):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT MAX(order_index) FROM notes")
    max_order = c.fetchone()[0] or 0
    c.execute("INSERT INTO notes (title, content, order_index) VALUES (?, ?, ?)", (title, content, max_order + 1))
    conn.commit()
    conn.close()

def delete_note(note_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()

def update_note_order(note_id, new_order):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE notes SET order_index = ? WHERE id = ?", (new_order, note_id))
    conn.commit()
    conn.close()

def update_note(note_id, title, content):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE notes SET title = ?, content = ? WHERE id = ?", (title, content, note_id))
    conn.commit()
    conn.close()

def get_all_notes():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, title, content, created_at, order_index FROM notes ORDER BY order_index ASC")
    notes = c.fetchall()
    conn.close()
    return notes

# ----------- REORDERING FUNCTIONS -----------
def move_up(listbox, save_func, update_order_func, items_data):
    selection = listbox.curselection()
    if selection and selection[0] > 0:
        index = selection[0]
        text = listbox.get(index)
        listbox.delete(index)
        listbox.insert(index - 1, text)
        listbox.selection_set(index - 1)
        
        # Update order in database
        if items_data:
            item_id = items_data[index][0]  # Assuming first element is ID
            update_order_func(item_id, index)
        save_func(listbox)

def move_down(listbox, save_func, update_order_func, items_data):
    selection = listbox.curselection()
    if selection and selection[0] < listbox.size() - 1:
        index = selection[0]
        text = listbox.get(index)
        listbox.delete(index)
        listbox.insert(index + 1, text)
        listbox.selection_set(index + 1)
        
        # Update order in database
        if items_data:
            item_id = items_data[index][0]  # Assuming first element is ID
            update_order_func(item_id, index + 2)
        save_func(listbox)

# ----------- TIMER FUNCTIONS -----------
def add_timer_window(selected_uuid: str | None = None):
    selected_uuid = selected_uuid or get_selected_todo_uuid()
    if not selected_uuid or selected_uuid not in todo_data:
        messagebox.showwarning("No Task Selected", "Please select a task first before adding a timer.")
        return
    
    timer_window = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    timer_window.withdraw()
    timer_window.title("Set Deadline")
    timer_window.config(bg="#f5f7fa")
    timer_window.resizable(False, False)
    
    # Set icon for timer window
    set_window_icon(timer_window)
    
    # Center window relative to main window
    center_window_relative_to_parent(timer_window, 500, 600)
    timer_window.deiconify()
    
    # Make modal
    timer_window.transient(root)
    timer_window.grab_set()
    
    # Main container with padding
    container = tk.Frame(timer_window, bg="#f5f7fa")
    container.pack(fill="both", expand=True, padx=30, pady=30)
    
    # Header section with icon and title
    header_frame = tk.Frame(container, bg="#f5f7fa")
    header_frame.pack(fill="x", pady=(0, 25))
    
    title_label = tk.Label(header_frame, text="⏰ Set Deadline", 
                          font=("Segoe UI", 20, "bold"), bg="#f5f7fa", fg="#1a1a1a")
    title_label.pack()
    
    # Task card (modern card design)
    task_card = tk.Frame(container, bg="white", relief="flat", bd=0)
    task_card.pack(fill="x", pady=(0, 20))
    
    task_text = str(todo_data[selected_uuid].get("task") or "")
    task_label = tk.Label(task_card, text=task_text, 
                          font=("Segoe UI", 12), bg="white", fg="#333",
                          wraplength=350, justify="left", padx=20, pady=15)
    task_label.pack()
    
    # Date section
    date_section = tk.Frame(container, bg="#f5f7fa")
    date_section.pack(fill="x", pady=(0, 15))
    
    tk.Label(date_section, text="Date", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
    
    date_entry = tk.Entry(date_section, font=("Segoe UI", 12), 
                         relief="flat", bd=0, bg="white", fg="#333",
                         insertbackground="#333", highlightthickness=1,
                         highlightbackground="#ddd", highlightcolor="#007bff")
    date_entry.pack(fill="x", ipady=12, padx=0)
    date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
    
    # Time section
    time_section = tk.Frame(container, bg="#f5f7fa")
    time_section.pack(fill="x", pady=(0, 20))
    
    tk.Label(time_section, text="Time", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
    
    time_input_frame = tk.Frame(time_section, bg="white", relief="flat", bd=0,
                                highlightthickness=1, highlightbackground="#ddd", highlightcolor="#007bff")
    time_input_frame.pack(fill="x")
    
    # Hour
    hour_var = tk.StringVar(value=str(datetime.now().hour % 12 or 12))
    hour_spinbox = tk.Spinbox(time_input_frame, from_=1, to=12, width=4,
                              textvariable=hour_var, font=("Segoe UI", 13, "bold"),
                              relief="flat", bd=0, bg="white", fg="#333",
                              highlightthickness=0, justify="center")
    hour_spinbox.pack(side="left", padx=(15, 5), pady=12)
    
    tk.Label(time_input_frame, text=":", bg="white", font=("Segoe UI", 16, "bold"), 
             fg="#666").pack(side="left", padx=2)
    
    # Minute
    minute_var = tk.StringVar(value=f"{datetime.now().minute:02d}")
    minute_spinbox = tk.Spinbox(time_input_frame, from_=0, to=59, width=4,
                                textvariable=minute_var, font=("Segoe UI", 13, "bold"),
                                relief="flat", bd=0, bg="white", fg="#333",
                                highlightthickness=0, justify="center",
                                format="%02.0f")
    minute_spinbox.pack(side="left", padx=5, pady=12)
    
    # AM/PM
    ampm_var = tk.StringVar(value="PM" if datetime.now().hour >= 12 else "AM")
    ampm_frame = tk.Frame(time_input_frame, bg="white")
    ampm_frame.pack(side="left", padx=(15, 15), pady=12)
    
    ampm_btn_am = tk.Button(ampm_frame, text="AM", command=lambda: ampm_var.set("AM"),
                           font=("Segoe UI", 10, "bold"), bg="#f0f0f0", fg="#666",
                           relief="flat", bd=0, padx=10, pady=5,
                           activebackground="#e0e0e0", activeforeground="#333")
    ampm_btn_am.pack(side="left", padx=(0, 2))
    
    ampm_btn_pm = tk.Button(ampm_frame, text="PM", command=lambda: ampm_var.set("PM"),
                           font=("Segoe UI", 10, "bold"), bg="#f0f0f0", fg="#666",
                           relief="flat", bd=0, padx=10, pady=5,
                           activebackground="#e0e0e0", activeforeground="#333")
    ampm_btn_pm.pack(side="left")
    
    def update_ampm_style():
        if ampm_var.get() == "AM":
            ampm_btn_am.config(bg="#007bff", fg="white")
            ampm_btn_pm.config(bg="#f0f0f0", fg="#666")
        else:
            ampm_btn_am.config(bg="#f0f0f0", fg="#666")
            ampm_btn_pm.config(bg="#007bff", fg="white")
    
    ampm_var.trace("w", lambda *args: update_ampm_style())
    update_ampm_style()
    
    # Quick time buttons (modern pill buttons)
    quick_frame = tk.Frame(container, bg="#f5f7fa")
    quick_frame.pack(fill="x", pady=(0, 20))
    
    tk.Label(quick_frame, text="Quick Select", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 10))
    
    quick_buttons_frame = tk.Frame(quick_frame, bg="#f5f7fa")
    quick_buttons_frame.pack(fill="x")
    
    def set_quick_time(hour, ampm):
        hour_var.set(str(hour))
        minute_var.set("00")
        ampm_var.set(ampm)
        update_ampm_style()
    
    quick_times = [
        ("9:00 AM", 9, "AM"), ("12:00 PM", 12, "PM"), 
        ("3:00 PM", 3, "PM"), ("6:00 PM", 6, "PM")
    ]
    
    for i, (label, h, a) in enumerate(quick_times):
        btn = tk.Button(quick_buttons_frame, text=label,
                       command=lambda hour=h, ampm=a: set_quick_time(hour, ampm),
                       font=("Segoe UI", 9), bg="white", fg="#007bff",
                       relief="flat", bd=1, highlightthickness=1,
                       highlightbackground="#ddd", highlightcolor="#007bff",
                       padx=12, pady=5, cursor="hand2",
                       activebackground="#f0f7ff", activeforeground="#0056b3")
        btn.pack(side="left", padx=(0, 8) if i < len(quick_times) - 1 else (0, 0))
    
    # Status label (hidden initially)
    status_label = tk.Label(container, text="", bg="#f5f7fa", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 15))
    
    def apply_timer():
        try:
            date_str = date_entry.get().strip()
            hour = int(hour_var.get())
            minute = int(minute_var.get())
            ampm = ampm_var.get()
            
            # Validate inputs
            if not date_str or hour < 1 or hour > 12 or minute < 0 or minute > 59:
                status_label.config(text="❌ Please enter a valid date and time", fg="#dc3545", bg="#f5f7fa")
                status_label.pack(pady=(0, 15))
                return
            
            # Convert 12-hour format to 24-hour format
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
            
            # Format time string for datetime parsing
            time_str = f"{hour:02d}:{minute:02d}"
            deadline_raw = f"{date_str} {time_str}"
            # Validate format
            datetime.strptime(deadline_raw, DEADLINE_RAW_FMT)
            
            if selected_uuid in todo_data:
                todo_data[selected_uuid]["deadline"] = deadline_raw
                refresh_todo_tree(selection_uuid=selected_uuid)
                persist_todos_to_db(list(todo_tree.get_children()))
                update_status_bar()
                timer_window.destroy()
            else:
                status_label.config(text="❌ Task no longer exists", fg="#dc3545", bg="#f5f7fa")
                status_label.pack(pady=(0, 15))
        except ValueError:
            status_label.config(text="❌ Invalid date format. Use: YYYY-MM-DD", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
    
    def on_timer_window_close():
        timer_window.destroy()
    
    # Action buttons (modern design)
    button_frame = tk.Frame(container, bg="#f5f7fa")
    button_frame.pack(fill="x", pady=(15, 0))
    
    cancel_btn = tk.Button(button_frame, text="Cancel", command=on_timer_window_close,
              bg="white", fg="#666", font=("Segoe UI", 10),
              relief="flat", bd=1, highlightthickness=1,
              highlightbackground="#ddd", padx=16, pady=8,
              cursor="hand2", activebackground="#f5f5f5")
    cancel_btn.pack(side="left", padx=(0, 10))
    
    apply_btn = tk.Button(button_frame, text="Set Deadline", command=apply_timer,
              bg="#007bff", fg="white", font=("Segoe UI", 10, "bold"),
              relief="flat", bd=0, padx=20, pady=8,
              cursor="hand2", activebackground="#0056b3")
    apply_btn.pack(side="right")
    
    # Bind Enter key to apply timer
    timer_window.bind('<Return>', lambda e: apply_timer())
    
    # Bind window close event
    timer_window.protocol("WM_DELETE_WINDOW", on_timer_window_close)
    
    # Focus on date entry
    date_entry.focus_set()
    date_entry.select_range(0, tk.END)

def update_timers():
    """Update timer displays and check for overdue tasks"""
    global blink_state
    # Update table rows (time-left column + color tags) and beep on first overdue
    if "todo_tree" in globals():
        for uuid_val in list(todo_tree.get_children()):
            row = todo_data.get(uuid_val)
            if not row:
                continue
            deadline_raw = str(row.get("deadline") or "")
            done_bool = bool(row.get("done"))
            left, tag = _format_time_left(deadline_raw, done_bool)

            # Update row values if needed (keeps time left fresh)
            values = list(todo_tree.item(uuid_val, "values"))
            # values = [status, task, created, deadline, left]
            if len(values) == 5:
                values[0] = "✅" if done_bool else "☐"
                values[1] = str(row.get("task") or "")
                values[2] = _format_created_display(str(row.get("created_at") or ""))
                values[3] = _format_deadline_display(deadline_raw)
                values[4] = left
                todo_tree.item(uuid_val, values=values, tags=(tag,))

            # Sound on overdue (once per uuid)
            if tag == "overdue" and not done_bool:
                if uuid_val not in overdue_sound_played:
                    try:
                        sound_file = resource_path("assets", "overdue.mp3")
                        if os.path.exists(sound_file):
                            threading.Thread(target=lambda: playsound(sound_file, block=False), daemon=True).start()
                        elif winsound:
                            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
                    except Exception:
                        try:
                            if winsound:
                                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
                        except Exception:
                            pass
                    overdue_sound_played.add(uuid_val)
    
    # Toggle blink state for next update
    blink_state = not blink_state
    
    # Schedule next update in 1 second for blinking effect and 30 seconds for timer updates
    root.after(1000, update_timers)

# ----------- MAIN FUNCTIONS -----------
def open_website(url):
    webbrowser.open_new_tab(url)

def on_enter(event):
    event.widget.config(fg="#007acc", font=("Segoe UI", 10, "bold"), cursor="hand2")
def on_leave(event):
    event.widget.config(fg="#333", font=("Segoe UI", 10), cursor="arrow")

def add_todo():
    task = todo_entry.get().strip()
    if task:
        uuid_val = str(uuid.uuid4())
        todo_data[uuid_val] = {
            "task": task,
            "done": False,
            "deadline": "",
            "done_at": "",
            "created_at": now_ts(),
            "order_index": len(todo_data),
        }
        refresh_todo_tree(selection_uuid=uuid_val)
        persist_todos_to_db(list(todo_tree.get_children()))
        todo_entry.delete(0, tk.END)
        update_status_bar()
        try:
            todo_tree.selection_set(uuid_val)
            todo_tree.see(uuid_val)
        except Exception:
            pass

def toggle_task(event=None):
    uuid_val = get_selected_todo_uuid()
    if uuid_val and uuid_val in todo_data:
        row = todo_data[uuid_val]
        row["done"] = not bool(row.get("done"))
        row["done_at"] = now_ts() if row["done"] else ""
        todo_data[uuid_val] = row
        refresh_todo_tree(selection_uuid=uuid_val)
        persist_todos_to_db(list(todo_tree.get_children()))
        update_status_bar()

def delete_task():
    uuid_val = get_selected_todo_uuid()
    if uuid_val and uuid_val in todo_data:
        del todo_data[uuid_val]
        try:
            todo_tree.delete(uuid_val)
        except Exception:
            pass
        persist_todos_to_db(list(todo_tree.get_children()))
        update_status_bar()
    else:
        messagebox.showinfo("No Selection", "Please select a task to delete.")

def on_todo_select(event):
    """Treeview handles selection highlighting; keep for compatibility."""
    return

def on_todo_key(event):
    """Handle keyboard shortcuts for todo list"""
    if event.keysym == 'Return':
        add_todo()
    elif event.keysym == 'Delete':
        delete_task()
    elif event.keysym == 'space':
        toggle_task()
    elif event.keysym == 'Up':
        if "todo_tree" in globals():
            sel = get_selected_todo_uuid()
            children = list(todo_tree.get_children())
            if sel in children:
                idx = children.index(sel)
                if idx > 0:
                    todo_tree.selection_set(children[idx - 1])
                    todo_tree.see(children[idx - 1])
    elif event.keysym == 'Down':
        if "todo_tree" in globals():
            sel = get_selected_todo_uuid()
            children = list(todo_tree.get_children())
            if sel in children:
                idx = children.index(sel)
                if idx < len(children) - 1:
                    todo_tree.selection_set(children[idx + 1])
                    todo_tree.see(children[idx + 1])

def add_link_window():
    link_window = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    link_window.withdraw()
    link_window.title("Add New Link")
    link_window.config(bg="#f5f7fa")
    link_window.resizable(False, False)
    
    # Set icon for link window
    set_window_icon(link_window)
    
    # Center window relative to main window
    center_window_relative_to_parent(link_window, 480, 450)
    link_window.deiconify()
    
    # Make modal
    link_window.transient(root)
    link_window.grab_set()
    
    # Main container
    container = tk.Frame(link_window, bg="#f5f7fa")
    container.pack(fill="both", expand=True, padx=30, pady=30)
    
    # Header
    header_frame = tk.Frame(container, bg="#f5f7fa")
    header_frame.pack(fill="x", pady=(0, 25))
    
    title_label = tk.Label(header_frame, text="🔗 Add New Link", 
                          font=("Segoe UI", 20, "bold"), bg="#f5f7fa", fg="#1a1a1a")
    title_label.pack()
    
    # Link Name section
    name_section = tk.Frame(container, bg="#f5f7fa")
    name_section.pack(fill="x", pady=(0, 15))
    
    tk.Label(name_section, text="Link Name", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
    
    name_entry = tk.Entry(name_section, font=("Segoe UI", 12), 
                         relief="flat", bd=0, bg="white", fg="#333",
                         insertbackground="#333", highlightthickness=1,
                         highlightbackground="#ddd", highlightcolor="#007bff")
    name_entry.pack(fill="x", ipady=12, padx=0)
    add_placeholder(name_entry, "Enter link name...")
    
    # URL section
    url_section = tk.Frame(container, bg="#f5f7fa")
    url_section.pack(fill="x", pady=(0, 20))
    
    tk.Label(url_section, text="URL", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
    
    url_entry = tk.Entry(url_section, font=("Segoe UI", 12), 
                        relief="flat", bd=0, bg="white", fg="#333",
                        insertbackground="#333", highlightthickness=1,
                        highlightbackground="#ddd", highlightcolor="#007bff")
    url_entry.pack(fill="x", ipady=12, padx=0)
    add_placeholder(url_entry, "Enter URL...")
    
    # Status label (hidden initially)
    status_label = tk.Label(container, text="", bg="#f5f7fa", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 15))
    
    def save():
        name = name_entry.get().strip()
        url = url_entry.get().strip()
        
        # Check if placeholders are still there
        if name == "Enter link name..." or url == "Enter URL...":
            status_label.config(text="❌ Please fill in all fields", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
            return
        
        if not name or not url:
            status_label.config(text="❌ Please fill in all fields", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
            return
        
        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        try:
            save_link(name, url)
            refresh_links()
            link_window.destroy()
        except Exception as e:
            status_label.config(text=f"❌ Error: {str(e)}", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
    
    # Action buttons
    button_frame = tk.Frame(container, bg="#f5f7fa")
    button_frame.pack(fill="x", pady=(15, 0))
    
    cancel_btn = tk.Button(button_frame, text="Cancel", command=link_window.destroy,
              bg="white", fg="#666", font=("Segoe UI", 10),
              relief="flat", bd=1, highlightthickness=1,
              highlightbackground="#ddd", padx=16, pady=8,
              cursor="hand2", activebackground="#f5f5f5")
    cancel_btn.pack(side="left", padx=(0, 10))
    
    save_btn = tk.Button(button_frame, text="Save Link", command=save,
             bg="#007bff", fg="white", font=("Segoe UI", 10, "bold"),
             relief="flat", bd=0, padx=20, pady=8,
             cursor="hand2", activebackground="#0056b3")
    save_btn.pack(side="right")
    
    # Bind Enter key to save
    link_window.bind('<Return>', lambda e: save())
    
    # Focus on name entry
    name_entry.focus_set()

def refresh_links():
    links_listbox.delete(0, tk.END)
    links = load_links()
    for link_id, name, url, order_index in links:
        links_listbox.insert(tk.END, f"🌐 {name}")
        
        # Bind click event to open URL
        def open_link(event, url=url):
            open_website(url)
        
        # Bind double-click to open link
        links_listbox.bind("<Double-Button-1>", lambda e, url=url: open_website(url))
        
        # Add right-click menu for delete
        def create_popup(link_id):
            popup = tk.Menu(links_listbox, tearoff=0)
            popup.add_command(label="Delete", command=lambda: delete_and_refresh_link(link_id))
            return popup
        
        popup = create_popup(link_id)
        links_listbox.bind("<Button-3>", lambda e, p=popup: p.tk_popup(e.x_root, e.y_root))

def delete_and_refresh_link(link_id):
    if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this link?"):
        delete_link(link_id)
        refresh_links()

def add_note_window():
    note_window = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    note_window.withdraw()
    note_window.title("Add New Note")
    note_window.config(bg="white")
    note_window.resizable(False, False)
    
    # Set icon for note window
    set_window_icon(note_window)
    
    # Center window relative to main window
    center_window_relative_to_parent(note_window, 600, 500)
    note_window.deiconify()
    
    # Make modal
    note_window.transient(root)
    note_window.grab_set()
    
    container = tk.Frame(note_window, bg="white", padx=20, pady=15)
    container.pack(fill="both", expand=True)
    
    # Title entry with placeholder
    title_entry = tk.Entry(container, font=("Segoe UI", 11), 
                          relief="flat", bg="#f8f9fa")
    title_entry.pack(fill="x", ipady=8, pady=(0,15))
    add_placeholder(title_entry, "Enter note title...")
    
    # Content text area with placeholder
    content_text = tk.Text(container, height=15, font=("Segoe UI", 11),
                          wrap=tk.WORD, relief="flat", bg="#f8f9fa")
    content_text.pack(fill="both", expand=True, pady=(0,15))
    content_text.insert("1.0", "Enter your note content...")
    content_text.bind("<FocusIn>", lambda e: content_text.delete("1.0", tk.END) 
                     if content_text.get("1.0", tk.END).strip() == "Enter your note content..." else None)
    
    # Button frame
    btn_frame = tk.Frame(container, bg="white")
    btn_frame.pack(fill="x", pady=(0,10))
    
    def save():
        title = title_entry.get().strip()
        content = content_text.get("1.0", tk.END).strip()
        if title and content:
            save_note(title, content)
            refresh_notes()
            note_window.destroy()
    
    save_btn = tk.Button(btn_frame, text="Save Note",
                        command=save, bg="#28a745", fg="white",
                        font=("Segoe UI", 9, "bold"),
                        padx=14, pady=6)
    save_btn.pack(side="right")

def edit_note_window(note_id):
    """Open edit window for an existing note"""
    notes = get_all_notes()
    note_data = None
    for note in notes:
        if note[0] == note_id:
            note_data = note
            break
    
    if not note_data:
        messagebox.showerror("Error", "Note not found.")
        return
    
    edit_window = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    edit_window.withdraw()
    edit_window.title("Edit Note")
    edit_window.config(bg="#f5f7fa")
    edit_window.resizable(False, False)
    
    # Set icon for edit window
    set_window_icon(edit_window)
    
    # Center window relative to main window - make it taller with scrollability
    center_window_relative_to_parent(edit_window, 700, 800)
    edit_window.deiconify()
    
    # Make modal
    edit_window.transient(root)
    edit_window.grab_set()
    
    # Create scrollable container
    canvas = tk.Canvas(edit_window, bg="#f5f7fa", highlightthickness=0)
    scrollbar = tk.Scrollbar(edit_window, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="#f5f7fa")
    
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    scrollable_frame.bind("<Configure>", on_frame_configure)
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    def on_canvas_configure(event):
        canvas_width = event.width
        canvas_window = canvas.find_all()
        if canvas_window:
            canvas.itemconfig(canvas_window[0], width=canvas_width)
    
    canvas.bind("<Configure>", on_canvas_configure)
    
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def bind_mousewheel(event):
        canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def unbind_mousewheel(event):
        canvas.unbind_all("<MouseWheel>")
    
    canvas.bind("<Enter>", bind_mousewheel)
    canvas.bind("<Leave>", unbind_mousewheel)
    edit_window.bind("<MouseWheel>", on_mousewheel)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Main container with padding
    container = tk.Frame(scrollable_frame, bg="#f5f7fa", padx=30, pady=30)
    container.pack(fill="both", expand=True)
    
    # Header section
    header_frame = tk.Frame(container, bg="#f5f7fa")
    header_frame.pack(fill="x", pady=(0, 25))
    
    title_label = tk.Label(header_frame, text="✏️ Edit Note", 
                          font=("Segoe UI", 22, "bold"), bg="#f5f7fa", fg="#1a1a1a")
    title_label.pack()
    
    # Title section
    title_section = tk.Frame(container, bg="#f5f7fa")
    title_section.pack(fill="x", pady=(0, 20))
    
    tk.Label(title_section, text="Note Title", bg="#f5f7fa", font=("Segoe UI", 11, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 10))
    
    title_entry = tk.Entry(title_section, font=("Segoe UI", 13), 
                          relief="flat", bd=0, bg="white", fg="#333",
                          insertbackground="#333", highlightthickness=1,
                          highlightbackground="#ddd", highlightcolor="#007bff")
    title_entry.pack(fill="x", ipady=12)
    title_entry.insert(0, note_data[1])  # note_data[1] is the title
    
    # Content section
    content_section = tk.Frame(container, bg="#f5f7fa")
    content_section.pack(fill="both", expand=True, pady=(0, 20))
    
    tk.Label(content_section, text="Note Content", bg="#f5f7fa", font=("Segoe UI", 11, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 10))
    
    # Text area with scrollbar
    text_frame = tk.Frame(content_section, bg="white", relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#ddd", highlightcolor="#007bff")
    text_frame.pack(fill="both", expand=True)
    
    content_text = tk.Text(text_frame, font=("Segoe UI", 12), 
                          relief="flat", bd=0, bg="white", fg="#333",
                          insertbackground="#333", wrap="word",
                          padx=15, pady=15, height=20)
    content_text.pack(side="left", fill="both", expand=True)
    
    text_scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=content_text.yview)
    text_scrollbar.pack(side="right", fill="y")
    content_text.config(yscrollcommand=text_scrollbar.set)
    
    # Insert current note content
    content_text.insert("1.0", note_data[2])  # note_data[2] is the content
    
    # Status label (for errors)
    status_label = tk.Label(container, text="", bg="#f5f7fa", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 15))
    
    def save_changes():
        title = title_entry.get().strip()
        content = content_text.get("1.0", tk.END).strip()
        
        if not title:
            status_label.config(text="❌ Note title cannot be empty", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
            return
        
        if not content:
            status_label.config(text="❌ Note content cannot be empty", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
            return
        
        try:
            update_note(note_id, title, content)
            refresh_notes()
            edit_window.destroy()
        except Exception as e:
            status_label.config(text=f"❌ Error: {str(e)}", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
    
    def on_edit_window_close():
        try:
            canvas.unbind_all("<MouseWheel>")
        except:
            pass
        edit_window.destroy()
    
    # Action buttons
    button_frame = tk.Frame(container, bg="#f5f7fa")
    button_frame.pack(fill="x", pady=(15, 0))
    
    cancel_btn = tk.Button(button_frame, text="Cancel", command=on_edit_window_close,
              bg="white", fg="#666", font=("Segoe UI", 10),
              relief="flat", bd=1, highlightthickness=1,
              highlightbackground="#ddd", padx=16, pady=8,
              cursor="hand2", activebackground="#f5f5f5")
    cancel_btn.pack(side="left", padx=(0, 10))
    
    save_btn = tk.Button(button_frame, text="Save Changes", command=save_changes,
              bg="#28a745", fg="white", font=("Segoe UI", 10, "bold"),
              relief="flat", bd=0, padx=20, pady=8,
              cursor="hand2", activebackground="#218838")
    save_btn.pack(side="right")
    
    # Bind Enter key (Ctrl+Enter to save)
    edit_window.bind('<Control-Return>', lambda e: save_changes())
    edit_window.bind('<Escape>', lambda e: on_edit_window_close())
    
    # Bind window close event
    edit_window.protocol("WM_DELETE_WINDOW", on_edit_window_close)
    
    # Focus on title entry
    title_entry.focus_set()
    title_entry.select_range(0, tk.END)

def refresh_notes():
    notes_listbox.delete(0, tk.END)
    notes = get_all_notes()
    for note in notes:
        note_frame = tk.Frame(notes_listbox, bg="#f8f9fa")
        notes_listbox.insert(tk.END, f"{note[0]} - {note[1]}")
        
        # Add right-click menu for edit and delete
        def create_popup(note_id):
            popup = tk.Menu(notes_listbox, tearoff=0)
            popup.add_command(label="Edit", command=lambda: edit_note_window(note_id))
            popup.add_separator()
            popup.add_command(label="Delete", command=lambda: delete_and_refresh_note(note_id))
            return popup
        
        popup = create_popup(note[0])
        notes_listbox.bind("<Button-3>", lambda e, p=popup: p.tk_popup(e.x_root, e.y_root))

def delete_and_refresh_note(note_id):
    if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this note?"):
        delete_note(note_id)
        refresh_notes()

def view_note(event):
    selection = notes_listbox.curselection()
    if selection:
        note_id = int(notes_listbox.get(selection[0]).split(" - ")[0])
        notes = get_all_notes()
        for note in notes:
            if note[0] == note_id:
                view_window = tk.Toplevel(root)
                # Create hidden first to avoid visible "jump" animation, then center and show
                view_window.withdraw()
                view_window.title(note[1])
                view_window.config(bg="white")
                view_window.resizable(False, False)
                
                # Set icon for view window
                set_window_icon(view_window)
                
                # Center window relative to main window
                center_window_relative_to_parent(view_window, 600, 400)
                view_window.deiconify()
                
                # Make modal
                view_window.transient(root)
                view_window.grab_set()
                
                # Add a container frame
                container = tk.Frame(view_window, bg="white", padx=20, pady=10)
                container.pack(fill="both", expand=True)
                
                # Title display
                title_label = tk.Label(container, text=note[1], 
                                     font=("Segoe UI", 16, "bold"),
                                     bg="white", fg="#333")
                title_label.pack(anchor="w", pady=(0, 10))
                
                # Content display
                text_frame = tk.Frame(container, bg="white")
                text_frame.pack(fill="both", expand=True)
                
                text = tk.Text(text_frame, wrap=tk.WORD, font=("Segoe UI", 11),
                              padx=10, pady=10, relief="flat", bg="#f8f9fa")
                text.pack(fill="both", expand=True)
                text.insert("1.0", note[2])
                text.config(state="disabled")
                
                # Button frame
                btn_frame = tk.Frame(container, bg="white")
                btn_frame.pack(fill="x", pady=(10, 0))
                
                def edit_current_note():
                    view_window.destroy()
                    edit_note_window(note_id)
                
                def delete_current_note():
                    if messagebox.askyesno("Confirm Delete", 
                                         "Are you sure you want to delete this note?"):
                        delete_note(note_id)
                        refresh_notes()
                        view_window.destroy()
                
                edit_btn = tk.Button(btn_frame, text="Edit Note", 
                                    command=edit_current_note,
                                    bg="#007bff", fg="white",
                                    font=("Segoe UI", 9),
                                    padx=12, pady=4)
                edit_btn.pack(side="left", padx=(0, 10))
                
                delete_btn = tk.Button(btn_frame, text="Delete Note", 
                                     command=delete_current_note,
                                     bg="#dc3545", fg="white",
                                     font=("Segoe UI", 9),
                                     padx=12, pady=4)
                delete_btn.pack(side="right")
                break

# ----------- GUI SETUP -----------
init_db()
settings = load_settings()
root = tk.Tk()
root.title("🧠 Advanced Daily Dashboard")
try:
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w = int(sw * 0.85)
    h = int(sh * 0.85)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.minsize(950, 700)
except Exception:
    root.geometry("1024x768")
    root.minsize(950, 700)
root.config(bg="#eaf4fc")

# Set application icon using shared utility
set_window_icon(root)

def apply_theme():
    """Basic light/dark theme for main surfaces. (Listboxes are styled manually)."""
    theme = settings.get("theme", "light")
    if theme == "dark":
        root.configure(bg="#0f172a")
    else:
        root.configure(bg="#eaf4fc")
    # Update known frames if they exist
    try:
        if "outer_frame" in globals():
            outer_frame.configure(bg=root["bg"])
        if "status_frame" in globals():
            status_frame.configure(bg=root["bg"])
        if "status_label_bar" in globals():
            status_label_bar.configure(bg=root["bg"])
    except Exception:
        pass

apply_theme()

# ----------- MENU BAR -----------
def backup_database():
    try:
        default_name = f"taskmask-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        path = filedialog.asksaveasfilename(
            title="Backup Database",
            defaultextension=".db",
            initialfile=default_name,
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")],
        )
        if not path:
            return
        shutil.copy2(DB_NAME, path)
        messagebox.showinfo("Backup Complete", f"Database backup saved to:\n{path}")
    except Exception as e:
        messagebox.showerror("Backup Failed", str(e))

def restore_database():
    path = filedialog.askopenfilename(
        title="Restore Database",
        filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")],
    )
    if not path:
        return
    if not messagebox.askyesno(
        "Confirm Restore",
        "This will replace your current database.\n\nContinue?",
    ):
        return
    try:
        shutil.copy2(path, DB_NAME)
        init_db()
        load_todo_data_from_db()
        # Reload views
        refresh_links()
        refresh_notes()
        refresh_todo_tree()
        messagebox.showinfo("Restore Complete", "Database restored successfully.")
    except Exception as e:
        messagebox.showerror("Restore Failed", str(e))

def open_settings_window():
    win = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    win.withdraw()
    win.title("Settings")
    win.config(bg="white")
    win.resizable(False, False)
    set_window_icon(win)
    
    # Center window relative to main window - increased height for new fields
    center_window_relative_to_parent(win, 580, 750)
    win.deiconify()
    
    # Make modal
    win.transient(root)
    win.grab_set()

    # Create scrollable container
    canvas = tk.Canvas(win, bg="white", highlightthickness=0)
    scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="white")
    
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    scrollable_frame.bind("<Configure>", on_frame_configure)
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    def on_canvas_configure(event):
        canvas_width = event.width
        canvas_window = canvas.find_all()
        if canvas_window:
            canvas.itemconfig(canvas_window[0], width=canvas_width)
    
    canvas.bind("<Configure>", on_canvas_configure)
    
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    container = tk.Frame(scrollable_frame, bg="white", padx=18, pady=18)
    container.pack(fill="both", expand=True)

    tk.Label(container, text="⚙️ Settings", font=("Segoe UI", 16, "bold"), bg="white", fg="#111").pack(anchor="w")

    # Theme
    theme_frame = tk.LabelFrame(container, text="Appearance", font=("Segoe UI", 10, "bold"), bg="white", fg="#111", padx=12, pady=10)
    theme_frame.pack(fill="x", pady=(12, 10))

    theme_var = tk.StringVar(value=settings.get("theme", "light"))
    tk.Radiobutton(theme_frame, text="Light", value="light", variable=theme_var, bg="white").pack(anchor="w")
    tk.Radiobutton(theme_frame, text="Dark", value="dark", variable=theme_var, bg="white").pack(anchor="w")

    # Sync
    sync_frame = tk.LabelFrame(container, text="Server Sync (optional)", font=("Segoe UI", 10, "bold"), bg="white", fg="#111", padx=12, pady=10)
    sync_frame.pack(fill="x", pady=(0, 10))

    sync_enabled_var = tk.BooleanVar(value=bool(settings.get("sync_enabled", False)))
    tk.Checkbutton(sync_frame, text="Enable auto sync", variable=sync_enabled_var, bg="white").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    # Sync type selection
    tk.Label(sync_frame, text="Sync Type:", bg="white").grid(row=1, column=0, sticky="w", pady=(0, 0))
    sync_type_var = tk.StringVar(value=settings.get("sync_type", "http"))
    sync_type_frame = tk.Frame(sync_frame, bg="white")
    sync_type_frame.grid(row=1, column=1, sticky="w", padx=(10, 0))
    tk.Radiobutton(sync_type_frame, text="HTTP", value="http", variable=sync_type_var, bg="white", command=lambda: update_sync_fields()).pack(side="left", padx=(0, 10))
    tk.Radiobutton(sync_type_frame, text="FTP", value="ftp", variable=sync_type_var, bg="white", command=lambda: update_sync_fields()).pack(side="left", padx=(0, 10))
    tk.Radiobutton(sync_type_frame, text="S3", value="s3", variable=sync_type_var, bg="white", command=lambda: update_sync_fields()).pack(side="left")

    # HTTP fields
    http_frame = tk.Frame(sync_frame, bg="white")
    http_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    
    tk.Label(http_frame, text="Server URL:", bg="white").grid(row=0, column=0, sticky="w", pady=(0, 4))
    url_var = tk.StringVar(value=settings.get("sync_server_url", "http://127.0.0.1:8765"))
    tk.Entry(http_frame, textvariable=url_var).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(http_frame, text="User:", bg="white").grid(row=1, column=0, sticky="w", pady=(0, 4))
    user_var = tk.StringVar(value=settings.get("sync_user", "default"))
    tk.Entry(http_frame, textvariable=user_var).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(http_frame, text="Token:", bg="white").grid(row=2, column=0, sticky="w", pady=(0, 4))
    token_var = tk.StringVar(value=settings.get("sync_token", ""))
    tk.Entry(http_frame, textvariable=token_var, show="*").grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
    http_frame.columnconfigure(1, weight=1)

    # FTP fields
    ftp_frame = tk.Frame(sync_frame, bg="white")
    ftp_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    
    tk.Label(ftp_frame, text="FTP Host:", bg="white").grid(row=0, column=0, sticky="w", pady=(0, 4))
    ftp_host_var = tk.StringVar(value=settings.get("sync_ftp_host", ""))
    tk.Entry(ftp_frame, textvariable=ftp_host_var).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(ftp_frame, text="FTP Port:", bg="white").grid(row=1, column=0, sticky="w", pady=(0, 4))
    ftp_port_var = tk.StringVar(value=str(settings.get("sync_ftp_port", 21)))
    tk.Entry(ftp_frame, textvariable=ftp_port_var, width=10).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(0, 4))

    tk.Label(ftp_frame, text="FTP User:", bg="white").grid(row=2, column=0, sticky="w", pady=(0, 4))
    ftp_user_var = tk.StringVar(value=settings.get("sync_ftp_user", ""))
    tk.Entry(ftp_frame, textvariable=ftp_user_var).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(ftp_frame, text="FTP Password:", bg="white").grid(row=3, column=0, sticky="w", pady=(0, 4))
    ftp_pass_var = tk.StringVar(value=settings.get("sync_ftp_pass", ""))
    tk.Entry(ftp_frame, textvariable=ftp_pass_var, show="*").grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(ftp_frame, text="Remote Path:", bg="white").grid(row=4, column=0, sticky="w", pady=(0, 4))
    ftp_path_var = tk.StringVar(value=settings.get("sync_ftp_path", "/"))
    tk.Entry(ftp_frame, textvariable=ftp_path_var).grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
    ftp_frame.columnconfigure(1, weight=1)

    # S3 fields
    s3_frame = tk.Frame(sync_frame, bg="white")
    s3_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    
    tk.Label(s3_frame, text="S3 Bucket:", bg="white").grid(row=0, column=0, sticky="w", pady=(0, 4))
    s3_bucket_var = tk.StringVar(value=settings.get("sync_s3_bucket", ""))
    tk.Entry(s3_frame, textvariable=s3_bucket_var).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(s3_frame, text="S3 Key (filename):", bg="white").grid(row=1, column=0, sticky="w", pady=(0, 4))
    s3_key_var = tk.StringVar(value=settings.get("sync_s3_key", "taskmask.db"))
    tk.Entry(s3_frame, textvariable=s3_key_var).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(s3_frame, text="S3 Region:", bg="white").grid(row=2, column=0, sticky="w", pady=(0, 4))
    s3_region_var = tk.StringVar(value=settings.get("sync_s3_region", "us-east-1"))
    tk.Entry(s3_frame, textvariable=s3_region_var).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(s3_frame, text="Access Key ID:", bg="white").grid(row=3, column=0, sticky="w", pady=(0, 4))
    s3_access_var = tk.StringVar(value=settings.get("sync_s3_access_key", ""))
    tk.Entry(s3_frame, textvariable=s3_access_var).grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))

    tk.Label(s3_frame, text="Secret Access Key:", bg="white").grid(row=4, column=0, sticky="w", pady=(0, 4))
    s3_secret_var = tk.StringVar(value=settings.get("sync_s3_secret_key", ""))
    tk.Entry(s3_frame, textvariable=s3_secret_var, show="*").grid(row=4, column=1, sticky="ew", padx=(10, 0), pady=(0, 4))
    s3_frame.columnconfigure(1, weight=1)

    # Common fields
    tk.Label(sync_frame, text="Interval (sec):", bg="white").grid(row=5, column=0, sticky="w", pady=(8, 0))
    interval_var = tk.StringVar(value=str(settings.get("sync_interval_sec", 60)))
    tk.Entry(sync_frame, textvariable=interval_var, width=10).grid(row=5, column=1, sticky="w", padx=(10, 0), pady=(8, 0))

    sync_frame.columnconfigure(1, weight=1)

    # Connection test status label
    test_status_var = tk.StringVar(value="")
    test_status_label = tk.Label(sync_frame, textvariable=test_status_var, bg="white",
                                 fg="#555", font=("Segoe UI", 9))
    test_status_label.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _set_test_status(msg: str, color: str = "#198754"):
        """Update small status text inside Settings sync section."""
        test_status_var.set(msg)
        test_status_label.config(fg=color)

    def _test_http_connection():
        url = url_var.get().strip()
        if not url:
            _set_test_status("HTTP: Server URL is empty.", "#dc3545")
            return
        user = (user_var.get().strip() or "default")
        token = token_var.get().strip()
        headers = {}
        if token:
            headers["X-Token"] = token
        try:
            meta_url = _join_url(url, "/api/meta", {"user": user})
            resp = http_get_json(meta_url, headers=headers, timeout=5)
            # Show compact response summary
            exists = resp.get("exists", None)
            _set_test_status(f"HTTP OK: meta exists={exists}", "#198754")
        except Exception as e:
            _set_test_status(f"HTTP error: {e}", "#dc3545")

    def _test_ftp_connection():
        host = ftp_host_var.get().strip()
        user = ftp_user_var.get().strip()
        if not host or not user:
            _set_test_status("FTP: Host or user is empty.", "#dc3545")
            return
        try:
            port = int(ftp_port_var.get() or 21)
        except ValueError:
            port = 21
        password = ftp_pass_var.get()
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port, timeout=5)
            ftp.login(user, password)
            cwd = ftp.pwd()
            ftp.quit()
            _set_test_status(f"FTP OK: connected (cwd: {cwd})", "#198754")
        except Exception as e:
            _set_test_status(f"FTP error: {e}", "#dc3545")

    def _test_s3_connection():
        if not S3_AVAILABLE:
            _set_test_status("S3: boto3 not installed.", "#dc3545")
            return
        bucket = s3_bucket_var.get().strip()
        region = (s3_region_var.get().strip() or "us-east-1")
        access_key = s3_access_var.get().strip()
        secret_key = s3_secret_var.get().strip()
        if not bucket or not access_key or not secret_key:
            _set_test_status("S3: bucket or credentials missing.", "#dc3545")
            return
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            # Cheap check: does bucket exist / is it reachable?
            s3.head_bucket(Bucket=bucket)
            _set_test_status("S3 OK: bucket reachable.", "#198754")
        except Exception as e:
            _set_test_status(f"S3 error: {e}", "#dc3545")

    def test_connection():
        """Test connection for the currently selected sync type without changing any data."""
        _set_test_status("Testing connection...", "#0d6efd")
        sync_type = sync_type_var.get()
        if sync_type == "http":
            _test_http_connection()
        elif sync_type == "ftp":
            _test_ftp_connection()
        else:  # s3
            _test_s3_connection()

    # Test Connection button
    test_btn = tk.Button(
        sync_frame,
        text="Test Connection",
        command=test_connection,
        bg="#0d6efd",
        fg="white",
        font=("Segoe UI", 9, "bold"),
        padx=10,
        pady=4,
    )
    test_btn.grid(row=6, column=1, sticky="e", pady=(8, 0))

    def update_sync_fields():
        sync_type = sync_type_var.get()
        if sync_type == "http":
            http_frame.grid()
            ftp_frame.grid_remove()
            s3_frame.grid_remove()
        elif sync_type == "ftp":
            http_frame.grid_remove()
            ftp_frame.grid()
            s3_frame.grid_remove()
        else:  # s3
            http_frame.grid_remove()
            ftp_frame.grid_remove()
            s3_frame.grid()
    
    # Initialize field visibility
    update_sync_fields()

    btns = tk.Frame(container, bg="white")
    btns.pack(fill="x", pady=(10, 0))

    def save_and_close():
        settings["theme"] = theme_var.get()
        settings["sync_enabled"] = bool(sync_enabled_var.get())
        settings["sync_type"] = sync_type_var.get()
        settings["sync_server_url"] = url_var.get().strip()
        settings["sync_user"] = user_var.get().strip() or "default"
        settings["sync_token"] = token_var.get().strip()
        settings["sync_ftp_host"] = ftp_host_var.get().strip()
        try:
            settings["sync_ftp_port"] = int(ftp_port_var.get() or 21)
        except ValueError:
            settings["sync_ftp_port"] = 21
        settings["sync_ftp_user"] = ftp_user_var.get().strip()
        settings["sync_ftp_pass"] = ftp_pass_var.get().strip()
        settings["sync_ftp_path"] = ftp_path_var.get().strip() or "/"
        settings["sync_s3_bucket"] = s3_bucket_var.get().strip()
        settings["sync_s3_key"] = s3_key_var.get().strip() or "taskmask.db"
        settings["sync_s3_region"] = s3_region_var.get().strip() or "us-east-1"
        settings["sync_s3_access_key"] = s3_access_var.get().strip()
        settings["sync_s3_secret_key"] = s3_secret_var.get().strip()
        try:
            settings["sync_interval_sec"] = max(10, int(interval_var.get()))
        except ValueError:
            settings["sync_interval_sec"] = 60
        save_settings(settings)
        apply_theme()
        win.destroy()

    tk.Button(btns, text="Close", command=win.destroy, bg="#6c757d", fg="white", padx=12, pady=5).pack(side="left")
    tk.Button(btns, text="Save", command=save_and_close, bg="#28a745", fg="white", padx=12, pady=5).pack(side="right")

menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
file_menu.add_command(label="Backup Database...", command=backup_database)
file_menu.add_command(label="Restore Database...", command=restore_database)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.destroy)
menubar.add_cascade(label="File", menu=file_menu)

def open_mysql_backup_gui():
    """Open MySQL Backup GUI in a separate process."""
    try:
        # Get the path to the MySQL backup GUI script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mysql_gui_path = os.path.join(script_dir, "mysql_client", "mysql_backup_gui.py")
        
        # Check if file exists
        if not os.path.exists(mysql_gui_path):
            messagebox.showerror(
                "File Not Found",
                f"MySQL Backup GUI not found at:\n{mysql_gui_path}\n\nPlease ensure the file exists."
            )
            return
        
        # Launch the MySQL backup GUI in a separate process
        if sys.platform == "win32":
            # Windows
            subprocess.Popen([sys.executable, mysql_gui_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
        else:
            # Linux/Mac
            subprocess.Popen([sys.executable, mysql_gui_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open MySQL Backup GUI:\n{str(e)}")

def open_otithee_automation():
    """Open Otithee Automation GUI in a separate process."""
    try:
        # Get the path to the Otithee Automation GUI script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        otithee_gui_path = os.path.join(script_dir, "automation_otithee", "index_gui.py")
        
        # Check if file exists
        if not os.path.exists(otithee_gui_path):
            messagebox.showerror(
                "File Not Found",
                f"Otithee Automation GUI not found at:\n{otithee_gui_path}\n\nPlease ensure the file exists."
            )
            return
        
        # Launch the Otithee Automation GUI in a separate process
        if sys.platform == "win32":
            # Windows
            subprocess.Popen([sys.executable, otithee_gui_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
        else:
            # Linux/Mac
            subprocess.Popen([sys.executable, otithee_gui_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open Otithee Automation GUI:\n{str(e)}")

def open_ossl_automation():
    """Open OSSL Automation GUI in a separate process."""
    try:
        # Get the path to the OSSL Automation GUI script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ossl_gui_path = os.path.join(script_dir, "ossl", "index_gui.py")
        
        # Check if file exists
        if not os.path.exists(ossl_gui_path):
            messagebox.showerror(
                "File Not Found",
                f"OSSL Automation GUI not found at:\n{ossl_gui_path}\n\nPlease ensure the file exists."
            )
            return
        
        # Launch the OSSL Automation GUI in a separate process
        if sys.platform == "win32":
            # Windows
            subprocess.Popen([sys.executable, ossl_gui_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
        else:
            # Linux/Mac
            subprocess.Popen([sys.executable, ossl_gui_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open OSSL Automation GUI:\n{str(e)}")

tools_menu = tk.Menu(menubar, tearoff=0)
tools_menu.add_command(label="Sync Now", command=lambda: sync_once_async())
tools_menu.add_command(label="Settings...", command=open_settings_window)
tools_menu.add_separator()
tools_menu.add_command(label="MySQL Backup Tool...", command=open_mysql_backup_gui)
tools_menu.add_command(label="Otithee Automation...", command=open_otithee_automation)
tools_menu.add_command(label="OSSL Automation...", command=open_ossl_automation)
menubar.add_cascade(label="Tools", menu=tools_menu)

root.config(menu=menubar)

# Create outer container
outer_frame = tk.Frame(root, bg="#eaf4fc")
outer_frame.pack(fill="both", expand=True)

# Status bar (counts + sync placeholder)
status_frame = tk.Frame(root, bg="#eaf4fc")
status_frame.pack(fill="x", side="bottom")
status_var = tk.StringVar(value="Ready")
status_label_bar = tk.Label(status_frame, textvariable=status_var, bg="#eaf4fc", fg="#555", font=("Segoe UI", 9))
status_label_bar.pack(side="left", padx=10, pady=4)

def update_status_bar():
    try:
        total = len(todo_data)
        done_count = 0
        overdue_count = 0
        for uuid_val, row in todo_data.items():
            done_bool = bool(row.get("done"))
            if done_bool:
                done_count += 1
            deadline_raw = str(row.get("deadline") or "")
            if deadline_raw:
                _, _, is_overdue = _deadline_status(deadline_raw)
                if is_overdue and not done_bool:
                    overdue_count += 1
        sync_txt = "Sync: ON" if settings.get("sync_enabled") else "Sync: OFF"
        status_var.set(f"Tasks: {total} | Done: {done_count} | Overdue: {overdue_count} | {sync_txt} | DB: {DB_NAME}")
    except Exception:
        pass

# Create scrollable canvas
main_canvas = tk.Canvas(outer_frame, bg="#eaf4fc")
scrollbar = tk.Scrollbar(outer_frame, orient="vertical", command=main_canvas.yview)
scrollable_frame = tk.Frame(main_canvas, bg="#eaf4fc")

# Configure scrolling
scrollable_frame.bind(
    "<Configure>",
    lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
)

# Make canvas expand with window
def on_canvas_configure(e):
    main_canvas.itemconfig(canvas_window, width=e.width)
main_canvas.bind('<Configure>', on_canvas_configure)
canvas_window = main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

# Pack scrollbar and canvas
scrollbar.pack(side="right", fill="y")
main_canvas.pack(side="left", fill="both", expand=True)

# Title
title_frame = tk.Frame(scrollable_frame, bg="#eaf4fc")
title_frame.pack(fill="x", padx=20, pady=15)

# Main title
tk.Label(title_frame, text="🌅 My Daily Dashboard", 
         font=("Segoe UI", 20, "bold"), bg="#eaf4fc", fg="#222").pack()

# Date and Time frame
datetime_frame = tk.Frame(title_frame, bg="#eaf4fc")
datetime_frame.pack(pady=(2, 0))

# Date label with larger font
date_label = tk.Label(datetime_frame, text="", font=("Segoe UI", 12), 
                      bg="#eaf4fc", fg="#555")
date_label.pack()

# Time label with larger font and special styling
time_label = tk.Label(datetime_frame, text="", font=("Segoe UI", 16, "bold"), 
                      bg="#eaf4fc", fg="#007bff")
time_label.pack()

# AM/PM label
ampm_label = tk.Label(datetime_frame, text="", font=("Segoe UI", 12, "bold"), 
                      bg="#eaf4fc", fg="#28a745")
ampm_label.pack(pady=(0, 5))

def update_datetime():
    # Get Bangladesh time
    bd_timezone = pytz.timezone('Asia/Dhaka')
    bd_time = datetime.now(bd_timezone)
    
    # Update date in format: "Tuesday, July 29, 2025"
    date_label.config(text=bd_time.strftime("%A, %B %d, %Y"))
    
    # Update time in 12-hour format: "11:30:45"
    time_label.config(text=bd_time.strftime("%I:%M:%S %p"))
    
    
    # Schedule the next update in 1000ms (1 second)
    root.after(1000, update_datetime)

# Main content frame
main_frame = tk.Frame(scrollable_frame, bg="#eaf4fc")
main_frame.pack(fill="both", expand=True, padx=20)

left_frame = tk.Frame(main_frame, bg="#ffffff", bd=1, relief="groove", width=420)
left_frame.pack(side="left", fill="y", padx=10, pady=10)
left_frame.pack_propagate(False)  # Prevent frame from shrinking below width

right_frame = tk.Frame(main_frame, bg="#ffffff", bd=1, relief="groove")
right_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

# Website Links
links_title_frame = tk.Frame(left_frame, bg="white", padx=15, pady=10)
links_title_frame.pack(fill="x")
tk.Label(links_title_frame, text="🔗 Useful Links", bg="white", fg="#111", 
         font=("Segoe UI", 14, "bold")).pack(side="left")
tk.Button(links_title_frame, text="➕ Add New Link", command=add_link_window,
          bg="#007bff", fg="white", font=("Segoe UI", 9),
          padx=10, pady=4).pack(side="right")

# Create links listbox for reordering
links_listbox = create_scrolled_listbox(left_frame, 
                          font=("Segoe UI", 13),
                          height=8, selectbackground="#007bff",
                          selectforeground="white", relief="flat",
                          bg="#f8f9fa",
                          padx=15, pady=(0,15))

# Add reorder buttons for links
links_button_frame = tk.Frame(left_frame, bg="white")
links_button_frame.pack(pady=(0, 10))

tk.Button(links_button_frame, text="⬆️ Move Up", 
          command=lambda: move_up(links_listbox, lambda x: None, update_link_order, []),
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)
tk.Button(links_button_frame, text="⬇️ Move Down", 
          command=lambda: move_down(links_listbox, lambda x: None, update_link_order, []),
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)

links_frame = tk.Frame(left_frame, bg="white")
links_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))

# To-Do List
todo_title_frame = tk.Frame(right_frame, bg="white", padx=15, pady=10)
todo_title_frame.pack(fill="x")
tk.Label(todo_title_frame, text="✅ To-Do List", bg="white", fg="#111", 
         font=("Segoe UI", 14, "bold")).pack(side="left")

# Quick search (high-signal “advanced” UX without heavy refactor)
todo_search_var = tk.StringVar(value="")
search_entry = tk.Entry(todo_title_frame, textvariable=todo_search_var,
                        font=("Segoe UI", 10), relief="solid", bd=1, bg="#f8f9fa")
search_entry.pack(side="left", padx=(12, 8), fill="x", expand=True, ipady=6)
search_entry.insert(0, "Search tasks...")
search_placeholder_active = True

def _search_focus_in(_e):
    global search_placeholder_active
    if search_placeholder_active:
        search_entry.delete(0, tk.END)
        search_entry.config(fg="#111")
        search_placeholder_active = False

def _search_focus_out(_e):
    global search_placeholder_active
    if not search_entry.get().strip():
        search_entry.delete(0, tk.END)
        search_entry.insert(0, "Search tasks...")
        search_entry.config(fg="#888")
        search_placeholder_active = True

search_entry.config(fg="#888")
search_entry.bind("<FocusIn>", _search_focus_in)
search_entry.bind("<FocusOut>", _search_focus_out)

def find_next_task(event=None):
    query = todo_search_var.get().strip()
    if search_placeholder_active or not query:
        return
    query_l = query.lower()
    children = list(todo_tree.get_children()) if "todo_tree" in globals() else []
    start_idx = 0
    cur = get_selected_todo_uuid()
    if cur and cur in children:
        start_idx = children.index(cur) + 1
    # wrap-around scan
    for pass_idx in range(2):
        rng = range(start_idx, len(children)) if pass_idx == 0 else range(0, start_idx)
        for idx in rng:
            uuid_val = children[idx]
            row = todo_data.get(uuid_val, {})
            hay = f"{row.get('task','')} {row.get('deadline','')} {row.get('created_at','')}".lower()
            if query_l in hay:
                todo_tree.selection_set(uuid_val)
                todo_tree.see(uuid_val)
                return

search_entry.bind("<Return>", find_next_task)

# Add timer button with better feedback
def add_timer_with_check():
    sel = get_selected_todo_uuid()
    if not sel:
        messagebox.showwarning("No Task Selected", 
                             "Please select a task first before adding a timer.\n\n"
                             "Click on any task in the list to select it.")
        return
    add_timer_window(sel)

# Add timer button
tk.Button(todo_title_frame, text="⏰ Add Timer", command=add_timer_with_check,
          bg="#ffc107", fg="black", font=("Segoe UI", 9),
          padx=10, pady=6).pack(side="right")

todo_tree_frame = tk.Frame(right_frame, bg="white")
todo_tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

todo_tree = ttk.Treeview(
    todo_tree_frame,
    columns=("status", "task", "created", "deadline", "left"),
    show="headings",
    selectmode="browse",
)
todo_tree.heading("status", text="✓")
todo_tree.heading("task", text="Task")
todo_tree.heading("created", text="Created")
todo_tree.heading("deadline", text="Deadline")
todo_tree.heading("left", text="Time Left")
todo_tree.column("status", width=40, anchor="center", stretch=False)
todo_tree.column("task", width=300, anchor="w", stretch=True)
todo_tree.column("created", width=200, anchor="center", stretch=False)
todo_tree.column("deadline", width=220, anchor="center", stretch=False)
todo_tree.column("left", width=140, anchor="center", stretch=False)

# Configure Treeview font to be larger
style = ttk.Style()
style.configure("Treeview", font=("Segoe UI", 13))
style.configure("Treeview.Heading", font=("Segoe UI", 13, "bold"))

todo_tree_scroll = ttk.Scrollbar(todo_tree_frame, orient="vertical", command=todo_tree.yview)
todo_tree.configure(yscrollcommand=todo_tree_scroll.set)
todo_tree_scroll.pack(side="right", fill="y")
todo_tree.pack(side="left", fill="both", expand=True)

# Ensure row highlight disappears when focus moves away from the to-do list
def _todo_tree_on_focus_out(event):
    """
    When the Treeview loses focus (user clicks somewhere else),
    clear the visual selection so the highlight background disappears.
    """
    try:
        sel = todo_tree.selection()
        if sel:
            todo_tree.selection_remove(sel)
    except Exception:
        pass

def _todo_tree_on_focus_in(event):
    """
    Placeholder for future focus-in styling if needed.
    Currently does nothing but kept for symmetry / easy extension.
    """
    return

todo_tree.bind("<FocusOut>", _todo_tree_on_focus_out)
todo_tree.bind("<FocusIn>", _todo_tree_on_focus_in)

todo_tree.bind("<Double-Button-1>", lambda e: toggle_task())
todo_tree.bind("<KeyPress-Return>", on_todo_key)
todo_tree.bind("<KeyPress-Delete>", on_todo_key)
todo_tree.bind("<KeyPress-space>", on_todo_key)
todo_tree.bind("<KeyPress-Up>", on_todo_key)
todo_tree.bind("<KeyPress-Down>", on_todo_key)

# Right-click context menu (edit / clear timer / delete)
todo_menu = tk.Menu(todo_tree, tearoff=0)

def edit_selected_task():
    uuid_val = get_selected_todo_uuid()
    if not uuid_val or uuid_val not in todo_data:
        messagebox.showwarning("No Task Selected", "Please select a task first to edit.")
        return
    
    row = todo_data[uuid_val]
    
    # Create edit window
    edit_window = tk.Toplevel(root)
    # Create hidden first to avoid visible "jump" animation, then center and show
    edit_window.withdraw()
    edit_window.title("Edit Task - Detailed")
    edit_window.config(bg="#f5f7fa")
    edit_window.resizable(False, False)
    
    # Set icon
    set_window_icon(edit_window)
    
    # Center window relative to main window - make it bigger and taller
    center_window_relative_to_parent(edit_window, 750, 1000)
    edit_window.deiconify()
    
    # Make modal
    edit_window.transient(root)
    edit_window.grab_set()
    
    # Create scrollable container
    canvas = tk.Canvas(edit_window, bg="#f5f7fa", highlightthickness=0)
    scrollbar = tk.Scrollbar(edit_window, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="#f5f7fa")
    
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    scrollable_frame.bind("<Configure>", on_frame_configure)
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    def on_canvas_configure(event):
        canvas_width = event.width
        canvas_window = canvas.find_all()
        if canvas_window:
            canvas.itemconfig(canvas_window[0], width=canvas_width)
    
    canvas.bind("<Configure>", on_canvas_configure)
    
    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def bind_mousewheel(event):
        canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def unbind_mousewheel(event):
        canvas.unbind_all("<MouseWheel>")
    
    canvas.bind("<Enter>", bind_mousewheel)
    canvas.bind("<Leave>", unbind_mousewheel)
    edit_window.bind("<MouseWheel>", on_mousewheel)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Main container with padding
    container = tk.Frame(scrollable_frame, bg="#f5f7fa")
    container.pack(fill="both", expand=True, padx=30, pady=30)
    
    # Header section
    header_frame = tk.Frame(container, bg="#f5f7fa")
    header_frame.pack(fill="x", pady=(0, 25))
    
    title_label = tk.Label(header_frame, text="✏️ Edit Task", 
                          font=("Segoe UI", 22, "bold"), bg="#f5f7fa", fg="#1a1a1a")
    title_label.pack()
    
    # Task Text Section (multi-line)
    task_section = tk.Frame(container, bg="#f5f7fa")
    task_section.pack(fill="both", expand=True, pady=(0, 20))
    
    tk.Label(task_section, text="Task Description", bg="#f5f7fa", font=("Segoe UI", 11, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 10))
    
    # Text area with scrollbar
    text_frame = tk.Frame(task_section, bg="white", relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#ddd", highlightcolor="#007bff")
    text_frame.pack(fill="both", expand=True)
    
    task_text_area = tk.Text(text_frame, font=("Segoe UI", 11), 
                             relief="flat", bd=0, bg="white", fg="#333",
                             insertbackground="#333", wrap="word",
                             padx=15, pady=15, height=8)
    task_text_area.pack(side="left", fill="both", expand=True)
    
    text_scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=task_text_area.yview)
    text_scrollbar.pack(side="right", fill="y")
    task_text_area.config(yscrollcommand=text_scrollbar.set)
    
    # Insert current task text
    current_task = str(row.get("task") or "")
    task_text_area.insert("1.0", current_task)
    
    # Status Section (Done checkbox)
    status_section = tk.Frame(container, bg="#f5f7fa")
    status_section.pack(fill="x", pady=(0, 20))
    
    done_var = tk.BooleanVar(value=bool(row.get("done", False)))
    done_checkbox = tk.Checkbutton(status_section, text="Task Completed", 
                                   variable=done_var, bg="#f5f7fa", 
                                   font=("Segoe UI", 11, "bold"), fg="#333",
                                   activebackground="#f5f7fa", activeforeground="#333",
                                   selectcolor="white")
    done_checkbox.pack(anchor="w")
    
    # Created Date Section
    created_section = tk.Frame(container, bg="#f5f7fa")
    created_section.pack(fill="x", pady=(0, 15))
    
    tk.Label(created_section, text="Created Date", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
             fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
    
    created_at_str = str(row.get("created_at") or now_ts())
    try:
        created_dt = datetime.strptime(created_at_str, TS_FMT)
        created_display = created_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        created_display = created_at_str
    
    created_entry = tk.Entry(created_section, font=("Segoe UI", 11), 
                            relief="flat", bd=0, bg="white", fg="#666",
                            insertbackground="#333", highlightthickness=1,
                            highlightbackground="#ddd", highlightcolor="#007bff")
    created_entry.pack(fill="x", ipady=10)
    created_entry.insert(0, created_display)
    
    # Deadline Section (reuse timer window style)
    deadline_section = tk.LabelFrame(container, text="Deadline", font=("Segoe UI", 11, "bold"),
                                     bg="#f5f7fa", fg="#555", padx=15, pady=15)
    deadline_section.pack(fill="x", pady=(0, 20))
    
    # Parse existing deadline if any
    deadline_raw = str(row.get("deadline") or "")
    deadline_date_str = ""
    deadline_hour = 12
    deadline_minute = 0
    deadline_ampm = "PM"
    
    if deadline_raw:
        try:
            deadline_dt = datetime.strptime(deadline_raw, DEADLINE_RAW_FMT)
            deadline_date_str = deadline_dt.strftime("%Y-%m-%d")
            hour_24 = deadline_dt.hour
            deadline_hour = hour_24 % 12 or 12
            deadline_minute = deadline_dt.minute
            deadline_ampm = "PM" if hour_24 >= 12 else "AM"
        except:
            deadline_date_str = datetime.now().strftime("%Y-%m-%d")
    else:
        deadline_date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Date input
    date_label_frame = tk.Frame(deadline_section, bg="#f5f7fa")
    date_label_frame.pack(fill="x", pady=(0, 8))
    tk.Label(date_label_frame, text="Date (YYYY-MM-DD)", bg="#f5f7fa", 
             font=("Segoe UI", 10), fg="#666").pack(anchor="w")
    
    deadline_date_entry = tk.Entry(deadline_section, font=("Segoe UI", 12), 
                                   relief="flat", bd=0, bg="white", fg="#333",
                                   insertbackground="#333", highlightthickness=1,
                                   highlightbackground="#ddd", highlightcolor="#007bff")
    deadline_date_entry.pack(fill="x", ipady=10, pady=(0, 15))
    deadline_date_entry.insert(0, deadline_date_str)
    
    # Time input
    time_label_frame = tk.Frame(deadline_section, bg="#f5f7fa")
    time_label_frame.pack(fill="x", pady=(0, 8))
    tk.Label(time_label_frame, text="Time", bg="#f5f7fa", 
             font=("Segoe UI", 10), fg="#666").pack(anchor="w")
    
    time_input_frame = tk.Frame(deadline_section, bg="white", relief="flat", bd=0,
                                highlightthickness=1, highlightbackground="#ddd", highlightcolor="#007bff")
    time_input_frame.pack(fill="x", pady=(0, 15))
    
    # Hour
    deadline_hour_var = tk.StringVar(value=str(deadline_hour))
    deadline_hour_spinbox = tk.Spinbox(time_input_frame, from_=1, to=12, width=4,
                                      textvariable=deadline_hour_var, font=("Segoe UI", 13, "bold"),
                                      relief="flat", bd=0, bg="white", fg="#333",
                                      highlightthickness=0, justify="center")
    deadline_hour_spinbox.pack(side="left", padx=(15, 5), pady=12)
    
    tk.Label(time_input_frame, text=":", bg="white", font=("Segoe UI", 16, "bold"), 
             fg="#666").pack(side="left", padx=2)
    
    # Minute
    deadline_minute_var = tk.StringVar(value=f"{deadline_minute:02d}")
    deadline_minute_spinbox = tk.Spinbox(time_input_frame, from_=0, to=59, width=4,
                                        textvariable=deadline_minute_var, font=("Segoe UI", 13, "bold"),
                                        relief="flat", bd=0, bg="white", fg="#333",
                                        highlightthickness=0, justify="center",
                                        format="%02.0f")
    deadline_minute_spinbox.pack(side="left", padx=5, pady=12)
    
    # AM/PM
    deadline_ampm_var = tk.StringVar(value=deadline_ampm)
    deadline_ampm_frame = tk.Frame(time_input_frame, bg="white")
    deadline_ampm_frame.pack(side="left", padx=(15, 15), pady=12)
    
    deadline_ampm_btn_am = tk.Button(deadline_ampm_frame, text="AM", 
                                    command=lambda: deadline_ampm_var.set("AM"),
                                    font=("Segoe UI", 10, "bold"), bg="#f0f0f0", fg="#666",
                                    relief="flat", bd=0, padx=10, pady=5,
                                    activebackground="#e0e0e0", activeforeground="#333")
    deadline_ampm_btn_am.pack(side="left", padx=(0, 2))
    
    deadline_ampm_btn_pm = tk.Button(deadline_ampm_frame, text="PM", 
                                    command=lambda: deadline_ampm_var.set("PM"),
                                    font=("Segoe UI", 10, "bold"), bg="#f0f0f0", fg="#666",
                                    relief="flat", bd=0, padx=10, pady=5,
                                    activebackground="#e0e0e0", activeforeground="#333")
    deadline_ampm_btn_pm.pack(side="left")
    
    def update_deadline_ampm_style():
        if deadline_ampm_var.get() == "AM":
            deadline_ampm_btn_am.config(bg="#007bff", fg="white")
            deadline_ampm_btn_pm.config(bg="#f0f0f0", fg="#666")
        else:
            deadline_ampm_btn_am.config(bg="#f0f0f0", fg="#666")
            deadline_ampm_btn_pm.config(bg="#007bff", fg="white")
    
    deadline_ampm_var.trace("w", lambda *args: update_deadline_ampm_style())
    update_deadline_ampm_style()
    
    # Clear deadline button
    clear_deadline_btn = tk.Button(deadline_section, text="Clear Deadline", 
                                  command=lambda: deadline_date_entry.delete(0, tk.END),
                                  font=("Segoe UI", 9), bg="white", fg="#dc3545",
                                  relief="flat", bd=1, highlightthickness=1,
                                  highlightbackground="#ddd", padx=12, pady=5,
                                  cursor="hand2", activebackground="#ffe0e0")
    clear_deadline_btn.pack(anchor="w", pady=(5, 0))
    
    # Done At Section (if task is done)
    done_at_frame = tk.Frame(container, bg="#f5f7fa")
    done_at_frame.pack(fill="x", pady=(0, 20))
    
    done_at_str = str(row.get("done_at") or "")
    if done_at_str:
        try:
            done_at_dt = datetime.strptime(done_at_str, TS_FMT)
            done_at_display = done_at_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            done_at_display = done_at_str
        
        tk.Label(done_at_frame, text="Completed At", bg="#f5f7fa", font=("Segoe UI", 10, "bold"), 
                 fg="#555", anchor="w").pack(fill="x", pady=(0, 8))
        
        done_at_label = tk.Label(done_at_frame, text=done_at_display, 
                                font=("Segoe UI", 10), bg="white", fg="#666",
                                relief="flat", bd=0, highlightthickness=1,
                                highlightbackground="#ddd", anchor="w", padx=15, pady=10)
        done_at_label.pack(fill="x")
    
    # Status label (for errors)
    status_label = tk.Label(container, text="", bg="#f5f7fa", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 15))
    
    def save_changes():
        try:
            # Get task text
            new_task_text = task_text_area.get("1.0", tk.END).strip()
            if not new_task_text:
                status_label.config(text="❌ Task description cannot be empty", fg="#dc3545", bg="#f5f7fa")
                status_label.pack(pady=(0, 15))
                return
            
            # Update task data
            row["task"] = new_task_text
            row["done"] = bool(done_var.get())
            
            # Update done_at
            if row["done"] and not row.get("done_at"):
                row["done_at"] = now_ts()
            elif not row["done"]:
                row["done_at"] = ""
            
            # Update created_at if changed
            try:
                new_created_str = created_entry.get().strip()
                if new_created_str:
                    # Validate format
                    datetime.strptime(new_created_str, "%Y-%m-%d %H:%M:%S")
                    row["created_at"] = new_created_str
            except ValueError:
                status_label.config(text="❌ Invalid created date format. Use: YYYY-MM-DD HH:MM:SS", fg="#dc3545", bg="#f5f7fa")
                status_label.pack(pady=(0, 15))
                return
            
            # Update deadline
            deadline_date = deadline_date_entry.get().strip()
            if deadline_date:
                try:
                    hour = int(deadline_hour_var.get())
                    minute = int(deadline_minute_var.get())
                    ampm = deadline_ampm_var.get()
                    
                    if hour < 1 or hour > 12 or minute < 0 or minute > 59:
                        raise ValueError("Invalid time")
                    
                    # Convert to 24-hour format
                    if ampm == "PM" and hour != 12:
                        hour += 12
                    elif ampm == "AM" and hour == 12:
                        hour = 0
                    
                    time_str = f"{hour:02d}:{minute:02d}"
                    deadline_raw = f"{deadline_date} {time_str}"
                    # Validate format
                    datetime.strptime(deadline_raw, DEADLINE_RAW_FMT)
                    row["deadline"] = deadline_raw
                except ValueError:
                    status_label.config(text="❌ Invalid deadline format. Use: YYYY-MM-DD for date", fg="#dc3545", bg="#f5f7fa")
                    status_label.pack(pady=(0, 15))
                    return
            else:
                row["deadline"] = ""
            
            # Save to data structure
            todo_data[uuid_val] = row
            refresh_todo_tree(selection_uuid=uuid_val)
            persist_todos_to_db(list(todo_tree.get_children()))
            update_status_bar()
            edit_window.destroy()
        except Exception as e:
            status_label.config(text=f"❌ Error: {str(e)}", fg="#dc3545", bg="#f5f7fa")
            status_label.pack(pady=(0, 15))
    
    def on_edit_window_close():
        try:
            canvas.unbind_all("<MouseWheel>")
        except:
            pass
        edit_window.destroy()
    
    # Action buttons
    button_frame = tk.Frame(container, bg="#f5f7fa")
    button_frame.pack(fill="x", pady=(15, 0))
    
    cancel_btn = tk.Button(button_frame, text="Cancel", command=on_edit_window_close,
              bg="white", fg="#666", font=("Segoe UI", 10),
              relief="flat", bd=1, highlightthickness=1,
              highlightbackground="#ddd", padx=16, pady=8,
              cursor="hand2", activebackground="#f5f5f5")
    cancel_btn.pack(side="left", padx=(0, 10))
    
    save_btn = tk.Button(button_frame, text="Save Changes", command=save_changes,
              bg="#28a745", fg="white", font=("Segoe UI", 10, "bold"),
              relief="flat", bd=0, padx=20, pady=8,
              cursor="hand2", activebackground="#218838")
    save_btn.pack(side="right")
    
    # Bind Enter key (Ctrl+Enter to save)
    edit_window.bind('<Control-Return>', lambda e: save_changes())
    edit_window.bind('<Escape>', lambda e: on_edit_window_close())
    
    # Bind window close event
    edit_window.protocol("WM_DELETE_WINDOW", on_edit_window_close)
    
    # Focus on text area
    task_text_area.focus_set()
    task_text_area.select_range("1.0", tk.END)

def clear_selected_timer():
    uuid_val = get_selected_todo_uuid()
    if not uuid_val or uuid_val not in todo_data:
        return
    row = todo_data[uuid_val]
    row["deadline"] = ""
    todo_data[uuid_val] = row
    refresh_todo_tree(selection_uuid=uuid_val)
    persist_todos_to_db(list(todo_tree.get_children()))

todo_menu.add_command(label="Toggle Done", command=toggle_task)
todo_menu.add_command(label="Set Timer...", command=add_timer_with_check)
todo_menu.add_command(label="Clear Timer", command=clear_selected_timer)
todo_menu.add_separator()
todo_menu.add_command(label="Edit Task...", command=edit_selected_task)
todo_menu.add_command(label="Delete Task", command=delete_task)

def show_todo_menu(event):
    try:
        row_id = todo_tree.identify_row(event.y)
        if row_id:
            todo_tree.selection_set(row_id)
    except Exception:
        pass
    todo_menu.tk_popup(event.x_root, event.y_root)

todo_tree.bind("<Button-3>", show_todo_menu)

# Entry & Buttons
todo_entry = tk.Entry(right_frame, font=("Segoe UI", 12), 
                     relief="flat", bg="#f8f9fa")
todo_entry.pack(padx=10, pady=(10, 10), fill="x", ipady=8)
add_placeholder(todo_entry, "Add a new task...")

# Bind Enter key to add task
todo_entry.bind("<Return>", lambda e: add_todo())

button_frame = tk.Frame(right_frame, bg="white")
button_frame.pack(pady=(0, 10))

tk.Button(button_frame, text="➕ Add Task", command=add_todo,
          font=("Segoe UI", 9, "bold"), bg="#28a745", fg="white",
          padx=10, pady=4).pack(side="left", padx=5)
tk.Button(button_frame, text="🗑️ Delete Task", command=delete_task,
          font=("Segoe UI", 9), bg="#dc3545", fg="white",
          padx=10, pady=4).pack(side="left", padx=5)

# Add reorder buttons for todo tree
def move_todo_up():
    sel = get_selected_todo_uuid()
    if not sel:
        return
    children = list(todo_tree.get_children())
    if sel in children:
        idx = children.index(sel)
        if idx > 0:
            todo_tree.move(sel, "", idx - 1)
            persist_todos_to_db(list(todo_tree.get_children()))

def move_todo_down():
    sel = get_selected_todo_uuid()
    if not sel:
        return
    children = list(todo_tree.get_children())
    if sel in children:
        idx = children.index(sel)
        if idx < len(children) - 1:
            todo_tree.move(sel, "", idx + 1)
            persist_todos_to_db(list(todo_tree.get_children()))

tk.Button(button_frame, text="⬆️ Move Up", 
          command=move_todo_up,
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)
tk.Button(button_frame, text="⬇️ Move Down", 
          command=move_todo_down,
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)

# Add keyboard shortcuts info
shortcuts_frame = tk.Frame(right_frame, bg="white")
shortcuts_frame.pack(fill="x", padx=10, pady=(0, 5))
tk.Label(shortcuts_frame, text="💡 Shortcuts: Enter=Add, Space=Toggle, Delete=Remove, ↑↓=Navigate", 
         font=("Segoe UI", 8), bg="white", fg="#666").pack(anchor="w")

# Notes Frame
notes_frame = tk.Frame(scrollable_frame, bg="#ffffff", bd=1, relief="groove")
notes_frame.pack(fill="both", expand=True, padx=20, pady=(20, 20))

title_frame = tk.Frame(notes_frame, bg="white", padx=15, pady=10)
title_frame.pack(fill="x")

tk.Label(title_frame, text="📝 Notes", bg="white", fg="#111", 
         font=("Segoe UI", 14, "bold")).pack(side="left")
tk.Button(title_frame, text="➕ Add New Note", command=add_note_window,
          bg="#007bff", fg="white", font=("Segoe UI", 9),
          padx=10, pady=4).pack(side="right")

notes_listbox = create_scrolled_listbox(notes_frame, 
                          font=("Segoe UI", 13),
                          height=8, selectbackground="#007bff",
                          selectforeground="white", relief="flat",
                          bg="#f8f9fa",
                          padx=15, pady=(0,15))
notes_listbox.bind("<Double-Button-1>", view_note)

# Add reorder buttons for notes
notes_button_frame = tk.Frame(notes_frame, bg="white")
notes_button_frame.pack(pady=(0, 10))

tk.Button(notes_button_frame, text="⬆️ Move Up", 
          command=lambda: move_up(notes_listbox, lambda x: None, update_note_order, []),
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)
tk.Button(notes_button_frame, text="⬇️ Move Down", 
          command=lambda: move_down(notes_listbox, lambda x: None, update_note_order, []),
          font=("Segoe UI", 9), bg="#6c757d", fg="white",
          padx=8, pady=4).pack(side="left", padx=5)

# Start timer updates immediately and then every 30 seconds
def start_timer_updates():
    update_timers()  # Run immediately
    # The update_timers function now schedules itself every 1 second for blinking

# Load saved todos into the table
load_todo_data_from_db()
refresh_todo_tree()

update_status_bar()

# Run initial timer update to format existing deadlines
root.after(1000, update_timers)

# Auto-select first task if available
try:
    children = list(todo_tree.get_children())
    if children:
        todo_tree.selection_set(children[0])
        todo_tree.see(children[0])
except Exception:
    pass

refresh_links()
refresh_notes()

# Start timer updates
start_timer_updates()

# Start optional auto-sync loop
root.after(2000, schedule_auto_sync)

# Developer credit in footer
footer_frame = tk.Frame(scrollable_frame, bg="#eaf4fc")
footer_frame.pack(fill="x", pady=(0, 10))

credit_frame = tk.Frame(footer_frame, bg="#eaf4fc")
credit_frame.pack(expand=True)

credit_text = tk.Label(credit_frame, text="Develop by ", 
                      font=("Segoe UI", 10), bg="#eaf4fc", fg="#666")
credit_text.pack(side="left")

def open_profile(event):
    webbrowser.open_new_tab("https://github.com/needyamin")  # Replace with your actual profile URL

credit_link = tk.Label(credit_frame, text="Md. Yamin Hossain", 
                      font=("Segoe UI", 10, "bold"), bg="#eaf4fc", 
                      fg="#007bff", cursor="hand2")
credit_link.pack(side="left")
credit_link.bind("<Button-1>", open_profile)
credit_link.bind("<Enter>", lambda e: credit_link.config(fg="#0056b3"))
credit_link.bind("<Leave>", lambda e: credit_link.config(fg="#007bff"))

# Test sound function for debugging
def play_sound_background():
    """Test function to debug sound playback"""
    try:
        sound_file = resource_path("assets", "overdue.mp3")
        if os.path.exists(sound_file):
            print(f"Testing sound playback: {sound_file}")  # Debug print
            full_path = os.path.abspath(sound_file)
            print(f"Full path: {full_path}")
            
            # Use threading to play sound in background
            def play_sound_thread():
                try:
                    # Method 1: Try using playsound in background
                    playsound(sound_file, block=False)
                    print("Test: Sound should have played using playsound in background")
                except Exception as e:
                    print(f"Test: Playsound failed: {e}")
                    try:
                        # Method 2: Try using subprocess with start command
                        subprocess.Popen(['start', full_path], shell=True, 
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print("Test: Sound should have played using 'start' command")
                    except Exception as e:
                        print(f"Test: Start command failed: {e}")
                        try:
                            # Method 3: Fallback to system sound (Windows only)
                            if winsound:
                                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
                                print("Test: Sound should have played using winsound")
                            else:
                                print("Test: winsound not available on this platform")
                        except Exception as e:
                            print(f"Test: Winsound failed: {e}")
                            pass
            
            # Start sound in background thread
            threading.Thread(target=play_sound_thread, daemon=True).start()
        else:
            print(f"Test: Sound file not found: {sound_file}")
    except Exception as e:
        print(f"Test: Sound test error: {e}")

# Add a test button for sound (temporary, for debugging)
test_frame = tk.Frame(scrollable_frame, bg="#eaf4fc")
test_frame.pack(fill="x", pady=(0, 10))
tk.Button(test_frame, text="🔊 Test Sound", command=play_sound_background,
          bg="#ffc107", fg="black", font=("Segoe UI", 9),
          padx=10, pady=4).pack()

# Start the datetime update
update_datetime()

# Start GUI loop
root.mainloop()
