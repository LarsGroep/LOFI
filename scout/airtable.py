"""
Read-only Airtable access for LOFI booking history (Phase 3).

This is the "second world": Lofi's own bookings — gages, events, outcomes —
which ground the chat's verdicts and gage benchmarking. Gage data into the LLM
was approved by Lofi (option 1).

Status: INTERFACE READY, queries pending the real schema. Until the table/field
names are configured the loaders return [] so the chat degrades gracefully and
never invents booking or gage data. `httpx` is imported lazily so importing this
module never hard-fails.

Configure via env once the schema is known:
    AIRTABLE_TOKEN, AIRTABLE_BASE_ID,
    AIRTABLE_BOOKINGS_TABLE, and the field-name mapping below.
"""
from __future__ import annotations

import os

_API_ROOT = "https://api.airtable.com/v0"


def _configured() -> bool:
    return bool(os.environ.get("AIRTABLE_TOKEN")
               and os.environ.get("AIRTABLE_BASE_ID")
               and os.environ.get("AIRTABLE_BOOKINGS_TABLE"))


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _fetch_records(table: str) -> list[dict]:
    """Paginated read of an Airtable table. Returns raw {id, fields} records."""
    import httpx  # lazy — only needed when actually configured

    token = os.environ["AIRTABLE_TOKEN"]
    base = os.environ["AIRTABLE_BASE_ID"]
    url = f"{_API_ROOT}/{base}/{table}"
    headers = {"Authorization": f"Bearer {token}"}
    out, offset = [], None
    with httpx.Client(timeout=30.0) as client:
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            r = client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
    return out


# ── public loaders (used by the chat) ────────────────────────────────────────
# These return [] until the schema mapping is finalised — see the TODO below.

def load_booking_history(artist_name: str) -> list[dict]:
    """Past LOFI bookings of THIS artist (gage, event, date, outcome)."""
    if not _configured():
        return []
    # TODO(schema): fetch _fetch_records(AIRTABLE_BOOKINGS_TABLE), match on the
    # artist-name field (via _norm), map gage/event/date/outcome fields.
    return []


def load_comparables(artist_name: str, profile: dict, limit: int = 5) -> list[dict]:
    """Similar past bookings (genre/popularity tier) for gage benchmarking."""
    if not _configured():
        return []
    # TODO(schema): rank past bookings by genre + popularity similarity to
    # `profile`, return the top `limit` with their gages.
    return []
