#!/usr/bin/env python3
"""
Shared utility for setting window icons across all GUI applications.
Ensures all windows use the same icon.ico from the project root.
Cross-platform compatible (Windows, Linux, macOS).
"""

import os
import sys
import platform
import tkinter as tk


def get_project_root():
    """Find the project root directory by looking for icon.ico"""
    # Get the directory of the current file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if icon.ico exists in current directory
    icon_path = os.path.join(current_dir, "icon.ico")
    if os.path.exists(icon_path):
        return current_dir
    
    # If not, go up directories until we find it
    parent = os.path.dirname(current_dir)
    while parent != current_dir:
        icon_path = os.path.join(parent, "icon.ico")
        if os.path.exists(icon_path):
            return parent
        current_dir = parent
        parent = os.path.dirname(current_dir)
    
    # Fallback: return the directory of this file (project root should be here)
    return os.path.dirname(os.path.abspath(__file__))


def get_icon_path():
    """Get the path to icon.ico in the project root"""
    project_root = get_project_root()
    return os.path.join(project_root, "icon.ico")


def set_window_icon(window):
    """Set icon for a window if icon file exists - cross-platform compatible"""
    try:
        icon_path = get_icon_path()
        if not os.path.exists(icon_path):
            return
        
        system = platform.system()
        
        # Windows: use iconbitmap (works best with .ico files)
        if system == "Windows":
            window.iconbitmap(icon_path)
        else:
            # Linux/macOS: try iconbitmap first, fallback to iconphoto with PIL
            try:
                window.iconbitmap(icon_path)
            except (tk.TclError, Exception):
                # Fallback: use PIL/Pillow to load image and set as iconphoto
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(icon_path)
                    # Convert to format that works on Linux
                    photo = ImageTk.PhotoImage(img)
                    window.iconphoto(False, photo)
                    # Keep a reference to prevent garbage collection
                    window._icon_photo = photo
                except ImportError:
                    # PIL not available, try alternative formats
                    # Check for .xbm or .xpm files
                    base_path = os.path.splitext(icon_path)[0]
                    for ext in ['.xbm', '.xpm', '.png']:
                        alt_path = base_path + ext
                        if os.path.exists(alt_path):
                            try:
                                window.iconbitmap(alt_path)
                                return
                            except:
                                continue
                except Exception:
                    # All methods failed, silently continue
                    pass
    except Exception:
        # Silently fail - icon is optional
        pass

