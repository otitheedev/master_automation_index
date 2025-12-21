# Centralized configuration for Otithee automation scripts

# ========== ADMINISTRATOR (Main Admin) ==========
# Main admin URLs
ADMIN_LOGIN_URL = "https://administrator.otithee.com/login"
ADMIN_BASE_URL = "https://administrator.otithee.com"
ADMIN_TARGET_URL = f"{ADMIN_BASE_URL}/agent-ranking/agent/edit/"

# Administrator credentials
ADMIN_EMAIL_OR_MOBILE = "0187857850401878578504"
ADMIN_PASSWORD = "*#r@@t2025#"

# ========== ACCOUNTING (Change Referer) ==========
# Accounting URLs
ACCOUNTING_LOGIN_URL = "https://accounting.test/login"
ACCOUNTING_CHANGE_REFERER_URL = "https://accounting.test/change-referer"

# Accounting credentials
ACCOUNTING_USERNAME = "needyamin@otithee.com"
ACCOUNTING_PASSWORD = "Y123456789"

# ========== GATEWAY ==========
GATEWAY_URL = "https://gateway.otithee.com"

# ========== SELENIUM SETTINGS ==========
# Browser settings
HEADLESS_MODE = False  # True to run without opening Chrome window
BROWSER_WINDOW_SIZE = (1200, 900)

# Wait timeouts (tune if your server is slow)
PAGE_WAIT = 15        # general wait for pages/elements
POPULATE_WAIT = 30    # wait for AJAX population after entering entrepreneurNumber
SHORT_WAIT = 3        # quick detection for loader visibility

# ========== DEFAULT FILE PATHS ==========
# Change Referer defaults
DEFAULT_REFERER_INPUT_CSV = "data.csv"
DEFAULT_REFERER_OUTPUT_CSV = "results.csv"

# Number & Name Change defaults
DEFAULT_NUMBER_INPUT_FILE = "data.xlsx"  # Can be .xlsx or .csv
DEFAULT_NUMBER_OUTPUT_FILE = "output.csv"

# ========== BACKWARD COMPATIBILITY ALIASES ==========
# For existing code that uses old variable names
LOGIN_URL = ADMIN_LOGIN_URL
BASE_URL = ADMIN_BASE_URL
TARGET_URL = ADMIN_TARGET_URL
EMAIL_OR_MOBILE = ADMIN_EMAIL_OR_MOBILE
PASSWORD = ADMIN_PASSWORD

# ========== TEST/DEVELOPMENT (commented out) ==========
# Uncomment to use test environment:
# ADMIN_LOGIN_URL = "http://administrator.test/login"
# ADMIN_BASE_URL = "http://administrator.test"
# ADMIN_TARGET_URL = f"{ADMIN_BASE_URL}/agent-ranking/agent/edit/"
# ACCOUNTING_LOGIN_URL = "http://accounting.test/login"
# ACCOUNTING_CHANGE_REFERER_URL = "http://accounting.test/change-referer"
# GATEWAY_URL = "http://gateway.test"
# LOGIN_URL = ADMIN_LOGIN_URL
# BASE_URL = ADMIN_BASE_URL
# TARGET_URL = ADMIN_TARGET_URL
# EMAIL_OR_MOBILE = ADMIN_EMAIL_OR_MOBILE
# PASSWORD = ADMIN_PASSWORD