#!/usr/bin/env python3
"""
Build script to create Task.appimage for the entire project.
This script uses PyInstaller to create a standalone executable and packages it as an AppImage.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Project configuration
PROJECT_NAME = "Task"
APPIMAGE_NAME = "Task.appimage"
MAIN_SCRIPT = "task.py"
ICON_FILE = "icon.ico"

# Directories to include
INCLUDE_DIRS = [
    "automation_otithee",
    "ossl",
    "mysql_client",
]

# Files to include
INCLUDE_FILES = [
    "icon.ico",
    "icon_utils.py",
    "logging_config.py",
    "requirements.txt",
]

# Hidden imports that PyInstaller might miss
HIDDEN_IMPORTS = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.scrolledtext",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "sv_ttk",
    "pandas",
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.chrome",
    "selenium.webdriver.chrome.service",
    "selenium.webdriver.common.by",
    "selenium.webdriver.support",
    "selenium.webdriver.support.ui",
    "selenium.webdriver.support.expected_conditions",
    "webdriver_manager",
    "webdriver_manager.chrome",
    "requests",
    "bs4",
    "pytz",
    "playsound",
    "boto3",
    "botocore",
    "sqlite3",
    "threading",
    "subprocess",
    "importlib",
    "importlib.util",
    "icon_utils",
    "logging_config",
    "automation_otithee.config",
]

def check_dependencies():
    """Check if required build tools are installed."""
    print("Checking dependencies...")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found.")
        print("  Attempting to install PyInstaller...")
        try:
            # Try with --user flag first
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pyinstaller"])
            print("✓ PyInstaller installed (user install)")
        except subprocess.CalledProcessError:
            try:
                # Try with --break-system-packages (for Python 3.12+)
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyinstaller"])
                print("✓ PyInstaller installed")
            except subprocess.CalledProcessError:
                print("⚠ Could not install PyInstaller automatically.")
                print("  Please install manually:")
                print("    pip install --user pyinstaller")
                print("  Or if using a virtual environment:")
                print("    pip install pyinstaller")
                print("  Or with system packages:")
                print("    pip install --break-system-packages pyinstaller")
                return None
    
    # Check if appimagetool is available
    appimagetool_path = shutil.which("appimagetool")
    if not appimagetool_path:
        # Check common locations
        possible_paths = [
            os.path.expanduser("~/appimagetool"),
            "/usr/local/bin/appimagetool",
            "/usr/bin/appimagetool",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                appimagetool_path = path
                break
    
    if not appimagetool_path:
        print("\n⚠ WARNING: appimagetool not found!")
        print("To create an AppImage, you need appimagetool.")
        print("Download it from: https://github.com/AppImage/AppImageKit/releases")
        print("Or install via: wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage")
        print("Then: chmod +x appimagetool-x86_64.AppImage && sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool")
        return None
    
    print(f"✓ appimagetool found at: {appimagetool_path}")
    return appimagetool_path

def clean_build_dirs():
    """Clean up previous build artifacts."""
    print("\nCleaning up previous build artifacts...")
    dirs_to_clean = ['build', 'dist', f'{PROJECT_NAME}.AppDir', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"  Removing {dir_name}/...")
            shutil.rmtree(dir_name)
    
    # Clean .spec files
    for spec_file in Path('.').glob('*.spec'):
        if spec_file.name != f'{PROJECT_NAME}.spec':
            try:
                spec_file.unlink()
            except:
                pass

def build_with_pyinstaller():
    """Build the executable using PyInstaller."""
    print(f"\nBuilding {PROJECT_NAME} with PyInstaller...")
    
    # Get project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    main_script_path = os.path.join(project_root, MAIN_SCRIPT)
    icon_path = os.path.join(project_root, ICON_FILE) if os.path.exists(os.path.join(project_root, ICON_FILE)) else None
    
    if not os.path.exists(main_script_path):
        raise FileNotFoundError(f"Main script not found: {main_script_path}")
    
    # Build PyInstaller arguments
    args = [
        sys.executable, "-m", "PyInstaller",
        main_script_path,
        '--name', PROJECT_NAME,
        '--onefile',
        '--windowed',  # No console window
        '--clean',
        '--noconfirm',
    ]
    
    # Add icon if available
    if icon_path and os.path.exists(icon_path):
        args.extend(['--icon', icon_path])
        print(f"  Using icon: {icon_path}")
    
    # Add hidden imports
    for imp in HIDDEN_IMPORTS:
        args.extend(['--hidden-import', imp])
    
    # Add data files and directories
    # Use ':' separator for Linux (PyInstaller uses this format)
    data_sep = ':'
    for dir_name in INCLUDE_DIRS:
        dir_path = os.path.join(project_root, dir_name)
        if os.path.exists(dir_path):
            # Use --add-data for PyInstaller
            args.extend(['--add-data', f'{dir_path}{data_sep}{dir_name}'])
            print(f"  Including directory: {dir_name}/")
    
    # Add individual files
    for file_name in INCLUDE_FILES:
        file_path = os.path.join(project_root, file_name)
        if os.path.exists(file_path):
            target_dir = os.path.dirname(file_name) or '.'
            args.extend(['--add-data', f'{file_path}{data_sep}{target_dir}'])
            print(f"  Including file: {file_name}")
    
    # Add collect-all for certain packages
    collect_packages = ['selenium', 'pandas', 'PIL', 'tkinter']
    for pkg in collect_packages:
        args.extend(['--collect-all', pkg])
    
    print(f"\nRunning: {' '.join(args)}\n")
    
    # Run PyInstaller
    result = subprocess.run(args, cwd=project_root)
    if result.returncode != 0:
        raise RuntimeError("PyInstaller build failed")
    
    # Check if executable was created
    exe_path = os.path.join(project_root, 'dist', PROJECT_NAME)
    if not os.path.exists(exe_path):
        raise FileNotFoundError(f"Executable not found at: {exe_path}")
    
    print(f"✓ Executable created: {exe_path}")
    return exe_path

def create_appdir(exe_path, appimagetool_path):
    """Create AppDir structure for AppImage."""
    print(f"\nCreating AppDir structure...")
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    appdir_path = os.path.join(project_root, f'{PROJECT_NAME}.AppDir')
    
    # Create AppDir structure
    dirs_to_create = [
        appdir_path,
        os.path.join(appdir_path, 'usr'),
        os.path.join(appdir_path, 'usr', 'bin'),
        os.path.join(appdir_path, 'usr', 'share'),
        os.path.join(appdir_path, 'usr', 'share', 'applications'),
        os.path.join(appdir_path, 'usr', 'share', 'icons'),
        os.path.join(appdir_path, 'usr', 'share', 'icons', 'hicolor'),
        os.path.join(appdir_path, 'usr', 'share', 'icons', 'hicolor', '256x256'),
        os.path.join(appdir_path, 'usr', 'share', 'icons', 'hicolor', '256x256', 'apps'),
    ]
    
    for dir_path in dirs_to_create:
        os.makedirs(dir_path, exist_ok=True)
    
    # Copy executable
    target_exe = os.path.join(appdir_path, 'usr', 'bin', PROJECT_NAME)
    shutil.copy2(exe_path, target_exe)
    os.chmod(target_exe, 0o755)
    print(f"  Copied executable to: {target_exe}")
    
    # Copy icon
    icon_path = os.path.join(project_root, ICON_FILE)
    if os.path.exists(icon_path):
        # Copy to AppDir root (for AppImage)
        shutil.copy2(icon_path, os.path.join(appdir_path, f'{PROJECT_NAME}.png'))
        # Copy to icon directory
        icon_target = os.path.join(appdir_path, 'usr', 'share', 'icons', 'hicolor', '256x256', 'apps', f'{PROJECT_NAME}.png')
        shutil.copy2(icon_path, icon_target)
        print(f"  Copied icon to: {icon_target}")
    
    # Create .desktop file
    desktop_content = f"""[Desktop Entry]
