from pathlib import Path
import sys

CURRENT_FILE = Path(__file__).resolve()
FEATURE_ROOT = CURRENT_FILE.parents[1]
SRC_DIR = FEATURE_ROOT / "src"

sys.path.append(str(SRC_DIR))

from load_data import load_lofi_data
from clean_data import clean_events
from lineup_parsing import build_parsed_event_lineups
from config import INTERIM_DIR


def main():
    print("Loading LOFI data...")
    artist_events_df, artists_df, events_df = load_lofi_data()

    print("Cleaning events...")
    events = clean_events(events_df)

    print("Parsing event lineups...")
    parsed_lineups = build_parsed_event_lineups(events)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    output_path = INTERIM_DIR / "parsed_event_lineups.csv"
    parsed_lineups.to_csv(output_path, index=False)

    print(f"Saved parsed event lineups to: {output_path}")
    print(f"Parsed rows: {len(parsed_lineups)}")
    print(parsed_lineups.head(30))


if __name__ == "__main__":
    main()