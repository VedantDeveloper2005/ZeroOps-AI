"""Test-process bootstrap settings required before backend modules import."""

import os


os.environ.setdefault("APP_ENV", "test")
