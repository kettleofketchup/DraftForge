"""Pytest configuration for telemetry tests."""

import os
import sys
from pathlib import Path

# Add backend directory to Python path BEFORE any imports
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

# Set Django settings before importing django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
os.environ.setdefault("DISABLE_CACHE", "true")


def pytest_configure(config):
    """Setup Django before test collection."""
    import django

    django.setup()
