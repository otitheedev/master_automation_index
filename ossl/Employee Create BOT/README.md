# HR Employee CSV Importer

An automated tool to bulk import employee data from CSV files into your HR system using Selenium WebDriver. This application provides a user-friendly GUI for importing employee information including personal details, department, designation, and office location.

## Features

- ✅ **Bulk Employee Import**: Import multiple employees from a CSV file at once
- ✅ **Automatic Form Filling**: Automatically fills all required fields in the employee creation form
- ✅ **Smart Field Mapping**: Maps CSV columns to form fields (name, phone, department, designation, office)
- ✅ **Phone Number Normalization**: Automatically adds leading "0" to phone numbers if missing
- ✅ **Searchable Dropdown Support**: Handles custom searchable dropdown fields for department and designation
- ✅ **Real-time Logging**: View progress and errors in real-time through the GUI
- ✅ **Error Handling**: Robust error handling with detailed logging for troubleshooting

## Prerequisites

### System Requirements

- **Python 3.8 or higher**
- **Google Chrome browser** (latest version recommended)
- **Internet connection** (for downloading ChromeDriver and accessing the HR system)

### Python Packages

All required Python packages are listed in `requirements.txt`.

## Installation

### 1. Clone or Download the Project

```bash
cd "/home/needyamin/Desktop/INSERT BOT"
```

### 2. Create a Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Tkinter (if not already installed)

**On Ubuntu/Debian:**
```bash
sudo apt-get install python3-tk
```

**On CentOS/RHEL:**
```bash
sudo yum install python3-tkinter
```

**On macOS:**
Tkinter is usually included with Python. If not, install via Homebrew:
```bash
brew install python-tk
```

**On Windows:**
Tkinter is usually included with Python installations.

## CSV File Format

Your CSV file should have the following columns (case-insensitive):

| Column Name | Description | Required | Example |
|------------|-------------|----------|---------|
| `EMPLOYEE NAME` | Full name of the employee | ✅ Yes | "MD. YAMIN HOSSAIN" |
| `CLEAN NUMBER` | Phone number (will auto-add leading 0 if missing) | ✅ Yes | "1712573270" or "01712573270" |
| `OFFICE LOCATION` | Office location | ⚠️ Optional | "HEAD OFFICE", "CHITTAGONG OFFICE", "SYLHET OFFICE" |
| `DESIGNATION` | Job designation/title | ⚠️ Optional | "SR. SOFTWARE ENGINEER", "MANAGER" |
| `DEPARTMENT` | Department name | ⚠️ Optional | "IT DEPARTMENT", "HR & ADMIN" |

### CSV Example

```csv
Sr.,EMPLOYEE NAME,OFFICE LOCATION,Office Code,DESIGNATION,DEPARTMENT,CLEAN NUMBER,OFFICE
1,MD. YAMIN HOSSAIN,HEAD OFFICE,HO,SR. SOFTWARE ENGINEER,IT DEPARTMENT,1712573270,DHAKA OFFICE - 8TH FLOOR
2,LN. REAR ADMIRAL ABU TAHER,HEAD OFFICE,HO,ADVISOR,OPERATION,1714006794,DHAKA OFFICE - 8TH FLOOR
```

**Note:** The script will automatically:
- Normalize phone numbers (add "0" prefix if missing)
- Map office locations to office IDs
- Match department and designation names to dropdown options

## Usage

### Running the Application

1. **Activate your virtual environment** (if using one):
   ```bash
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate    # Windows
   ```

2. **Run the script**:
   ```bash
   python automation.py
   ```

3. **The GUI will open** with the following interface:
   - **Base URL**: Enter your HR system URL (default: `https://o-erp.otithee.com/`)
   - **CSV File**: Click "Browse…" to select your CSV file
   - **Start Import**: Click to begin the import process

### Step-by-Step Guide

1. **Launch the Application**
   - Run `python automation.py` from the command line
   - The GUI window will appear

2. **Configure Settings**
   - **Base URL**: Verify or update the base URL of your HR system
   - The application uses built-in admin credentials (configured in code)

3. **Select CSV File**
   - Click the "Browse…" button
   - Navigate to and select your employee CSV file
   - The file path will appear in the text field

