"""
One-time migration: create tinder.xgboost_predictions table in Supabase.

Run once:
    python create_xgboost_table.py
"""
from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

DDL = """
CREATE TABLE IF NOT EXISTS tinder.xgboost_predictions (
    artist_id             uuid PRIMARY KEY REFERENCES tinder.artists(id) ON DELETE CASCADE,
    artist_name           text NOT NULL,
    predicted_growth_90d  numeric,
    missing_pct           numeric,
    available_features    int,
    total_features        int,
    prediction_date       date,
    model_version         text,
    predicted_at          timestamptz DEFAULT now()
);
"""

print("Creating tinder.xgboost_predictions table...")
try:
    result = sb.schema("tinder").rpc("exec_sql", {"sql": DDL}).execute()
    print("Done via RPC exec_sql.")
except Exception as e1:
    print(f"RPC exec_sql failed ({e1}), trying postgres_meta approach...")
    # Supabase exposes a REST endpoint for running SQL in the Management API,
    # but that requires the service_role key and a direct pg connection.
    # Fall back to using the Supabase REST query builder to check if the table exists
    # by attempting a select, and report the status.
    try:
        check = sb.schema("tinder").table("xgboost_predictions").select("artist_id").limit(1).execute()
        print("Table already exists (select succeeded). Nothing to do.")
    except Exception as e2:
        print(
            "\nCould not create or verify the table automatically.\n"
            "Please run the following SQL in the Supabase SQL editor:\n"
        )
        print(DDL)
        print(f"\nOriginal errors:\n  RPC: {e1}\n  Select: {e2}")
        sys.exit(1)
