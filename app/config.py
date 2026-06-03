"""
IHCL Contract Pipeline — Central Configuration
================================================
Single source of truth for all paths, settings, and connections.
All other modules import from here — NEVER hardcode paths elsewhere.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================
# Base Paths
# ============================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# Data Directories
# ============================================
INPUT_PDF_DIR     = Path(os.getenv("INPUT_PDF_DIR", BASE_DIR / "data" / "input_pdfs"))
PROCESSED_PDF_DIR = Path(os.getenv("PROCESSED_PDF_DIR", BASE_DIR / "data" / "processed_pdfs"))
MARKDOWN_DIR      = Path(os.getenv("MARKDOWN_DIR", BASE_DIR / "data" / "markdowns"))
OUTPUT_EXCEL_DIR  = Path(os.getenv("OUTPUT_EXCEL_DIR", BASE_DIR / "data" / "output_excel"))
LOG_DIR           = Path(os.getenv("LOG_DIR", BASE_DIR / "data" / "logs"))

# Create directories if they don't exist
for d in [INPUT_PDF_DIR, PROCESSED_PDF_DIR, MARKDOWN_DIR, OUTPUT_EXCEL_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================
# Qdrant Settings
# ============================================
QDRANT_HOST       = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT       = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hotel_contracts")
QDRANT_URL        = f"http://{QDRANT_HOST}:{QDRANT_PORT}"

# ============================================
# Pipeline Settings
# ============================================
FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", 80))
MAX_WORKERS           = int(os.getenv("MAX_WORKERS", 4))

# ============================================
# Tracker File (for incremental processing)
# ============================================
PROCESSED_LOG_FILE = LOG_DIR / "processed_files.json"

# ============================================
# App Settings
# ============================================
APP_NAME = os.getenv("APP_NAME", "ihcl-contract-pipeline")
DEBUG    = os.getenv("DEBUG", "false").lower() == "true"