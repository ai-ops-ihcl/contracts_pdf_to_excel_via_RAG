#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick deployment test script
Verifies that all imports work and configurations load correctly.
Run this BEFORE building Docker to catch issues early.

Usage:
    python test_deployment.py
"""

import sys
import os
from pathlib import Path

# Fix encoding for Windows console
if os.name == 'nt':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=" * 60)
print("IHCL Contract Pipeline - Deployment Test")
print("=" * 60)

# Test 1: Python version
print("\n[1/7] Checking Python version...")
if sys.version_info < (3, 11):
    print(f"   [FAIL] Python 3.11+ required, found {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)
print(f"   [OK] Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# Test 2: Import app.config
print("\n[2/7] Importing app.config...")
try:
    import app.config as config
    print(f"   [OK] Config loaded")
    print(f"      - QDRANT_URL: {config.QDRANT_URL}")
    print(f"      - INPUT_PDF_DIR: {config.INPUT_PDF_DIR}")
    print(f"      - OUTPUT_EXCEL_DIR: {config.OUTPUT_EXCEL_DIR}")
except Exception as e:
    print(f"   [FAIL] Failed to import config: {e}")
    sys.exit(1)

# Test 3: Import utilities
print("\n[3/7] Importing utilities...")
try:
    from app.utils.logger import get_logger, PipelineRunLogger
    from app.utils.tracker import FileTracker
    print("   [OK] Utilities imported")
except Exception as e:
    print(f"   [FAIL] Failed to import utilities: {e}")
    sys.exit(1)

# Test 4: Import orchestrator
print("\n[4/7] Importing orchestrator...")
try:
    from app.pipeline.orchestrator import PipelineOrchestrator
    print("   [OK] Orchestrator imported")
except Exception as e:
    print(f"   [FAIL] Failed to import orchestrator: {e}")
    sys.exit(1)

# Test 5: Import FastAPI app
print("\n[5/7] Importing FastAPI app...")
try:
    from app.main import app
    print("   [OK] FastAPI app imported")
    print(f"      - Title: {app.title}")
    print(f"      - Version: {app.version}")
except Exception as e:
    print(f"   [FAIL] Failed to import app: {e}")
    sys.exit(1)

# Test 6: Check directory structure
print("\n[6/7] Checking directories...")
required_dirs = [
    config.INPUT_PDF_DIR,
    config.PROCESSED_PDF_DIR,
    config.MARKDOWN_DIR,
    config.OUTPUT_EXCEL_DIR,
    config.LOG_DIR,
]
for dir_path in required_dirs:
    if dir_path.exists():
        print(f"   [OK] {dir_path.name}")
    else:
        print(f"   [WARN]  {dir_path.name} (will be created)")

# Test 7: Test orchestrator instantiation
print("\n[7/7] Testing orchestrator instantiation...")
try:
    orchestrator = PipelineOrchestrator(config)
    print("   [OK] Orchestrator created successfully")
except Exception as e:
    print(f"   [FAIL] Failed to create orchestrator: {e}")
    sys.exit(1)

# Summary
print("\n" + "=" * 60)
print("[OK] ALL TESTS PASSED - Ready for deployment!")
print("=" * 60)
print("\nNext steps:")
print("  1. Ensure .env file is configured")
print("  2. Run: docker-compose up -d")
print("  3. Check health: curl http://localhost:8000/health")
print("  4. View docs: http://localhost:8000/docs")
print()
