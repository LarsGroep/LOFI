from pathlib import Path
import sys
import pandas as pd

CURRENT_FILE = Path(__file__).resolve()
FEATURE_ROOT = CURRENT_FILE.parents[1]
SRC_DIR = FEATURE_ROOT / "src"

sys.path.append(str(SRC_DIR))

from load_data import load_lofi_data
from clean_data import clean_artist_events, clean_events
from cooccurrence import build_lofi_cooccurrence
from config import INTERIM_DIR, PROCESSED_DIR


def main():
    print("Loading LOFI data...")
    artist_events_df, artists_df, events_df = load_lofi_data()

    print("Cleaning LOFI data...")
    artist_events = clean_artist_events(artist_events_df)
    events = clean_events(events_df)

    parsed_path = INTERIM_DIR / "parsed_event_lineups.csv"

    if not parsed_path.exists():
        raise FileNotFoundError(
            f"Missing parsed lineup table: {parsed_path}. "
            "Run scripts/build_lineup_tables.py first."
        )

    print("Loading parsed event lineups...")
    parsed_lineups = pd.read_csv(parsed_path)

    if "event_date" in parsed_lineups.columns:
        parsed_lineups["event_date"] = pd.to_datetime(
            parsed_lineups["event_date"],
            errors="coerce",
        )

    print("Building LOFI co-occurrence table...")
    cooccurrence, parsed_with_ids, event_artists = build_lofi_cooccurrence(
        parsed_lineups=parsed_lineups,
        artist_events=artist_events,
        events=events,
    )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    parsed_with_ids_path = INTERIM_DIR / "parsed_event_lineups_with_artist_ids.csv"
    event_artists_path = INTERIM_DIR / "event_artists.csv"
    cooccurrence_path = PROCESSED_DIR / "lofi_artist_cooccurrence.csv"

    parsed_with_ids.to_csv(parsed_with_ids_path, index=False)
    event_artists.to_csv(event_artists_path, index=False)
    cooccurrence.to_csv(cooccurrence_path, index=False)

    print(f"Saved parsed lineups with IDs to: {parsed_with_ids_path}")
    print(f"Saved event-artists table to: {event_artists_path}")
    print(f"Saved LOFI co-occurrence table to: {cooccurrence_path}")

    print("\nSummary:")
    print(f"Parsed lineup rows: {len(parsed_lineups)}")
    print(f"Matched rows with artist IDs: {parsed_with_ids['artist_id'].notna().sum()}")
    print(f"Unmatched rows: {parsed_with_ids['artist_id'].isna().sum()}")
    print(f"Unique event-artist rows: {len(event_artists)}")
    print(f"Co-occurrence pairs: {len(cooccurrence)}")

    if len(cooccurrence) > 0:
        print("\nTop 20 co-occurring artist pairs:")
        print(
            cooccurrence[
                [
                    "artist_name_a",
                    "artist_name_b",
                    "cooccur_count",
                    "avg_event_result_together",
                    "avg_occupancy_rate_together",
                    "last_played_together",
                ]
            ].head(20)
        )
    else:
        print("\nNo co-occurrence pairs were created.")
        print("Likely reason: parsed lineup artist names did not match artist_events artist names.")


if __name__ == "__main__":
    main()