from pathlib import Path

# config.py lives in:
# lineup_recommender/src/config.py

SRC_DIR = Path(__file__).resolve().parent
FEATURE_ROOT = SRC_DIR.parent  # lineup_recommender

DATA_DIR = FEATURE_ROOT / "data"
RAW_LOFI_DIR = DATA_DIR / "lofi"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

ARTIST_EVENTS_PATH = RAW_LOFI_DIR / "artist_events_clean.csv"
ARTISTS_PATH = RAW_LOFI_DIR / "artists_clean.csv"
EVENTS_PATH = RAW_LOFI_DIR / "events_clean.csv"

HISTORICAL_SCORES_PATH = PROCESSED_DIR / "artist_historical_performance_scores.csv"

EXTERNAL_DIR = DATA_DIR / "external"

PARTYFLOCK_EVENTS_PATH = EXTERNAL_DIR / "partyflock_events.csv"
PARTYFLOCK_LINEUPS_PATH = EXTERNAL_DIR / "partyflock_lineups.csv"
RA_EVENTS_PATH = EXTERNAL_DIR / "ra_events.csv"
RA_LINEUPS_PATH = EXTERNAL_DIR / "ra_lineups.csv"

EXTERNAL_EVENT_ARTISTS_PATH = INTERIM_DIR / "external_event_artists.csv"
EXTERNAL_COOCCURRENCE_PATH = PROCESSED_DIR / "external_artist_cooccurrence.csv"