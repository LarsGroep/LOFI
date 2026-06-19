from pathlib import Path
import sys

import pandas as pd

CURRENT_FILE = Path(__file__).resolve()
FEATURE_ROOT = CURRENT_FILE.parents[1]
SRC_DIR = FEATURE_ROOT / "src"

sys.path.append(str(SRC_DIR))

from config import (
    EXTERNAL_EVENT_ARTISTS_PATH,
    EXTERNAL_COOCCURRENCE_PATH,
    PROCESSED_DIR,
)

from external_lineups import build_external_cooccurrence


def main():
    if not EXTERNAL_EVENT_ARTISTS_PATH.exists():
        raise FileNotFoundError(
            f"Missing external event-artists table: {EXTERNAL_EVENT_ARTISTS_PATH}. "
            "Run scripts/build_external_lineups.py first."
        )

    print(f"Loading external event-artists from: {EXTERNAL_EVENT_ARTISTS_PATH}")
    external_event_artists = pd.read_csv(EXTERNAL_EVENT_ARTISTS_PATH)

    if "event_date" in external_event_artists.columns:
        external_event_artists["event_date"] = pd.to_datetime(
            external_event_artists["event_date"],
            errors="coerce",
            utc=True,
        )

    # Convert to timezone-naive UTC timestamps.
    # This prevents pandas groupby min/max from comparing mixed timezone objects.
    external_event_artists["event_date"] = (
        external_event_artists["event_date"]
        .dt.tz_convert(None)
    )

    print("Building external artist co-occurrence...")
    external_cooccurrence = build_external_cooccurrence(external_event_artists)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    external_cooccurrence.to_csv(EXTERNAL_COOCCURRENCE_PATH, index=False)

    print(f"Saved external co-occurrence to: {EXTERNAL_COOCCURRENCE_PATH}")
    print(f"Rows: {len(external_cooccurrence)}")

    if not external_cooccurrence.empty:
        print("\nTop 30 external co-occurring artist pairs:")
        print(
            external_cooccurrence[
                [
                    "artist_name_a",
                    "artist_name_b",
                    "external_cooccur_count",
                    "sources_together",
                    "cities_together",
                    "last_seen_together",
                ]
            ].head(30)
        )


if __name__ == "__main__":
    main()