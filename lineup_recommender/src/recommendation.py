from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd


def normalize_artist_name(name: str) -> str:
    """
    Normalize artist names for matching only.

    Important:
    This is not used for display, because artist spelling can be intentional.
    """
    if pd.isna(name):
        return ""

    name = str(name)
    name = unicodedata.normalize("NFKC", name)
    name = name.strip().lower()
    name = re.sub(r"\s+", " ", name)

    return name


def max_normalize_100(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0)
    max_value = values.max()

    if max_value <= 0:
        return pd.Series(0, index=series.index)

    return 100 * values / max_value


def minmax_normalize_100(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    min_value = values.min()
    max_value = values.max()

    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        return pd.Series(50, index=series.index)

    return 100 * (values - min_value) / (max_value - min_value)


def build_candidates_for_artist(
    selected_artist_name: str,
    cooccurrence_df: pd.DataFrame,
) -> pd.DataFrame:
    required_columns = {
        "artist_name_a",
        "artist_name_b",
        "cooccur_count",
    }

    missing_columns = required_columns - set(cooccurrence_df.columns)

    if missing_columns:
        raise ValueError(f"cooccurrence_df is missing columns: {missing_columns}")

    selected_key = normalize_artist_name(selected_artist_name)

    df = cooccurrence_df.copy()
    df["artist_key_a"] = df["artist_name_a"].apply(normalize_artist_name)
    df["artist_key_b"] = df["artist_name_b"].apply(normalize_artist_name)

    mask = (df["artist_key_a"] == selected_key) | (df["artist_key_b"] == selected_key)
    pairs = df[mask].copy()

    if pairs.empty:
        return pd.DataFrame()

    pairs["candidate_artist"] = np.where(
        pairs["artist_key_a"] == selected_key,
        pairs["artist_name_b"],
        pairs["artist_name_a"],
    )

    pairs["candidate_key"] = np.where(
        pairs["artist_key_a"] == selected_key,
        pairs["artist_key_b"],
        pairs["artist_key_a"],
    )

    aggregation = {
        "candidate_artist": "first",
        "cooccur_count": "sum",
    }

    optional_mean_columns = [
        "avg_total_visitors_together",
        "avg_actual_tickets_together",
        "avg_ticketing_revenue_together",
        "avg_bar_revenue_together",
        "avg_total_revenue_together",
        "avg_total_cost_together",
        "avg_event_result_together",
        "avg_occupancy_rate_together",
    ]

    for column in optional_mean_columns:
        if column in pairs.columns:
            aggregation[column] = "mean"

    optional_date_columns = {
        "first_played_together": "min",
        "last_played_together": "max",
    }

    for column, method in optional_date_columns.items():
        if column in pairs.columns:
            aggregation[column] = method

    optional_text_columns = {
        "events_together": "first",
    }

    for column, method in optional_text_columns.items():
        if column in pairs.columns:
            aggregation[column] = method

    candidates = (
        pairs.groupby("candidate_key", as_index=False)
        .agg(aggregation)
        .sort_values("cooccur_count", ascending=False)
    )

    return candidates


def attach_historical_scores(
    candidates: pd.DataFrame,
    historical_scores_df: pd.DataFrame,
) -> pd.DataFrame:
    required_columns = {
        "artist_name",
        "historical_lofi_score",
        "confidence_score",
    }

    missing_columns = required_columns - set(historical_scores_df.columns)

    if missing_columns:
        raise ValueError(f"historical_scores_df is missing columns: {missing_columns}")

    historical = historical_scores_df.copy()
    historical["artist_key"] = historical["artist_name"].apply(normalize_artist_name)

    # If duplicate artist names exist after normalization, keep the most reliable row.
    historical = (
        historical.sort_values(
            ["confidence_score", "historical_lofi_score"],
            ascending=[False, False],
            na_position="last",
        )
        .groupby("artist_key", as_index=False)
        .first()
    )

    columns_to_keep = [
        "artist_key",
        "historical_lofi_score",
        "confidence_score",
    ]

    optional_columns = [
        "event_count",
        "first_event_date",
        "last_event_date",
        "genres",
        "reliability_score",
        "data_completeness",
        "recency_confidence",
        "score_explanation",
    ]

    for column in optional_columns:
        if column in historical.columns:
            columns_to_keep.append(column)

    enriched = candidates.merge(
        historical[columns_to_keep],
        left_on="candidate_key",
        right_on="artist_key",
        how="left",
    )

    return enriched


def make_recommendation_reason(row: pd.Series) -> str:
    reasons = []

    cooccur_count = row.get("cooccur_count", np.nan)

    if pd.notna(cooccur_count):
        reasons.append(
            f"has {int(cooccur_count)} historical LOFI line-up connection(s)"
        )

    historical_score = row.get("historical_lofi_score", np.nan)

    if pd.notna(historical_score):
        reasons.append(f"has a historical LOFI score of {historical_score:.1f}")
    else:
        reasons.append("has no available historical LOFI score yet")

    confidence_score = row.get("confidence_score", np.nan)

    if pd.notna(confidence_score):
        reasons.append(f"has an evidence confidence score of {confidence_score:.1f}")

    event_count = row.get("event_count", np.nan)

    if pd.notna(event_count):
        reasons.append(f"is based on {int(event_count)} historical LOFI event(s)")

    occupancy = row.get("avg_occupancy_rate_together", np.nan)

    if pd.notna(occupancy):
        reasons.append(
            f"shared events had average occupancy rate of {occupancy:.1f}"
        )

    return "Recommended because the artist " + ", ".join(reasons) + "."


def recommend_artists_for_artist(
    selected_artist_name: str,
    historical_scores_df: pd.DataFrame,
    cooccurrence_df: pd.DataFrame,
    min_confidence: float = 0,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Deterministic LOFI-only artist recommender.

    This version uses:
    - LOFI artist co-occurrence
    - historical LOFI score
    - confidence score

    It does not use:
    - scraper data
    - Chartmetric
    - LLM reasoning

    Important:
    Missing historical_lofi_score is not hidden. It is exposed in the output and
    receives a neutral placeholder for scoring, with a small penalty.
    """
    candidates = build_candidates_for_artist(
        selected_artist_name=selected_artist_name,
        cooccurrence_df=cooccurrence_df,
    )

    if candidates.empty:
        return pd.DataFrame()

    candidates = attach_historical_scores(
        candidates=candidates,
        historical_scores_df=historical_scores_df,
    )

    candidates["has_historical_lofi_score"] = candidates[
        "historical_lofi_score"
    ].notna()

    # Neutral placeholder, not fake evidence.
    # The missingness flag and score penalty keep this visible.
    candidates["historical_lofi_score_for_scoring"] = pd.to_numeric(
        candidates["historical_lofi_score"],
        errors="coerce",
    ).fillna(50)

    candidates["confidence_score_for_scoring"] = pd.to_numeric(
        candidates["confidence_score"],
        errors="coerce",
    ).fillna(0)

    candidates = candidates[
        candidates["confidence_score_for_scoring"] >= min_confidence
    ].copy()

    if candidates.empty:
        return pd.DataFrame()

    candidates["cooccur_count_norm"] = max_normalize_100(candidates["cooccur_count"])

    candidates["cooccurrence_strength"] = candidates["cooccur_count_norm"]

    if "avg_occupancy_rate_together" in candidates.columns:
        candidates["occupancy_norm"] = minmax_normalize_100(
            candidates["avg_occupancy_rate_together"]
        )

        candidates["cooccurrence_strength"] = (
            0.80 * candidates["cooccur_count_norm"]
            + 0.20 * candidates["occupancy_norm"]
        )

    candidates["recommendation_score_raw"] = (
        0.50 * candidates["cooccurrence_strength"]
        + 0.35 * candidates["historical_lofi_score_for_scoring"]
        + 0.15 * candidates["confidence_score_for_scoring"]
    )

    # Small penalty if the historical score is missing.
    # This avoids pretending missing evidence is equal to real evidence.
    candidates["missing_score_penalty"] = np.where(
        candidates["has_historical_lofi_score"],
        0,
        7.5,
    )

    candidates["recommendation_score"] = (
        candidates["recommendation_score_raw"] - candidates["missing_score_penalty"]
    ).clip(lower=0)

    candidates["selected_artist"] = selected_artist_name
    candidates["recommendation_reason"] = candidates.apply(
        make_recommendation_reason,
        axis=1,
    )

    output_columns = [
        "selected_artist",
        "candidate_artist",
        "cooccur_count",
        "historical_lofi_score",
        "has_historical_lofi_score",
        "confidence_score",
    ]

    optional_columns = [
        "event_count",
        "genres",
        "first_event_date",
        "last_event_date",
        "avg_total_visitors_together",
        "avg_actual_tickets_together",
        "avg_event_result_together",
        "avg_occupancy_rate_together",
        "first_played_together",
        "last_played_together",
        "score_explanation",
    ]

    for column in optional_columns:
        if column in candidates.columns:
            output_columns.append(column)

    output_columns += [
        "cooccurrence_strength",
        "recommendation_score",
        "recommendation_reason",
    ]

    return (
        candidates[output_columns]
        .sort_values("recommendation_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )