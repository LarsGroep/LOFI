import re
from itertools import combinations
from pathlib import Path

import pandas as pd


def normalize_artist_name(name):
    """
    Normalize artist names for matching and co-occurrence.
    """
    if pd.isna(name):
        return None

    name = str(name).strip().lower()
    name = re.sub(r"\s+", " ", name)

    if name in {"", "nan", "none", "null"}:
        return None

    return name


def clean_text(value):
    """
    Basic text cleaning.
    """
    if pd.isna(value):
        return None

    value = str(value).strip()
    value = re.sub(r"\s+", " ", value)

    if value.lower() in {"", "nan", "none", "null"}:
        return None

    return value


def find_column(df, candidates, required=False, table_name="dataframe"):
    """
    Find the first matching column from a list of candidate names.
    Case-insensitive.
    """
    lower_to_actual = {col.lower().strip(): col for col in df.columns}

    for candidate in candidates:
        key = candidate.lower().strip()
        if key in lower_to_actual:
            return lower_to_actual[key]

    if required:
        raise KeyError(
            f"Could not find required column in {table_name}. "
            f"Tried: {candidates}. Available columns: {list(df.columns)}"
        )

    return None


def split_lineup_text(value):
    """
    Split lineup text into artist names.

    Handles common separators:
    - semicolon
    - comma
    - newline
    - pipe

    Keeps B2B and '&' names intact for now.
    """
    if pd.isna(value):
        return []

    text = str(value)

    # Normalize separators
    text = text.replace("\n", ";")
    text = text.replace("|", ";")

    # Prefer semicolon splitting, common in exported lineup fields
    if ";" in text:
        parts = text.split(";")
    else:
        parts = text.split(",")

    artists = []

    for part in parts:
        cleaned = clean_text(part)
        if cleaned:
            artists.append(cleaned)

    return artists


def make_external_event_id(source, event_name=None, event_date=None, venue=None, raw_id=None):
    """
    Create a stable external event ID.
    """
    if raw_id is not None and not pd.isna(raw_id):
        return f"{source}_{str(raw_id).strip()}"

    parts = [
        source,
        clean_text(event_name) or "unknown_event",
        str(event_date) if not pd.isna(event_date) else "unknown_date",
        clean_text(venue) or "unknown_venue",
    ]

    key = "_".join(parts).lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")

    return key


def parse_partyflock_events(df):
    """
    Parse Partyflock Events.

    Expected shape:
    Usually one row per event-artist combination.

    Flexible column matching is used because scraper exports are not always civilized.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    table_name = "Partyflock Events"

    event_id_col = find_column(df, ["event_id", "id", "event_url", "url"], required=False, table_name=table_name)
    event_name_col = find_column(df, ["event_name", "event", "title", "name"], required=False, table_name=table_name)
    date_col = find_column(df, ["start_date", "event_date", "date", "datetime"], required=False, table_name=table_name)
    venue_col = find_column(df, ["venue", "location", "club"], required=False, table_name=table_name)
    city_col = find_column(df, ["city", "plaats"], required=False, table_name=table_name)
    country_col = find_column(df, ["country", "land"], required=False, table_name=table_name)
    artist_col = find_column(df, ["artist", "artist_name", "name_artist", "performer"], required=True, table_name=table_name)

    rows = []

    for _, row in df.iterrows():
        artist_raw = clean_text(row.get(artist_col))

        if not artist_raw:
            continue

        event_name = clean_text(row.get(event_name_col)) if event_name_col else None
        event_date = pd.to_datetime(row.get(date_col), errors="coerce") if date_col else pd.NaT
        venue = clean_text(row.get(venue_col)) if venue_col else None
        city = clean_text(row.get(city_col)) if city_col else None
        country = clean_text(row.get(country_col)) if country_col else None
        raw_id = row.get(event_id_col) if event_id_col else None

        rows.append(
            {
                "external_event_id": make_external_event_id(
                    source="partyflock_events",
                    event_name=event_name,
                    event_date=event_date,
                    venue=venue,
                    raw_id=raw_id,
                ),
                "source": "partyflock_events",
                "event_name": event_name,
                "event_date": event_date,
                "venue": venue,
                "city": city,
                "country": country,
                "artist_name_raw": artist_raw,
                "artist_name_clean": normalize_artist_name(artist_raw),
                "position_in_lineup": None,
            }
        )

    return pd.DataFrame(rows)


def parse_partyflock_lineups(df):
    """
    Parse Partyflock Lineups.

    Expected shape:
    Usually one row per event with a lineup text column.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    table_name = "Partyflock Lineups"

    event_id_col = find_column(df, ["event_id", "id", "event_url", "url"], required=False, table_name=table_name)
    event_name_col = find_column(df, ["event_name", "event", "title", "name"], required=False, table_name=table_name)
    date_col = find_column(df, ["start_date", "event_date", "date", "datetime"], required=False, table_name=table_name)
    venue_col = find_column(df, ["venue", "location", "club"], required=False, table_name=table_name)
    city_col = find_column(df, ["city", "plaats"], required=False, table_name=table_name)
    country_col = find_column(df, ["country", "land"], required=False, table_name=table_name)
    lineup_col = find_column(df, ["lineup", "line_up", "artists", "artist_names"], required=True, table_name=table_name)

    rows = []

    for _, row in df.iterrows():
        event_name = clean_text(row.get(event_name_col)) if event_name_col else None
        event_date = pd.to_datetime(row.get(date_col), errors="coerce") if date_col else pd.NaT
        venue = clean_text(row.get(venue_col)) if venue_col else None
        city = clean_text(row.get(city_col)) if city_col else None
        country = clean_text(row.get(country_col)) if country_col else None
        raw_id = row.get(event_id_col) if event_id_col else None

        external_event_id = make_external_event_id(
            source="partyflock_lineups",
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            raw_id=raw_id,
        )

        artists = split_lineup_text(row.get(lineup_col))

        for position, artist_raw in enumerate(artists, start=1):
            rows.append(
                {
                    "external_event_id": external_event_id,
                    "source": "partyflock_lineups",
                    "event_name": event_name,
                    "event_date": event_date,
                    "venue": venue,
                    "city": city,
                    "country": country,
                    "artist_name_raw": artist_raw,
                    "artist_name_clean": normalize_artist_name(artist_raw),
                    "position_in_lineup": position,
                }
            )

    return pd.DataFrame(rows)


