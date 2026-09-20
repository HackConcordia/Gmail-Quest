"""Central configuration: paths, org identity, model/LLM settings.

Everything here is read from the environment (see .env.example). Nothing raises at
import time so tests and tooling can import this module without a full .env — code
that actually needs a value (e.g. ORG_EMAIL for tagging inbound/outbound mail) checks
for it explicitly at the point of use.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("GMAILQUEST_DATA_DIR", PROJECT_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "gmailquest.sqlite"
CREDENTIALS_PATH = Path(os.getenv("GMAILQUEST_CREDENTIALS_PATH", DATA_DIR / "credentials.json"))
TOKEN_PATH = Path(os.getenv("GMAILQUEST_TOKEN_PATH", DATA_DIR / "token.json"))

ORG_EMAIL = os.getenv("GMAILQUEST_ORG_EMAIL", "").strip().lower()

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

EMBEDDING_MODEL = os.getenv("GMAILQUEST_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
ANTHROPIC_MODEL = os.getenv("GMAILQUEST_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
