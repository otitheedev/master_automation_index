# QA Testing Automation Tool

This script provides comprehensive automated QA testing for web applications, specifically designed for testing the HR management system.

## Features

- **Automatic Login**: Logs into the application using predefined admin credentials
- **Link Testing**: Crawls through all accessible pages and tests all internal/external links
- **Form Testing**: Finds and tests all forms by filling required fields and submitting them
- **CSV Report Generation**: Generates detailed test reports in CSV format for analysis
- **Real-time Logging**: Provides live progress updates and detailed logs

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure Chrome browser is installed (required for Selenium automation)

## Usage

1. Run the testing script:
```bash
python testing.py
```

2. Configure the Base URL (default: http://localhost:8000/)

3. Specify the output CSV file path (default: Testing Report All/record.csv)

4. Click "Start QA Testing" to begin the automated testing process

## Test Coverage

### Link Testing
- Tests all internal links within the application domain
- Verifies HTTP response codes
- Records external links for reference
- Crawls up to 50 pages per test run

### Form Testing
- Identifies all forms on each page
- Fills required fields with appropriate test data
- Submits forms and checks for success/error indicators
- Handles different field types (text, email, password, select, etc.)

### Test Data Generation
- Generates realistic test data based on field types and names
- Email fields: `test@example.com`
- Phone fields: `01712345678`
- Name fields: `Test User`
- Password fields: `TestPass123!`

## Output CSV Format

The generated CSV file contains the following columns:

- `type`: Test type (page_load, internal_link, external_link, form_submission)
- `url`: Page URL where the test was performed
- `link_url`: Target URL (for links) or form action (for forms)
- `link_text`: Link text or form identifier
- `status`: Test result (PASS, FAIL, ERROR, UNKNOWN, EXTERNAL)
- `response_time`: Response time (currently N/A for most tests)
- `error_message`: Error details if test failed
- `timestamp`: When the test was performed

## Test Results Interpretation

- **PASS**: Test completed successfully
- **FAIL**: Test failed (HTTP error, validation error, etc.)
- **ERROR**: Unexpected error during testing
- **UNKNOWN**: Could not determine test result
- **EXTERNAL**: External link (not tested)

## Browser Behavior

- The Chrome browser will remain open after testing for manual inspection
- All testing actions are performed automatically
- Progress is shown in real-time in the application log

## Configuration

The script uses the following default configuration:

- **Base URL**: `http://localhost:8000/`
- **Login Email**: `mirajul13041@gmail.com`
- **Login Password**: `@Aa12345` (stored in code)
- **Output File**: `Testing Report All/record.csv`

## Troubleshooting

### Common Issues

1. **Chrome Driver Issues**: Make sure Chrome browser is installed and up to date
2. **Login Failures**: Verify the base URL and credentials are correct
3. **Permission Errors**: Ensure write permissions for the output CSV file location
4. **Network Timeouts**: Check network connectivity and application availability

### Logs

All testing activities are logged with detailed information. Check the log area for:
- Login attempts and results
- Page loading status
- Link testing progress
- Form submission results
- Error messages and debugging information

## Security Note

This tool contains hardcoded credentials for testing purposes. In production environments, consider using environment variables or secure credential management.
