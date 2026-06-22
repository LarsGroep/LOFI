from pathlib import Path
import sys

# Make sure Python can import from lineup_recommender/src
CURRENT_FILE = Path(__file__).resolve()
FEATURE_ROOT = CURRENT_FILE.parents[1]   # lineup_recommender/
SRC_DIR = FEATURE_ROOT / "src"

sys.path.append(str(SRC_DIR))

from load_data import load_lofi_data
from clean_data import clean_artist_events
from performance_scoring import build_historical_performance_scores
from export import save_processed
from config import HISTORICAL_SCORES_PATH


def main():
    print("Loading LOFI data...")
    artist_events_df, artists_df, events_df = load_lofi_data()

    print("Cleaning artist-event data...")
    artist_events = clean_artist_events(artist_events_df)

    print("Building historical performance scores...")
    scores = build_historical_performance_scores(artist_events)

    print("Saving processed output...")
    save_processed(scores, HISTORICAL_SCORES_PATH)

    print(f"Saved historical performance scores to: {HISTORICAL_SCORES_PATH}")
    print("\nTop 20 artists by historical LOFI score:")
    print(
        scores[
            [
                "artist_id",
                "artist_name",
                "event_count",
                "historical_lofi_score",
                "confidence_score",
                "score_explanation",
            ]
        ].head(20)
    )


if __name__ == "__main__":
    main()