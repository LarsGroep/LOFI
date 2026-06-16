from itertools import combinations
import pandas as pd
import re

def normalize_artist_name(name):
    """
    Normalize artist names for matching.

    This handles:
    - casing differences: HUNEE / Hunee
    - extra whitespace
    - repeated spaces
    """
    if pd.isna(name):
        return None

    name = str(name).strip().lower()
    name = re.sub(r"\s+", " ", name)

    if name in {"", "nan", "none", "null"}:
        return None

    return name

def build_artist_lookup(artist_events):
    """
    Build lookup from normalized artist name to one canonical artist_id.

    If duplicate names exist with different casing or IDs, keep the most frequent one.
    """
    lookup = (
        artist_events[["artist_id", "artist_name"]]
        .dropna()
        .drop_duplicates()
        .copy()
    )

    lookup["artist_name_clean"] = lookup["artist_name"].apply(normalize_artist_name)

    # Count how often each artist_id/name version appears in artist_events
    counts = (
        artist_events[["artist_id", "artist_name"]]
        .dropna()
        .copy()
    )
    counts["artist_name_clean"] = counts["artist_name"].apply(normalize_artist_name)

    counts = (
        counts.groupby(["artist_name_clean", "artist_id", "artist_name"])
        .size()
        .reset_index(name="name_version_count")
    )

    # For each normalized name, keep the most frequent version
    counts = counts.sort_values(
        ["artist_name_clean", "name_version_count"],
        ascending=[True, False],
    )

    canonical_lookup = counts.drop_duplicates(
        subset=["artist_name_clean"],
        keep="first",
    )

    canonical_lookup = canonical_lookup[
        ["artist_name_clean", "artist_id", "artist_name"]
    ].copy()

    return canonical_lookup


def attach_artist_ids(parsed_lineups, artist_events):
    """
    Attach artist_id to parsed lineup rows using normalized artist names.
    """
    parsed = parsed_lineups.copy()

    parsed["artist_name_clean"] = parsed["artist_name_raw"].apply(normalize_artist_name)

    lookup = build_artist_lookup(artist_events)

    parsed = parsed.merge(
        lookup,
        on="artist_name_clean",
        how="left",
        suffixes=("", "_matched"),
    )

    return parsed


def build_event_artist_table(parsed_lineups_with_ids):
    """
    Build unique event-artist rows.

    Keeps only rows where an artist_id was matched.
    """
    event_artists = parsed_lineups_with_ids.dropna(subset=["event_id", "artist_id"]).copy()

    event_artists = event_artists[
        [
            "event_id",
            "event_name",
            "event_date",
            "genre",
            "kind",
            "event_type",
            "artist_id",
            "artist_name",
        ]
    ].drop_duplicates()

    return event_artists


def build_cooccurrence_pairs(event_artists):
    """
    Build all artist pairs per event.

    Prevents fake self-pairs caused by duplicate aliases.
    """
    rows = []

    for event_id, group in event_artists.groupby("event_id"):
        group = group.copy()

        group["artist_name_normalized"] = group["artist_name"].apply(normalize_artist_name)

        # Remove duplicate canonical artists within the same event
        group = group.drop_duplicates(subset=["artist_name_normalized"])

        artists = (
            group[["artist_id", "artist_name", "artist_name_normalized"]]
            .drop_duplicates()
            .sort_values("artist_id")
            .to_dict("records")
        )

        if len(artists) < 2:
            continue

        event_info = group.iloc[0]

        for artist_a, artist_b in combinations(artists, 2):
            # Extra safety: do not pair same normalized artist name
            if artist_a["artist_name_normalized"] == artist_b["artist_name_normalized"]:
                continue

            # Extra safety: do not pair same artist_id
            if artist_a["artist_id"] == artist_b["artist_id"]:
                continue

            rows.append(
                {
                    "event_id": event_id,
                    "event_name": event_info.get("event_name"),
                    "event_date": event_info.get("event_date"),
                    "genre": event_info.get("genre"),
                    "kind": event_info.get("kind"),
                    "event_type": event_info.get("event_type"),
                    "artist_id_a": artist_a["artist_id"],
                    "artist_name_a": artist_a["artist_name"],
                    "artist_id_b": artist_b["artist_id"],
                    "artist_name_b": artist_b["artist_name"],
                }
            )

    return pd.DataFrame(rows)


def add_event_performance_to_pairs(pairs, events):
    """
    Attach event-level performance metrics to artist pairs.
    """
    performance_cols = [
        "event_id",
        "total_visitors",
        "actual_tickets",
        "ticketing_revenue",
        "bar_revenue",
        "total_revenue",
        "total_cost",
        "event_result",
        "occupancy_rate",
    ]

    available_cols = [col for col in performance_cols if col in events.columns]

    pairs = pairs.merge(
        events[available_cols].drop_duplicates(subset=["event_id"]),
        on="event_id",
        how="left",
    )

    return pairs


def aggregate_cooccurrence_pairs(pairs_with_performance):
    """
    Aggregate pair-level event rows into co-occurrence summary.
    """
    if pairs_with_performance.empty:
        return pd.DataFrame()

    grouped = pairs_with_performance.groupby(
        ["artist_id_a", "artist_name_a", "artist_id_b", "artist_name_b"],
        dropna=False,
    )

    cooccurrence = grouped.agg(
        cooccur_count=("event_id", "nunique"),
        first_played_together=("event_date", "min"),
        last_played_together=("event_date", "max"),
        events_together=("event_name", lambda x: " | ".join(sorted(x.dropna().astype(str).unique()))),

        avg_total_visitors_together=("total_visitors", "mean"),
        avg_actual_tickets_together=("actual_tickets", "mean"),
        avg_ticketing_revenue_together=("ticketing_revenue", "mean"),
        avg_bar_revenue_together=("bar_revenue", "mean"),
        avg_total_revenue_together=("total_revenue", "mean"),
        avg_total_cost_together=("total_cost", "mean"),
        avg_event_result_together=("event_result", "mean"),
        avg_occupancy_rate_together=("occupancy_rate", "mean"),
    ).reset_index()

    cooccurrence = cooccurrence.sort_values(
        ["cooccur_count", "avg_event_result_together", "avg_occupancy_rate_together"],
        ascending=[False, False, False],
        na_position="last",
    )

    return cooccurrence.reset_index(drop=True)


def build_event_artist_table(parsed_lineups_with_ids):
    """
    Build unique event-artist rows.

    Keeps only rows where an artist_id was matched.
    Removes duplicate canonical artists within the same event.
    """
    event_artists = parsed_lineups_with_ids.dropna(
        subset=["event_id", "artist_id"]
    ).copy()

    event_artists["artist_name_normalized"] = event_artists["artist_name"].apply(
        normalize_artist_name
    )

    event_artists = event_artists[
        [
            "event_id",
            "event_name",
            "event_date",
            "genre",
            "kind",
            "event_type",
            "artist_id",
            "artist_name",
            "artist_name_normalized",
        ]
    ].drop_duplicates(
        subset=["event_id", "artist_name_normalized"]
    )

    return event_artists

def build_lofi_cooccurrence(parsed_lineups, artist_events, events):
    """
    Full LOFI co-occurrence pipeline.
    """
    parsed_with_ids = attach_artist_ids(parsed_lineups, artist_events)
    event_artists = build_event_artist_table(parsed_with_ids)
    pairs = build_cooccurrence_pairs(event_artists)
    pairs_with_performance = add_event_performance_to_pairs(pairs, events)
    cooccurrence = aggregate_cooccurrence_pairs(pairs_with_performance)

    return cooccurrence, parsed_with_ids, event_artists