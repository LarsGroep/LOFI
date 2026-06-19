"""
Train XGBoost growth-prediction model on all artist timeseries data.

Adapted from future_predictor_v1.ipynb to work with the tinder Supabase schema.

Features: per-platform indexed growth values + 30/90/180d pct changes
          + growth acceleration from ml_features in artist_chartmetric.

Target: Spotify listeners growth over the next ~90 days (inferred from
        the last 90 days of the held-out portion of the timeseries).

Saves:
  - ml/models/growth_predictor.json  (XGBoost model, loadable at inference time)
  - ml/models/predictions.csv        (latest prediction per artist)

Run:
    python ml/train_growth_model.py [--output-dir ml/models]

Requirements (add to requirements.txt if missing):
    xgboost scikit-learn
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import pandas as pd
import numpy as np

try:
    from xgboost import XGBRegressor
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import mean_absolute_error, r2_score
    from scipy.stats import spearmanr
    _HAS_SKL = True
except ImportError:
    _HAS_SKL = False

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

METRICS = [
    ("spotify",          "listeners"),
    ("spotify",          "followers"),
    ("instagram",        "followers"),
    ("tiktok",           "followers"),
    ("youtube_channel",  "subscribers"),
    ("youtube_channel",  "views"),
    ("soundcloud",       "followers"),
    ("cpp",              "score"),
]
TARGET_SOURCE  = "spotify"
TARGET_METRIC  = "listeners"
TARGET_DAYS    = 90   # predict growth over next 90 days


def _pct(a: float, b: float) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b - a) / abs(a) * 100.0


def build_features(ts: dict, ml: dict) -> dict:
    """
    Build a flat feature dict for one artist from cm_timeseries + ml_features.
    Returns {} if insufficient data.
    """
    feats: dict = {}

    # From ml_features (pre-computed, reliable)
    for key in [
        "sp_listeners_30d_pct", "sp_listeners_90d_pct", "sp_listeners_180d_pct",
        "sp_listeners_accel", "cross_platform_momentum_30d", "platforms_growing_30d",
        "cpp_score_30d_pct", "cpp_score_90d_pct", "cpp_score_current",
        "sp_listeners_to_followers",
    ]:
        feats[key] = ml.get(key)

    # From timeseries: compute indexed growth per platform
    for source, metric in METRICS:
        pts = (ts.get(source) or {}).get(metric) or []
        vals = [p["value"] for p in pts if p.get("value") is not None]
        if not vals:
            continue
        base = vals[0] if vals[0] else None
        latest = vals[-1]

        key = f"{source}_{metric}"
        feats[f"{key}_latest"]  = latest
        feats[f"{key}_indexed"] = (latest / base * 100.0) if base else None

        n = len(vals)
        feats[f"{key}_30d_pct"]  = _pct(vals[max(0, n - 31)], latest) if n > 30 else None
        feats[f"{key}_90d_pct"]  = _pct(vals[max(0, n - 91)], latest) if n > 90 else None
        feats[f"{key}_180d_pct"] = _pct(vals[max(0, n - 181)], latest) if n > 180 else None

    return feats


def compute_target(ts: dict) -> float | None:
    """
    Use the 90-day forward growth of Spotify listeners as the training target.
    Since we only have historical data, we use the most recent 90-day window
    as a proxy for 'recent growth momentum' (same approach as notebook).
    """
    pts = (ts.get(TARGET_SOURCE) or {}).get(TARGET_METRIC) or []
    vals = [p["value"] for p in pts if p.get("value") is not None]
    if len(vals) < TARGET_DAYS + 10:
        return None
    n = len(vals)
    before = vals[n - TARGET_DAYS - 1]
    after  = vals[-1]
    return _pct(before, after)


def _paginate(table, select: str, page_size: int = 100) -> list[dict]:
    """Fetch all rows from a Supabase table in pages to avoid statement timeout."""
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            sb.schema("tinder").table(table)
            .select(select)
            .range(offset, offset + page_size - 1)
            .execute().data or []
        )
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def load_data() -> tuple[pd.DataFrame, list[str]]:
    """Fetch all artists with timeseries + ml_features. Returns (df, feature_cols)."""
    print("Loading data from Supabase (paginated)...")

    # Paginate the heavy JSONB query to avoid statement timeout
    all_cm = _paginate("artist_chartmetric", "artist_id, cm_timeseries, ml_features", page_size=50)
    rows = [r for r in all_cm if r.get("cm_timeseries")]
    print(f"  Fetched {len(rows)} rows with timeseries data")

    # Also need artist names for group splitting
    name_rows = _paginate("artists", "id, name", page_size=500)
    id_to_name = {r["id"]: r["name"] for r in name_rows}

    records = []
    for r in rows:
        ts = r.get("cm_timeseries") or {}
        ml = r.get("ml_features") or {}
        aid = r["artist_id"]

        feats = build_features(ts, ml)
        target = compute_target(ts)
        if target is None or not feats or all(v is None for v in feats.values()):
            continue
        if not math.isfinite(target):
            continue

        feats["_artist_id"] = aid
        feats["_artist_name"] = id_to_name.get(aid, aid)
        feats["_target"] = target
        records.append(feats)

    if not records:
        print("No usable training rows found.")
        return pd.DataFrame(), []

    df = pd.DataFrame(records)
    feature_cols = [c for c in df.columns if not c.startswith("_")]

    # Fill NaN with 0 (missing = no signal)
    df[feature_cols] = df[feature_cols].fillna(0)

    # Clip extreme target outliers at 98th percentile
    p98 = df["_target"].quantile(0.98)
    p02 = df["_target"].quantile(0.02)
    df = df[(df["_target"] <= p98) & (df["_target"] >= p02)].copy()

    print(f"Training rows: {len(df)}  features: {len(feature_cols)}")
    return df, feature_cols


def train(output_dir: Path) -> None:
    if not _HAS_XGB:
        print("xgboost not installed — run: pip install xgboost")
        sys.exit(1)
    if not _HAS_SKL:
        print("scikit-learn or scipy not installed — run: pip install scikit-learn scipy")
        sys.exit(1)

    df, feature_cols = load_data()
    if df.empty:
        sys.exit(1)

    X = df[feature_cols].values
    y = df["_target"].values
    groups = df["_artist_name"].values

    # Group-aware train/test split (no artist leaks across splits)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups))

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    model = XGBRegressor(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    r2  = r2_score(y_test, preds)
    sp  = spearmanr(y_test, preds).correlation
    dir_acc = float(np.mean(np.sign(preds) == np.sign(y_test)))

    print(f"\nTest set — MAE: {mae:.1f}%  R²: {r2:.3f}  Spearman: {sp:.3f}  Dir: {dir_acc:.2%}")

    # Feature importance
    imp = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1])
    print("\nTop-10 features by gain:")
    for name, score in imp[:10]:
        print(f"  {name:<40} {score:.4f}")

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "growth_predictor.json"
    model.save_model(str(model_path))
    print(f"\nModel saved to {model_path}")

    # Predictions for all artists (latest snapshot)
    X_all = df[feature_cols].values
    df["predicted_growth_90d"] = model.predict(X_all)
    pred_df = df[["_artist_name", "_artist_id", "_target", "predicted_growth_90d"]].copy()
    pred_df.columns = ["artist_name", "artist_id", "actual_growth_90d", "predicted_growth_90d"]
    pred_df = pred_df.sort_values("predicted_growth_90d", ascending=False).reset_index(drop=True)

    pred_path = output_dir / "predictions.csv"
    pred_df.to_csv(pred_path, index=False)
    print(f"Predictions saved to {pred_path}")

    # Save feature column order, importances, and training stats for inference
    feat_imp = {col: float(v) for col, v in zip(feature_cols, model.feature_importances_)}
    meta_path = output_dir / "model_meta.json"
    with open(meta_path, "w") as f:
        json.dump({
            "feature_cols": feature_cols,
            "target": "sp_listeners_90d_pct",
            "feature_importances": feat_imp,
            "n_training_artists": len(df),
            "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "test_mae": round(float(mae), 1),
            "test_r2": round(float(r2), 3),
            "test_spearman": round(float(sp), 3),
            "test_dir_acc": round(float(dir_acc), 3),
        }, f, indent=2)
    print(f"Metadata saved to {meta_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="ml/models")
    args = parser.parse_args()
    train(Path(args.output_dir))


if __name__ == "__main__":
    main()