def parse_ra_events_and_lineups(ra_events, ra_lineups):
    """
    Parse RA Events + RA Lineups.

    RA Events usually contains event metadata.
    RA Lineups usually contains event identifier + lineup text.
    This function tries to join them on a shared event ID / URL / event name.
    """
    if ra_lineups is None or ra_lineups.empty:
        return pd.DataFrame()

    table_name_events = "RA Events"
    table_name_lineups = "RA Lineups"

    # Lineup table columns
    lineup_event_id_col = find_column(
        ra_lineups,
        ["event_id", "ra_event_id", "id", "url", "event_url", "link"],
        required=False,
        table_name=table_name_lineups,
    )
    lineup_event_name_col = find_column(
        ra_lineups,
        ["event_name", "event", "title", "name"],
        required=False,
        table_name=table_name_lineups,
    )
    lineup_col = find_column(
        ra_lineups,
        ["lineup", "line_up", "artists", "artist_names"],
        required=True,
        table_name=table_name_lineups,
    )

    lineups = ra_lineups.copy()

    # Events metadata columns
    merged = lineups.copy()

    if ra_events is not None and not ra_events.empty:
        events_event_id_col = find_column(
            ra_events,
            ["event_id", "ra_event_id", "id", "url", "event_url", "link"],
            required=False,
            table_name=table_name_events,
        )
        events_event_name_col = find_column(
            ra_events,
            ["event_name", "event", "title", "name"],
            required=False,
            table_name=table_name_events,
        )

        if lineup_event_id_col and events_event_id_col:
            merged = lineups.merge(
                ra_events,
                left_on=lineup_event_id_col,
                right_on=events_event_id_col,
                how="left",
                suffixes=("_lineup", "_event"),
            )
        elif lineup_event_name_col and events_event_name_col:
            merged = lineups.merge(
                ra_events,
                left_on=lineup_event_name_col,
                right_on=events_event_name_col,
                how="left",
                suffixes=("_lineup", "_event"),
            )

    event_id_col = find_column(merged, ["event_id", "ra_event_id", "id", "url", "event_url", "link"], required=False, table_name="Merged RA")
    event_name_col = find_column(merged, ["event_name", "event", "title", "name"], required=False, table_name="Merged RA")
    date_col = find_column(merged, ["event_date", "start_date", "date", "datetime"], required=False, table_name="Merged RA")
    venue_col = find_column(merged, ["venue", "location", "club"], required=False, table_name="Merged RA")
    city_col = find_column(merged, ["city", "plaats"], required=False, table_name="Merged RA")
    country_col = find_column(merged, ["country", "land"], required=False, table_name="Merged RA")

    # After merge, lineup_col may have kept its original name.
    if lineup_col not in merged.columns:
        possible_lineup_col = find_column(merged, ["lineup", "line_up", "artists", "artist_names"], required=True, table_name="Merged RA")
    else:
        possible_lineup_col = lineup_col

    rows = []

    for _, row in merged.iterrows():
        event_name = clean_text(row.get(event_name_col)) if event_name_col else None
        event_date = pd.to_datetime(row.get(date_col), errors="coerce") if date_col else pd.NaT
        venue = clean_text(row.get(venue_col)) if venue_col else None
        city = clean_text(row.get(city_col)) if city_col else None
        country = clean_text(row.get(country_col)) if country_col else None
        raw_id = row.get(event_id_col) if event_id_col else None

        external_event_id = make_external_event_id(
            source="resident_advisor",
            event_name=event_name,
            event_date=event_date,
            venue=venue,
            raw_id=raw_id,
        )

        artists = split_lineup_text(row.get(possible_lineup_col))

        for position, artist_raw in enumerate(artists, start=1):
            rows.append(
                {
                    "external_event_id": external_event_id,
                    "source": "resident_advisor",
                    "event_name": event_name,
                    "event_date": event_date,
                    "venue": venue,
                    "city": city,
                    "country": country,
                    "artist_name_raw": artist_raw,
                    "artist_name_clean": normalize_artist_name(artist_raw),
                    "position_in_lineup": position,
                }
            )

    return pd.DataFrame(rows)


