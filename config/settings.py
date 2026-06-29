"""
FinScreen configuration — loads from environment variables.
All Plaid credentials come from the environment; never hardcoded.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Plaid credentials ---
PLAID_CLIENT_ID: str = os.environ.get("PLAID_CLIENT_ID", "")#,fallback to an empty string
PLAID_SECRET: str = os.environ.get("PLAID_SECRET", "")
PLAID_ENV: str = os.environ.get("PLAID_ENV", "sandbox")

# --- Derived base URL ---
_BASE_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}
PLAID_BASE_URL: str = _BASE_URLS.get(PLAID_ENV, _BASE_URLS["sandbox"])#, fallback to sandbox

# --- FinScreen loan assessment defaults ---
FINSCREEN_CURRENCY: str = os.environ.get("FINSCREEN_CURRENCY", "NGN")

# --- Validation: warn loudly at startup if creds are missing ---
def validate_config() -> list[str]:
    """Return a list of missing required config keys. Empty = all good."""
    missing = []
    if not PLAID_CLIENT_ID:
        missing.append("PLAID_CLIENT_ID")
    if not PLAID_SECRET:
        missing.append("PLAID_SECRET")
    return missing