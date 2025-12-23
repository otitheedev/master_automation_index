#!/usr/bin/env python3
"""
Shared SQLite settings database for ALL tools in this project.

File location:
    <project_root>/settings.db

Usage patterns:
    from settings_db import get_connection, get_setting, set_setting

    # Simple key/value storage (string values)
    set_setting("otithee_admin_email", "admin@example.com")
    email = get_setting("otithee_admin_email", default="fallback@example.com")
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """
    Best-effort project root:
    - This file lives in project root, so we just return its parent directory.
    """
    return Path(__file__).resolve().parent


def get_settings_db_path() -> Path:
    """
    Absolute path to the shared settings DB:
        <project_root>/settings.db
    """
    root = get_project_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.db"


def _ensure_settings_schema(conn: sqlite3.Connection) -> None:
    """
    Ensure that the minimal schema for generic settings exists.
    NOTE: The MySQL Backup Tool may create additional tables
    (saved_connections, backup_locations, backup_history, settings).
    We only care that a generic key/value table exists.
    """
    cur = conn.cursor()
    # Use a simple key/value table named 'settings' for global storage.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()


def get_connection() -> sqlite3.Connection:
    """
    Get a connection to the shared settings DB.
    Creates the DB file and minimal schema if needed.
    """
    db_path = get_settings_db_path()
    # Ensure parent dir exists
    os.makedirs(db_path.parent, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    _ensure_settings_schema(conn)
    return conn


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Fetch a single string setting by key from the shared DB.
    Returns default if key is missing or any error occurs.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        if row is None:
            return default
        return row[0]
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    """
    Store a single string setting into the shared DB.
    Swallows errors so callers don't crash the GUI on failure.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
        conn.close()
    except Exception:
        # Best-effort; ignore failures.
        pass


