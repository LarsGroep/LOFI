"""Shared Supabase client for all live detection scrapers."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Walk up until we find .env (handles running from any sub-folder)
_here = Path(__file__).resolve()
for _parent in _here.parents:
    _env = _parent / ".env"
    if _env.exists():
        load_dotenv(_env)
        break

def get_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
