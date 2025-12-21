import PyInstaller.__main__
import os
import sys
import shutil

# Centralized logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from logging_config import get_logger
logger = get_logger(__name__)
logger = logging.getLogger(__name__)

def create_exe():
    try:
        logger.info("Starting build process...")
        
        # Get the current directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Define paths
        main_script = os.path.join(current_dir, "index_gui.py")
        icon_path = os.path.join(current_dir, "icon.ico")
        
        # Check if main script exists
        if not os.path.exists(main_script):
            logger.error(f"Main script not found at: {main_script}")
            return False
            
        logger.info(f"Building executable from: {main_script}")
        
        # Clean up previous build artifacts
        for dir_name in ['build', 'dist']:
            if os.path.exists(dir_name):
                logger.info(f"Cleaning up {dir_name} directory...")
                shutil.rmtree(dir_name)
        
        # List of all bot directories to include
        bot_dirs = [
            "withdrawal_complete_bot",
            "withdrawal_submit_bot",
            "profile_info_get",
            "withdrawals_info_get_bot",
            "create_acount_bot",
            "buy_package_bot"
        ]
        
        # PyInstaller arguments
        args = [
            main_script,
            '--name=Otithee_Automation_Suite',
            '--onefile',
            '--windowed',
            '--clean',
            '--noconfirm',
            '--log-level=DEBUG',
        ]
        
        # Add all bot directories
        for bot_dir in bot_dirs:
            bot_path = os.path.join(current_dir, bot_dir)
            if os.path.exists(bot_path):
                args.append(f'--add-data={bot_path};{bot_dir}')
                logger.info(f"Adding directory: {bot_dir}")
        
        # Add hidden imports
        hidden_imports = [
            'PIL',
            'PIL._tkinter_finder',
            'sv_ttk',
            'pandas',
            'openpyxl',
            'requests',
            'bs4',
            'urllib3',
            'dateutil',
            'PyPDF2',
            'tabula',
            'tabula-py',
            'tkinter',
            'tkinter.ttk',
            'tkinter.filedialog',
            'tkinter.messagebox',
            'tkinter.scrolledtext',
            'threading',
            'datetime',
            'logging',
            'json',
            'sys',
            'os',
            'time'
        ]
        
        for imp in hidden_imports:
            args.append(f'--hidden-import={imp}')
        
        # Add icon if exists
        if os.path.exists(icon_path):
            args.append(f'--icon={icon_path}')
            logger.info("Icon file found and will be included")
        
        # Add runtime hooks
        runtime_hook = """
import os
import sys

def _setup_path():
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        base_path = sys._MEIPASS
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Add all bot directories to path
    bot_dirs = [
        'withdrawal_complete_bot',
        'withdrawal_submit_bot',
        'profile_info_get',
        'withdrawals_info_get_bot',
        'create_acount_bot',
        'buy_package_bot'
    ]
    
    for bot_dir in bot_dirs:
        path = os.path.join(base_path, bot_dir)
        if os.path.exists(path):
            sys.path.append(path)

_setup_path()
"""
        
        # Write runtime hook
        hook_path = os.path.join(current_dir, 'hook.py')
        with open(hook_path, 'w') as f:
            f.write(runtime_hook)
        
        args.append(f'--runtime-hook={hook_path}')
        
        logger.info("Running PyInstaller with arguments:")
        for arg in args:
            logger.info(f"  {arg}")
        
        # Run PyInstaller
        PyInstaller.__main__.run(args)
        
        # Clean up hook file
        if os.path.exists(hook_path):
            os.remove(hook_path)
        
        # Verify the executable was created
        exe_path = os.path.join(current_dir, 'dist', 'Otithee_Automation_Suite.exe')
        if os.path.exists(exe_path):
            logger.info(f"Build completed successfully! Executable created at: {exe_path}")
            return True
        else:
            logger.error("Build completed but executable was not found!")
            return False
        
    except Exception as e:
        logger.error(f"Build failed with error: {str(e)}")
        return False

if __name__ == "__main__":
    success = create_exe()
    if not success:
        sys.exit(1) 