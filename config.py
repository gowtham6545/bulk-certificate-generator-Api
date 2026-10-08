"""Settings, read from environment variables (with sensible defaults)."""
import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certificates.db")
STORAGE_DIR = Path(os.getenv("CERT_STORAGE_DIR", "./storage"))
MAX_RECIPIENTS_PER_JOB = int(os.getenv("MAX_RECIPIENTS_PER_JOB", "1000"))
