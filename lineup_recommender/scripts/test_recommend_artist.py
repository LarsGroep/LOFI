from pathlib import Path
import argparse
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.recommendation import recommend_artists_for_artist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artist_name", type=str)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-confidence", type=float, default=0)

    args = parser.parse_args()

    historical_path = ROOT / "data" / "processed" / "artist_historical_performance_scores.csv"
    cooccurrence_path = ROOT / "data" / "processed" / "lofi_artist_cooccurrence.csv"
    external_cooccurrence_path = ROOT / "data" / "processed" / "external_artist_cooccurrence.csv"

    historical_scores = pd.read_csv(historical_path)
    cooccurrence = pd.read_csv(cooccurrence_path)

    external_cooccurrence = None

    if external_cooccurrence_path.exists():
        external_cooccurrence = pd.read_csv(external_cooccurrence_path)
        print(f"Loaded external co-occurrence: {external_cooccurrence.shape}")
    else:
        print("No external co-occurrence file found. Running LOFI-only recommender.")

    recommendations = recommend_artists_for_artist(
        selected_artist_name=args.artist_name,
        historical_scores_df=historical_scores,
        cooccurrence_df=cooccurrence,
        external_cooccurrence_df=external_cooccurrence,
        min_confidence=args.min_confidence,
        top_n=args.top_n,
    )

    if recommendations.empty:
        print(f"No recommendations found for: {args.artist_name}")
        print("\nPossible causes:")
        print("- Artist name does not exactly match after normalization.")
        print("- Artist has no co-occurrence pairs.")
        print("- min-confidence is too high.")
        return
    
    if len(recommendations) < args.top_n:
        print(
        f"Only {len(recommendations)} recommendation(s) found. "
        "This usually means the selected artist has limited historical LOFI co-occurrence data."
    )


    print(f"\nTop recommendations for: {args.artist_name}\n")

    
    display_columns = [
        "candidate_artist",
        "cooccur_count",
        "historical_lofi_score",
        "has_historical_lofi_score",
        "confidence_score",
        "cooccurrence_strength",
        "external_cooccur_count",
        "external_scene_score",
        "external_scene_bonus",
        "has_external_scene_evidence",
        "recommendation_score",
    ]

    existing_display_columns = [
        column for column in display_columns if column in recommendations.columns
    ]

    print(recommendations[existing_display_columns].to_string(index=False))

    print("\nReasons:\n")

    for index, row in recommendations.iterrows():
        rank = index + 1
        print(f"{rank}. {row['candidate_artist']}")
        print(f"   {row['recommendation_reason']}\n")


if __name__ == "__main__":
    main()