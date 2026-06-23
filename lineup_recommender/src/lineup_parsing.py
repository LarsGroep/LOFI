import re
import pandas as pd


def clean_artist_name(name):
    """
    Clean a single artist name string.
    """
    if pd.isna(name):
        return None

    name = str(name).strip()

    # Remove obvious empty garbage
    if name == "" or name.lower() in {"nan", "none", "null"}:
        return None

    # Normalize whitespace
    name = re.sub(r"\s+", " ", name)

    return name


def split_artist_source(value):
    """
    Split artist_source text into artist names.

    First iteration:
    - split on commas, semicolons, pipes, newlines
    - keep B2B / & cases as-is for now
    """
    if pd.isna(value):
        return []

    text = str(value)

    # Normalize separators
    text = text.replace("\n", ",")
    text = text.replace(";", ",")
    text = text.replace("|", ",")

    parts = text.split(",")

    artists = []

    for part in parts:
        cleaned = clean_artist_name(part)
        if cleaned:
            artists.append(cleaned)

    return artists


def build_parsed_event_lineups(events):
    """
    Build one row per event-artist from events dataframe.

    Uses artist_source as the first source column.
    """
    rows = []

    for _, event in events.iterrows():
        event_id = event.get("event_id")
        event_name = event.get("event_name")
        event_date = event.get("event_date")
        genre = event.get("genre")
        kind = event.get("kind")
        event_type = event.get("event_type")

        source_column = "artist_source"
        artist_names = split_artist_source(event.get(source_column))

        for position, artist_name in enumerate(artist_names, start=1):
            rows.append(
                {
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_date": event_date,
                    "genre": genre,
                    "kind": kind,
                    "event_type": event_type,
                    "artist_name_raw": artist_name,
                    "artist_name_clean": artist_name.lower().strip(),
                    "source_column": source_column,
                    "position_in_lineup": position,
                }
            )

    parsed = pd.DataFrame(rows)

    return parsed