Type=Application
Name={PROJECT_NAME}
Comment=Advanced Daily Dashboard with Automation Tools
Exec={PROJECT_NAME}
Icon={PROJECT_NAME}
Terminal=false
Categories=Utility;Office;
"""
    desktop_path = os.path.join(appdir_path, f'{PROJECT_NAME}.desktop')
    with open(desktop_path, 'w') as f:
        f.write(desktop_content)
    os.chmod(desktop_path, 0o755)
    
    # Also create in applications directory
    app_desktop_path = os.path.join(appdir_path, 'usr', 'share', 'applications', f'{PROJECT_NAME}.desktop')
    shutil.copy2(desktop_path, app_desktop_path)
    print(f"  Created .desktop file: {desktop_path}")
    
    # Create AppRun script
    apprun_content = f"""#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${{HERE}}/usr/bin/{PROJECT_NAME}" "$@"
"""
    apprun_path = os.path.join(appdir_path, 'AppRun')
    with open(apprun_path, 'w') as f:
        f.write(apprun_content)
    os.chmod(apprun_path, 0o755)
    print(f"  Created AppRun: {apprun_path}")
    
    return appdir_path

def create_appimage(appdir_path, appimagetool_path):
    """Create the final AppImage."""
    print(f"\nCreating AppImage...")
    
    project_root = os.path.dirname(os.path.abspath(__file__))
    appimage_path = os.path.join(project_root, APPIMAGE_NAME)
    
    # Remove existing AppImage if it exists
    if os.path.exists(appimage_path):
        os.remove(appimage_path)
        print(f"  Removed existing {APPIMAGE_NAME}")
    
    # Run appimagetool
    args = [appimagetool_path, appdir_path, appimage_path]
    print(f"  Running: {' '.join(args)}")
    
    result = subprocess.run(args, cwd=project_root)
    if result.returncode != 0:
        raise RuntimeError("AppImage creation failed")
    
    # Make AppImage executable
    os.chmod(appimage_path, 0o755)
    
    # Get file size
    size_mb = os.path.getsize(appimage_path) / (1024 * 1024)
    print(f"✓ AppImage created: {appimage_path} ({size_mb:.2f} MB)")
    
    return appimage_path

def main():
    """Main build function."""
    print("=" * 60)
    print(f"Building {APPIMAGE_NAME}")
    print("=" * 60)
    
    try:
        # Check dependencies
        appimagetool_path = check_dependencies()
        if not appimagetool_path:
            print("\n⚠ Cannot proceed without appimagetool.")
            print("The executable will still be built, but AppImage creation will be skipped.")
            build_executable_only = True
        else:
            build_executable_only = False
        
        # Clean previous builds
        clean_build_dirs()
        
        # Build executable
        exe_path = build_with_pyinstaller()
        
        if build_executable_only:
            print(f"\n✓ Build complete! Executable: {exe_path}")
            print("⚠ AppImage not created (appimagetool not found)")
            return
        
        # Create AppDir
        appdir_path = create_appdir(exe_path, appimagetool_path)
        
        # Create AppImage
        appimage_path = create_appimage(appdir_path, appimagetool_path)
        
        print("\n" + "=" * 60)
        print("✓ Build completed successfully!")
        print("=" * 60)
        print(f"\nAppImage location: {appimage_path}")
        print(f"\nTo run the AppImage:")
        print(f"  ./{APPIMAGE_NAME}")
        print(f"\nTo make it executable (if needed):")
        print(f"  chmod +x {APPIMAGE_NAME}")
        
    except Exception as e:
        print(f"\n✗ Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

