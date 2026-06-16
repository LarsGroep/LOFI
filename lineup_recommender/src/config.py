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