"""Root conftest — runs before any test module or tests/conftest.py is imported.

The app's Pydantic Settings read these from the environment at import time, and
TOKEN_ENCRYPTION_KEY is *required* (the app refuses to start without it). We set
throwaway test values here, before anything under `app` is imported, so the test
suite is fully self-contained: it never reads the real .env and never touches a
real database or external service.
"""

import os

from cryptography.fernet import Fernet

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
