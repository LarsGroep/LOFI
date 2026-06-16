import numpy as np
import pandas as pd

def safe_divide(numerator, denominator):
    """Divide safely or return NaN if denominator is zero."""
    return np.where(denominator.notna() & (denominator != 0), numerator / denominator, np.nan)

def add_performance_features(artist_events):
    """
    Add event-level performance features to artist_events.
    Expected input is already cleaned by clean_artist_events().
    """
    df = artist_events.copy()

    df["revenue_per_visitor"] = safe_divide(df["total_revenue"], df["total_attendance"])

    df["ticket_revenue_per_visitor"] = safe_divide(
        df["ticketing_revenue"],
        df["total_visitors"],
    )

    df["bar_revenue_per_visitor"] = safe_divide(
        df["bar_revenue"],
        df["total_visitors"],
    )

    df["profit_margin"] = safe_divide(
        df["event_result"],
        df["total_revenue"],
    )

    df["cost_ratio"] = safe_divide(
        df["total_cost"],
        df["total_revenue"],
    )

    df["artist_cost_ratio"] = safe_divide(
        df["artist_costs"],
        df["total_revenue"],
    )

    return df


def add_recency_features(artist_events):
    """
    Add months_since_event and recency_weight.

    Uses the latest event_date in the dataset as reference date.
    This keeps the scoring reproducible instead of depending on today's date.
    """
    df = artist_events.copy()

    reference_date = df["event_date"].max()

    df["months_since_event"] = np.where(
        df["event_date"].notna(),
        (reference_date - df["event_date"]).dt.days / 30.44,
        np.nan,
    )

    df["recency_weight"] = np.exp(-df["months_since_event"] / 24)

    return df

def compute_percentile_score(series, higher_is_better=True):
    """
    Convert numeric values to percentile scores from 0 to 100.

    Higher values receive higher scores by default.
    """
    if higher_is_better:
        return series.rank(pct=True, na_option="keep") * 100

    return (1 - series.rank(pct=True, na_option="keep")) * 100


def add_percentile_scores(artist_events):
    """
    Add global percentile scores for core performance metrics.

    First iteration uses global scoring.
    Later we can replace this with context-aware scoring by genre/event_type.
    """
    df = artist_events.copy()

    df["occupancy_score"] = compute_percentile_score(
        df["occupancy_rate"],
        higher_is_better=True,
    )

    df["event_result_score"] = compute_percentile_score(
        df["event_result"],
        higher_is_better=True,
    )

    df["revenue_per_visitor_score"] = compute_percentile_score(
        df["revenue_per_visitor"],
        higher_is_better=True,
    )

    df["profit_margin_score"] = compute_percentile_score(
        df["profit_margin"],
        higher_is_better=True,
    )

    return df

def add_historical_event_score(artist_events):
    """
    Combine event-level score components into one historical_event_score.

    Score is still event-level here. Reliability is added later at artist level.
    """
    df = artist_events.copy()

    df["historical_event_score"] = (
        0.30 * df["occupancy_score"]
        + 0.25 * df["profit_margin_score"]
        + 0.20 * df["revenue_per_visitor_score"]
        + 0.15 * df["event_result_score"]
    )

    df["weighted_historical_event_score"] = (
        df["historical_event_score"] * df["recency_weight"]
    )

    return df

def weighted_average_score(group):
    """
    Recency-weighted average of historical_event_score.

    Ignores rows where either score or weight is missing.
    """
    valid = group.dropna(subset=["historical_event_score", "recency_weight"])

    if valid.empty:
        return np.nan

    weight_sum = valid["recency_weight"].sum()

    if weight_sum == 0:
        return np.nan

    return (
        valid["historical_event_score"] * valid["recency_weight"]
    ).sum() / weight_sum


def unique_join(series):
    """
    Join unique non-empty values into a comma-separated string.
    """
    values = (
        series.dropna()
        .astype(str)
        .str.strip()
    )

    values = values[values != ""]

    return ", ".join(sorted(values.unique()))


def aggregate_artist_scores(artist_events):
    """
    Aggregate event-level features to artist-level scores.
    """
    df = artist_events.copy()

    grouped = df.groupby(["artist_id", "artist_name"], dropna=False)

    artist_scores = grouped.agg(
        event_count=("event_id", "nunique"),
        first_event_date=("event_date", "min"),
        last_event_date=("event_date", "max"),
        genres=("genre", unique_join),

        avg_occupancy_rate=("occupancy_rate", "mean"),
        avg_total_visitors=("total_visitors", "mean"),
        avg_actual_tickets=("actual_tickets", "mean"),
        avg_ticketing_revenue=("ticketing_revenue", "mean"),
        avg_bar_revenue=("bar_revenue", "mean"),
        avg_total_revenue=("total_revenue", "mean"),
        avg_total_cost=("total_cost", "mean"),
        avg_event_result=("event_result", "mean"),
        avg_artist_costs=("artist_costs", "mean"),

        avg_revenue_per_visitor=("revenue_per_visitor", "mean"),
        avg_profit_margin=("profit_margin", "mean"),
        avg_historical_event_score=("historical_event_score", "mean"),
    ).reset_index()

    weighted_scores = grouped.apply(weighted_average_score).reset_index(
        name="recency_weighted_score"
    )

    artist_scores = artist_scores.merge(
        weighted_scores,
        on=["artist_id", "artist_name"],
        how="left",
    )

    return artist_scores