def combine_external_event_artists(*frames):
    """
    Combine parsed external event-artist frames.
    """
    frames = [df for df in frames if df is not None and not df.empty]

    if not frames:
        return pd.DataFrame(
            columns=[
                "external_event_id",
                "source",
                "event_name",
                "event_date",
                "venue",
                "city",
                "country",
                "artist_name_raw",
                "artist_name_clean",
                "position_in_lineup",
            ]
        )

    combined = pd.concat(frames, ignore_index=True)

    combined = combined.dropna(subset=["external_event_id", "artist_name_clean"])

    combined = combined.drop_duplicates(
        subset=["external_event_id", "source", "artist_name_clean"]
    )

    return combined.reset_index(drop=True)


def build_external_cooccurrence(external_event_artists):
    """
    Build external artist co-occurrence pairs from external event-artist rows.
    """
    rows = []

    if external_event_artists is None or external_event_artists.empty:
        return pd.DataFrame()

    for external_event_id, group in external_event_artists.groupby("external_event_id"):
        group = group.dropna(subset=["artist_name_clean"]).copy()

        # Remove duplicate artists within one event
        group = group.drop_duplicates(subset=["artist_name_clean"])

        artists = (
            group[["artist_name_raw", "artist_name_clean"]]
            .drop_duplicates()
            .sort_values("artist_name_clean")
            .to_dict("records")
        )

        if len(artists) < 2:
            continue

        event_info = group.iloc[0]

        for artist_a, artist_b in combinations(artists, 2):
            if artist_a["artist_name_clean"] == artist_b["artist_name_clean"]:
                continue

            rows.append(
                {
                    "external_event_id": external_event_id,
                    "source": event_info.get("source"),
                    "event_name": event_info.get("event_name"),
                    "event_date": event_info.get("event_date"),
                    "venue": event_info.get("venue"),
                    "city": event_info.get("city"),
                    "country": event_info.get("country"),
                    "artist_name_a": artist_a["artist_name_raw"],
                    "artist_name_clean_a": artist_a["artist_name_clean"],
                    "artist_name_b": artist_b["artist_name_raw"],
                    "artist_name_clean_b": artist_b["artist_name_clean"],
                }
            )

    pairs = pd.DataFrame(rows)

    if pairs.empty:
        return pairs

    grouped = pairs.groupby(
        ["artist_name_clean_a", "artist_name_clean_b"],
        dropna=False,
    )

    cooccurrence = grouped.agg(
        artist_name_a=("artist_name_a", "first"),
        artist_name_b=("artist_name_b", "first"),
        external_cooccur_count=("external_event_id", "nunique"),
        sources_together=("source", lambda x: " | ".join(sorted(x.dropna().astype(str).unique()))),
        venues_together=("venue", lambda x: " | ".join(sorted(x.dropna().astype(str).unique()))),
        cities_together=("city", lambda x: " | ".join(sorted(x.dropna().astype(str).unique()))),
        countries_together=("country", lambda x: " | ".join(sorted(x.dropna().astype(str).unique()))),
        first_seen_together=("event_date", "min"),
        last_seen_together=("event_date", "max"),
        example_events=("event_name", lambda x: " | ".join(sorted(x.dropna().astype(str).unique())[:10])),
    ).reset_index()

    cooccurrence = cooccurrence.sort_values(
        ["external_cooccur_count", "last_seen_together"],
        ascending=[False, False],
        na_position="last",
    )

    return cooccurrence.reset_index(drop=True)