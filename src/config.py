"""
Central configuration. Endpoint paths and matching thresholds live here,
isolated from logic, so both live-demo changes and any mismatch against
the real /api/docs spec are one-file fixes.

CONFIRMED against a real curl response (2026-09-14):
  {"data": [...], "page": 1, "page_size": 50, "total": 31}
Query params confirmed via Swagger: q, city, state, zip, street,
parent_id, page, page_size.

CONFIRMED real account field names (from live JSON, NOT the brief's
prose description — these differ from it):
  account_id, name, parent_id, parent_name, billing_street, billing_city,
  billing_state, billing_zip, care_type, status, phone, lifetime_revenue,
  outstanding_ar, chow_current_account, duplicate_of_account, note,
  created_by_candidate, updated_at

created_by_candidate (bool) — every seed record is false. Likely used
to isolate candidate-created data during grading. Any account THIS
pipeline creates should set it true.

STILL UNVERIFIED: "Needs Review" as a real status value — the brief
mentions it, but every sampled real account is "Active" or "Inactive"
only. Keeping it in STATUS_VALUES per the brief; flag if the API
rejects it.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # reads a .env file in the current directory, if present

CRM_BASE_URL = os.environ.get(
    "CRM_BASE_URL", "https://analyst-assessment-production.up.railway.app/api/v1"
)
CRM_TOKEN = os.environ.get("CRM_TOKEN", "bh_arzIeBHlp9LgqAU10PxIKw")

# Bellhaven's public site to scrape. Fill in after you locate it —
# it is a separate site from the CRM sandbox above.
BELLHAVEN_SITE_URL = os.environ.get("BELLHAVEN_SITE_URL", "")

# --- Endpoint paths, confirmed against /api/docs Swagger UI ---
ENDPOINTS = {
    "list_accounts": "/accounts",           # GET ?q, city, state, zip, street, parent_id, page, page_size
    "get_account": "/accounts/{id}",        # GET
    "create_account": "/accounts",          # POST
    "update_account": "/accounts/{id}",     # PATCH
}
DEFAULT_PAGE_SIZE = 50

# --- Matching thresholds (tune here for live-demo requests) ---
FUZZY_MATCH_CONFIDENT = 0.90   # >= this -> confident match, no proposal
FUZZY_MATCH_CANDIDATE = 0.60   # >= this -> "needs fix" candidate; below -> "no account yet"

# --- CRM field contract, per the brief ---
STATUS_VALUES = {"Active", "Inactive", "Needs Review"}

# Local state store (SQLite) path
STATE_DB_PATH = os.environ.get("STATE_DB_PATH", "state.db")
