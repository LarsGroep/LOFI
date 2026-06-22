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


def build_external_candidates_for_artist(
    selected_artist_name: str,
    external_cooccurrence_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build candidates from external public co-lineup data.

    Unlike attach_external_scene_scores, this can create external-only candidates.
    """
    if external_cooccurrence_df is None or external_cooccurrence_df.empty:
        return pd.DataFrame()

    required_columns = {
        "artist_name_clean_a",
        "artist_name_clean_b",
        "artist_name_a",
        "artist_name_b",
        "external_cooccur_count",
        "external_scene_score",
    }

    missing_columns = required_columns - set(external_cooccurrence_df.columns)

    if missing_columns:
        raise ValueError(
            f"external_cooccurrence_df is missing columns: {missing_columns}"
        )

    selected_key = normalize_artist_name(selected_artist_name)

    df = external_cooccurrence_df.copy()

    df["artist_key_a"] = df["artist_name_clean_a"].apply(normalize_artist_name)
    df["artist_key_b"] = df["artist_name_clean_b"].apply(normalize_artist_name)

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
        "external_cooccur_count": "sum",
        "external_scene_score": "max",
    }

    optional_columns = {
        "source_count": "max",
        "sources_together": "first",
        "venues_together": "first",
        "cities_together": "first",
        "countries_together": "first",
        "first_seen_together": "min",
        "last_seen_together": "max",
        "example_events": "first",
    }

    for column, method in optional_columns.items():
        if column in pairs.columns:
            aggregation[column] = method

    candidates = (
        pairs.groupby("candidate_key", as_index=False)
        .agg(aggregation)
        .sort_values("external_cooccur_count", ascending=False)
    )

    candidates["cooccur_count"] = 0
    candidates["is_external_only_candidate"] = True

    rename_columns = {
        "first_seen_together": "first_seen_together_external",
        "last_seen_together": "last_seen_together_external",
        "example_events": "example_events_external",
    }

    candidates = candidates.rename(columns=rename_columns)

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


def attach_external_scene_scores(
    candidates: pd.DataFrame,
    selected_artist_name: str,
    external_cooccurrence_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Attach public external scene evidence to existing LOFI candidates.

    Important:
    This does not create external-only candidates.
    It only enriches candidates already found through LOFI co-occurrence.
    """

    candidates = candidates.copy()

    default_values = {
        "external_cooccur_count": 0,
        "source_count": 0,
        "sources_together": None,
        "venues_together": None,
        "cities_together": None,
        "countries_together": None,
        "first_seen_together_external": None,
        "last_seen_together_external": None,
        "example_events_external": None,
        "external_scene_score": 0.0,
        "has_external_scene_evidence": False,
    }

    if external_cooccurrence_df is None or external_cooccurrence_df.empty:
        for column, value in default_values.items():
            candidates[column] = value
        return candidates

    required_columns = {
        "artist_name_clean_a",
        "artist_name_clean_b",
        "external_cooccur_count",
        "sources_together",
        "external_scene_score",
    }

    missing_columns = required_columns - set(external_cooccurrence_df.columns)

    if missing_columns:
        raise ValueError(
            f"external_cooccurrence_df is missing columns: {missing_columns}"
        )

    selected_key = normalize_artist_name(selected_artist_name)

    external = external_cooccurrence_df.copy()

    external["artist_key_a"] = external["artist_name_clean_a"].apply(
        normalize_artist_name
    )
    external["artist_key_b"] = external["artist_name_clean_b"].apply(
        normalize_artist_name
    )

    mask = (external["artist_key_a"] == selected_key) | (
        external["artist_key_b"] == selected_key
    )

    external_pairs = external[mask].copy()

    if external_pairs.empty:
        for column, value in default_values.items():
            candidates[column] = value
        return candidates

    external_pairs["candidate_key"] = np.where(
        external_pairs["artist_key_a"] == selected_key,
        external_pairs["artist_key_b"],
        external_pairs["artist_key_a"],
    )

    aggregation = {
        "external_cooccur_count": "sum",
        "external_scene_score": "max",
        "sources_together": "first",
    }

    optional_columns = {
        "source_count": "max",
        "venues_together": "first",
        "cities_together": "first",
        "countries_together": "first",
        "first_seen_together": "min",
        "last_seen_together": "max",
        "example_events": "first",
    }

    for column, method in optional_columns.items():
        if column in external_pairs.columns:
            aggregation[column] = method

    external_by_candidate = (
        external_pairs.groupby("candidate_key", as_index=False)
        .agg(aggregation)
    )

    rename_columns = {
        "first_seen_together": "first_seen_together_external",
        "last_seen_together": "last_seen_together_external",
        "example_events": "example_events_external",
    }

    external_by_candidate = external_by_candidate.rename(columns=rename_columns)

    enriched = candidates.merge(
        external_by_candidate,
        on="candidate_key",
        how="left",
    )

    for column, value in default_values.items():
        if column not in enriched.columns:
            enriched[column] = value
        elif value is not None:
            enriched[column] = enriched[column].fillna(value)

    enriched["has_external_scene_evidence"] = (
        pd.to_numeric(enriched["external_cooccur_count"], errors="coerce").fillna(0) > 0
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

    external_count = row.get("external_cooccur_count", 0)
    external_score = row.get("external_scene_score", 0)

    if pd.notna(external_count) and external_count > 0:
        reasons.append(
            f"also has {int(external_count)} public external co-lineup connection(s)"
        )

    if pd.notna(external_score) and external_score > 0:
        reasons.append(f"has an external scene score of {external_score:.1f}")

    return "Recommended because the artist " + ", ".join(reasons) + "."


def recommend_artists_for_artist(
    selected_artist_name: str,
    historical_scores_df: pd.DataFrame,
    cooccurrence_df: pd.DataFrame,
    external_cooccurrence_df: pd.DataFrame | None = None,
    min_confidence: float = 0,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Deterministic LOFI-only artist recommender.

    This version uses:
    - LOFI artist co-occurrence
    - historical LOFI score
    - confidence score

    It optionally uses:
    - external public scene co-occurrence as a small bonus signal

    It does not use:
    - Chartmetric
    - LLM reasoning

    Important:
    Missing historical_lofi_score is not hidden. It is exposed in the output and
    receives a neutral placeholder for scoring, with a small penalty.
    """
    lofi_candidates = build_candidates_for_artist(
        selected_artist_name=selected_artist_name,
        cooccurrence_df=cooccurrence_df,
    )

    if not lofi_candidates.empty:
        lofi_candidates["is_external_only_candidate"] = False

    external_candidates = build_external_candidates_for_artist(
        selected_artist_name=selected_artist_name,
        external_cooccurrence_df=external_cooccurrence_df,
    )

    candidate_frames = [
        frame for frame in [lofi_candidates, external_candidates]
        if frame is not None and not frame.empty
    ]

    if not candidate_frames:
        return pd.DataFrame()

    candidates = pd.concat(candidate_frames, ignore_index=True)

    # If an artist appears through both LOFI and external data, merge the evidence.
    aggregation = {
        "candidate_artist": "first",
        "cooccur_count": "sum",
        "is_external_only_candidate": "min",
    }

    optional_sum_or_max_columns = {
        "external_cooccur_count": "sum",
        "external_scene_score": "max",
        "source_count": "max",
    }

    for column, method in optional_sum_or_max_columns.items():
        if column in candidates.columns:
            aggregation[column] = method

    optional_first_columns = [
        "sources_together",
        "venues_together",
        "cities_together",
        "countries_together",
        "first_seen_together_external",
        "last_seen_together_external",
        "example_events_external",
        "avg_total_visitors_together",
        "avg_actual_tickets_together",
        "avg_ticketing_revenue_together",
        "avg_bar_revenue_together",
        "avg_total_revenue_together",
        "avg_total_cost_together",
        "avg_event_result_together",
        "avg_occupancy_rate_together",
        "first_played_together",
        "last_played_together",
        "events_together",
    ]

    for column in optional_first_columns:
        if column in candidates.columns:
            aggregation[column] = "first"

    candidates = candidates.groupby("candidate_key", as_index=False).agg(aggregation)

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

    if "external_cooccur_count" not in candidates.columns:
        candidates = attach_external_scene_scores(
            candidates=candidates,
            selected_artist_name=selected_artist_name,
            external_cooccurrence_df=external_cooccurrence_df,
        )
    else:
        candidates["external_cooccur_count"] = candidates["external_cooccur_count"].fillna(0)
        candidates["external_scene_score"] = candidates["external_scene_score"].fillna(0)
        candidates["has_external_scene_evidence"] = (
            pd.to_numeric(candidates["external_cooccur_count"], errors="coerce").fillna(0) > 0
        )

    # External evidence is currently used only as a small bonus.
    # This prevents noisy public scraper data from dominating LOFI-specific evidence.
# External evidence is a small bonus for LOFI-backed candidates,
# but a stronger signal for external-only candidates.
    if "is_external_only_candidate" not in candidates.columns:
        candidates["is_external_only_candidate"] = False

    external_score_numeric = pd.to_numeric(
        candidates["external_scene_score"],
        errors="coerce",
    ).fillna(0)

    candidates["external_scene_bonus"] = np.where(
        candidates["has_external_scene_evidence"],
        np.where(
            candidates["is_external_only_candidate"],
            35.0 * external_score_numeric / 100.0,
            10.0 * external_score_numeric / 100.0,
        ),
        0.0,
    )

    candidates["recommendation_score"] = (
        candidates["recommendation_score"] + candidates["external_scene_bonus"]
    ).clip(lower=0, upper=100)

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
        "external_cooccur_count",
        "source_count",
        "sources_together",
        "venues_together",
        "cities_together",
        "countries_together",
        "first_seen_together_external",
        "last_seen_together_external",
        "example_events_external",
        "external_scene_score",
        "external_scene_bonus",
        "has_external_scene_evidence",
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