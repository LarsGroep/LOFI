from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

historical_path = ROOT / "data" / "processed" / "artist_historical_performance_scores.csv"
cooccurrence_path = ROOT / "data" / "processed" / "lofi_artist_cooccurrence.csv"

historical = pd.read_csv(historical_path)
cooccurrence = pd.read_csv(cooccurrence_path)

print("historical shape:", historical.shape)
print("cooccurrence shape:", cooccurrence.shape)

print("\nhistorical columns:")
print(historical.columns.tolist())

print("\ncooccurrence columns:")
print(cooccurrence.columns.tolist())

required_historical = {
    "artist_name",
    "historical_lofi_score",
    "confidence_score",
}

required_cooccurrence = {
    "artist_name_a",
    "artist_name_b",
    "cooccur_count",
}

print("\nmissing historical columns:")
print(required_historical - set(historical.columns))

print("\nmissing cooccurrence columns:")
print(required_cooccurrence - set(cooccurrence.columns))

cooccurrence["a_key"] = cooccurrence["artist_name_a"].astype(str).str.lower().str.strip()
cooccurrence["b_key"] = cooccurrence["artist_name_b"].astype(str).str.lower().str.strip()

self_pairs = cooccurrence[cooccurrence["a_key"] == cooccurrence["b_key"]]

print("\nself-pair count:", len(self_pairs))

print("\nmissing historical score:", historical["historical_lofi_score"].isna().sum())
print("missing confidence score:", historical["confidence_score"].isna().sum())
print("missing cooccur count:", cooccurrence["cooccur_count"].isna().sum())