4. **Start Import**
   - Click the "Start Import" button
   - A Chrome browser window will open automatically
   - The application will:
     - Log in to the HR system
     - Navigate to the employee creation page
     - Fill in employee data for each row
     - Submit the form
     - Move to the next employee

5. **Monitor Progress**
   - Watch the log area for real-time updates
   - Success messages will appear for each employee created
   - Errors will be logged with details for troubleshooting

6. **Completion**
   - When finished, the browser will navigate to the employees list
   - A summary will be displayed in the logs
   - The browser window will remain open for verification

## Configuration

### Changing Admin Credentials

Edit `automation.py` and update these lines (around line 30-31):

```python
ADMIN_EMAIL = "your-email@example.com"
ADMIN_PASSWORD = "your-password"
```

### Changing Default Base URL

Edit `automation.py` and update this line (around line 23):

```python
BASE_URL_DEFAULT = "https://your-hr-system-url.com/"
```

## Troubleshooting

### Common Issues

#### 1. **"ChromeDriver not found" or "ChromeDriver version mismatch"**
   - **Solution**: The `webdriver-manager` package automatically downloads the correct ChromeDriver. Ensure you have internet connectivity.

#### 2. **"Tkinter not found" or "No module named '_tkinter'"**
   - **Solution**: Install Tkinter using the commands in the Installation section above.

#### 3. **"Login failed" or "Could not locate email or password fields"**
   - **Solution**: 
     - Verify the base URL is correct
     - Check that admin credentials are correct
     - Ensure the login page structure hasn't changed

#### 4. **"Could not find option matching 'X' in dropdown"**
   - **Solution**: 
     - Verify the department/designation name in CSV exactly matches an option in the system
     - Check for typos or extra spaces
     - The matching is case-insensitive but must be a partial match

#### 5. **"Missing employee name or phone"**
   - **Solution**: Ensure your CSV has the required columns (`EMPLOYEE NAME` and `CLEAN NUMBER`)

#### 6. **Browser opens but doesn't fill forms**
   - **Solution**: 
     - Check the log messages for specific errors
     - Verify the form structure hasn't changed
     - Ensure JavaScript is enabled in Chrome

### Debug Mode

To see more detailed logging, check the log widget in the GUI. All operations are logged with timestamps and error details.

## Office Location Mapping

The script automatically maps office locations to office IDs:

| CSV Office Location | Office ID | Description |
|---------------------|-----------|-------------|
| "HEAD OFFICE", "HO", contains "dhaka" | 1 | Head Office (HO) |
| "CHITTAGONG OFFICE", "CTG", contains "chittagong" | 2 | Branch Office - Chittagong (CTG) |
| "SYLHET OFFICE", "SYL", contains "sylhet" | 3 | Branch Office - Sylhet (SYL) |

## Phone Number Format

- Phone numbers are automatically normalized to start with "0"
- If CSV has `1712573270`, it becomes `01712573270`
- If CSV already has `01712573270`, it stays as is
- Empty phone numbers are skipped (row will not be processed)

## Security Notes

⚠️ **Important Security Considerations:**

- Admin credentials are hardcoded in the script
- For production use, consider:
  - Using environment variables for credentials
  - Implementing a secure credential storage system
  - Adding user authentication to the GUI
  - Restricting file access permissions

## Limitations

- The script processes one employee at a time (sequential processing)
- Browser window must remain open during import
- Requires stable internet connection
- Chrome browser must be installed
- Form structure changes may require code updates

## Support

For issues or questions:
1. Check the log messages in the GUI for specific error details
2. Verify your CSV format matches the required structure
3. Ensure all prerequisites are installed correctly
4. Check that the HR system is accessible and the form structure hasn't changed

## License

This project is provided as-is for internal use.

## Version History

- **v1.0** - Initial release with basic employee import functionality
- **v1.1** - Added department and designation support with searchable dropdowns
- **v1.2** - Added phone number normalization (auto-add leading 0)

---

**Note:** This tool is designed for the specific HR system at `https://o-erp.otithee.com/`. Modifications may be required for use with other systems.