def add_confidence_scores(artist_scores):
    """
    Add reliability, data completeness, recency confidence, and final confidence.
    """
    df = artist_scores.copy()

    max_event_count = df["event_count"].max()

    if pd.isna(max_event_count) or max_event_count <= 0:
        df["reliability_score"] = np.nan
    else:
        df["reliability_score"] = (
            np.log1p(df["event_count"]) / np.log1p(max_event_count) * 100
        )

    key_performance_cols = [
        "avg_occupancy_rate",
        "avg_total_revenue",
        "avg_event_result",
        "avg_total_visitors",
        "avg_artist_costs",
    ]

    df["data_completeness"] = (
        df[key_performance_cols].notna().sum(axis=1)
        / len(key_performance_cols)
        * 100
    )

    reference_date = df["last_event_date"].max()

    df["months_since_last_event"] = np.where(
        df["last_event_date"].notna(),
        (reference_date - df["last_event_date"]).dt.days / 30.44,
        np.nan,
    )

    df["recency_confidence"] = (
        np.exp(-df["months_since_last_event"] / 24) * 100
    )

    event_count_confidence = np.minimum(df["event_count"] / 5, 1) * 100

    df["confidence_score"] = (
        0.50 * event_count_confidence
        + 0.25 * df["data_completeness"]
        + 0.25 * df["recency_confidence"]
    )

    return df

def add_final_historical_lofi_score(artist_scores):
    """
    Add final artist-level historical LOFI score.

    Main score:
        0.85 * recency_weighted_score + 0.15 * reliability_score

    Fallback:
        0.85 * avg_historical_event_score + 0.15 * reliability_score
    """
    df = artist_scores.copy()

    base_score = df["recency_weighted_score"].copy()

    base_score = base_score.fillna(df["avg_historical_event_score"])

    df["historical_lofi_score"] = (
        0.85 * base_score
        + 0.15 * df["reliability_score"]
    )

    score_cols = [
        "reliability_score",
        "data_completeness",
        "recency_confidence",
        "confidence_score",
        "historical_lofi_score",
        "avg_historical_event_score",
        "recency_weighted_score",
    ]

    for col in score_cols:
        if col in df.columns:
            df[col] = df[col].round(2)

    return df

def generate_score_explanation(row):
    """
    Generate a simple human-readable score explanation.
    """
    score = row.get("historical_lofi_score")
    confidence = row.get("confidence_score")
    event_count = row.get("event_count")
    occupancy = row.get("avg_occupancy_rate")
    profit_margin = row.get("avg_profit_margin")

    if pd.isna(score):
        return "Insufficient data for scoring."

    if event_count == 1:
        return "Single LOFI appearance, interpret carefully."

    if pd.notna(confidence) and confidence < 40:
        return "Low confidence: limited or incomplete LOFI history."

    if (
        pd.notna(occupancy)
        and pd.notna(profit_margin)
        and occupancy >= 0.75
        and profit_margin <= 0
    ):
        return "Strong attendance signal, but weaker profitability."

    if score >= 75 and pd.notna(confidence) and confidence >= 60:
        return "Strong historical LOFI performance with solid confidence."

    if score >= 50:
        return "Moderate historical LOFI performance based on available event data."

    return "Limited historical LOFI performance. Could indicate newer or inconsistent events."


def add_score_explanations(artist_scores):
    """
    Add text explanations for the score.
    """
    df = artist_scores.copy()

    df["score_explanation"] = df.apply(generate_score_explanation, axis=1)

    return df


def build_historical_performance_scores(artist_events):
    """
    Full historical performance scoring pipeline.

    Input:
        cleaned artist_events dataframe

    Output:
        artist-level historical performance scores
    """
    artist_events = add_performance_features(artist_events)
    artist_events = add_recency_features(artist_events)
    artist_events = add_percentile_scores(artist_events)
    artist_events = add_historical_event_score(artist_events)

    artist_scores = aggregate_artist_scores(artist_events)
    artist_scores = add_confidence_scores(artist_scores)
    artist_scores = add_final_historical_lofi_score(artist_scores)
    artist_scores = add_score_explanations(artist_scores)

    final_columns = [
        "artist_id",
        "artist_name",
        "event_count",
        "first_event_date",
        "last_event_date",
        "genres",

        "avg_occupancy_rate",
        "avg_total_visitors",
        "avg_actual_tickets",
        "avg_ticketing_revenue",
        "avg_bar_revenue",
        "avg_total_revenue",
        "avg_total_cost",
        "avg_event_result",
        "avg_artist_costs",
        "avg_revenue_per_visitor",
        "avg_profit_margin",

        "reliability_score",
        "data_completeness",
        "recency_confidence",
        "confidence_score",
        "historical_lofi_score",
        "score_explanation",
    ]

    existing_columns = [col for col in final_columns if col in artist_scores.columns]

    artist_scores = artist_scores[existing_columns].sort_values(
        "historical_lofi_score",
        ascending=False,
        na_position="last",
    )

    return artist_scores.reset_index(drop=True)