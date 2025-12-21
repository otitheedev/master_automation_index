# Daily Dashboard - Advanced Task Management & Automation Suite

A comprehensive Python application for daily task management with integrated automation tools for MySQL backups, Otithee automation, and OSSL automation.

## 🚀 Features

### 📋 Core Features
- **Task Management**: Create, edit, and manage tasks with deadlines and timers
- **Notes**: Create and manage detailed notes with rich text editing
- **Useful Links**: Quick access to frequently used URLs
- **Deadline Tracking**: Real-time countdown with visual alerts and sound notifications
- **Search**: Quick search functionality for tasks
- **Cloud Sync**: Optional HTTP, FTP, or S3 synchronization

### 🛠️ Integrated Automation Tools

#### MySQL Backup Tool
- GUI-based MySQL database backup management
- Save and manage multiple connection presets
- Backup history tracking
- Secure credential storage with SQLite
- Cross-platform support (Linux/Windows)

#### Otithee Automation Suite
- **Profile Info Scraper**: Extract agent profile information
- **Buy Package Bot**: Automate package purchases
- **Withdrawal Submit Bot**: Automate withdrawal submissions
- **Withdrawal Complete Bot**: Streamline withdrawal completion
- **Change Referer Name**: Batch process referer name changes
- **Number & Name Change**: Automate agent number and name changes
- All tools feature editable credentials and CSV file dialogs defaulting to current directory

#### OSSL Automation Suite
- **Download PDF Bot (ACC)**: Automate PDF downloads from ACC system
- **Employee Create BOT**: Batch employee creation with validation
- **Testing Report All**: Comprehensive QA testing with Playwright
- All tools feature editable credentials and centralized logging

## 📦 Installation

### Prerequisites
- Python 3.12 or higher
- Linux or Windows

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python task.py
```

## 🛠️ Building AppImage

Build the entire project as a portable AppImage:

```bash
# Install appimagetool (one-time setup)
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

# Build AppImage
python3 build.py
```

**Output**: `Task.appimage` - A portable, self-contained application that runs on any Linux distribution.

## 📁 Project Structure

```
sqlClient_python/
├── task.py                    # Main dashboard application
├── build.py                   # Build script for AppImage
├── icon.ico                   # Application icon
├── icon_utils.py             # Centralized icon management
├── logging_config.py         # Centralized logging configuration
├── requirements.txt          # Python dependencies
├── automation_otithee/      # Otithee automation tools
│   ├── index_gui.py         # Main GUI launcher
│   ├── config.py            # Centralized configuration
│   └── [various tools]/     # Individual automation tools
├── ossl/                    # OSSL automation tools
│   ├── index_gui.py         # Main GUI launcher
│   └── [various tools]/     # Individual automation tools
└── mysql_client/            # MySQL backup tool
    └── mysql_backup_gui.py
```

## 🎯 Usage

### Main Dashboard
- **Add Task**: Type in the input field and press Enter
- **Set Deadline**: Right-click task → "Set Timer..." or click "⏰ Add Timer"
- **Edit Task**: Right-click → "Edit Task..." for comprehensive editing
- **Search**: Type in search box and press Enter to find tasks
- **Manage Links/Notes**: Use the respective "Add" buttons

### Automation Tools
Access via **Tools** menu:
- **MySQL Backup Tool**: Database backup management
- **Otithee Automation**: Launch Otithee automation suite
- **OSSL Automation**: Launch OSSL automation suite

All automation tools feature:
- Editable credentials in GUI
- CSV/Excel file dialogs defaulting to current directory
- Centralized configuration management
- Consistent icon and window management

## 🔧 Configuration

### Database
- Default location: `%APPDATA%\DailyDashboard\database\sweethart.db` (Windows)
- Portable mode: Create `portable.txt` file next to `task.py` to use `./database/sweethart.db`

### Cloud Sync (Optional)
Configure in **Tools → Settings**:
- **HTTP Sync**: Custom server synchronization
- **FTP Sync**: FTP server synchronization
- **S3 Sync**: Amazon S3 or S3-compatible storage

## 📋 Dependencies

See `requirements.txt` for complete list. Key dependencies:
- `pytz` - Timezone handling
- `playsound` - Sound playback
- `boto3` - S3 sync support
- `pandas` - Data processing
- `selenium` - Browser automation
- `playwright` - Advanced browser automation
- `Pillow` - Image processing
- `sv-ttk` - Modern Tkinter themes

## 🆕 Recent Updates

- ✨ **Integrated Automation Tools**: MySQL Backup, Otithee Automation, and OSSL Automation suites
- ✨ **Editable Credentials**: All automation tools now feature GUI-based credential management
- ✨ **Smart File Dialogs**: CSV/Excel file dialogs automatically open in each tool's directory
- ✨ **Centralized Configuration**: Shared config files for consistent settings across tools
- ✨ **Centralized Logging**: Unified logging system across all automation tools
- ✨ **Icon Management**: Single icon file used across all GUIs with proper path resolution
- ✨ **AppImage Build**: Complete build script for creating portable Linux AppImage
- ✨ **Cross-Platform Support**: Full compatibility with Linux and Windows
- ✨ **Improved Error Handling**: Better error messages and fallback mechanisms

## 🐛 Troubleshooting

**Import Errors**: Ensure all dependencies are installed: `pip install -r requirements.txt`

**Icon Not Loading**: Icon file should be in project root as `icon.ico`

**Build Issues**: Ensure `appimagetool` is installed and in PATH for AppImage creation

**Database Issues**: Delete database file to reset (location shown in status bar)

## 📄 License

MIT License - See LICENSE file for details

---

**Made with ❤️ for productive daily management and automation**
