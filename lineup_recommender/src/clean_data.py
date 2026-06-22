import pandas as pd


def clean_numeric_series(s):
    """
    Convert a pandas Series to numeric.

    Handles:
    - euro signs
    - dollar signs
    - percent signs
    - spaces
    - comma decimals
    """
    if pd.api.types.is_numeric_dtype(s):
        return s

    s = (
        s.astype(str)
        .str.replace("€", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )

    s = s.replace({"nan": None, "None": None, "": None})

    return pd.to_numeric(s, errors="coerce")


def clean_percentage_series(s):
    """
    Convert percentage-like values to 0-1 scale.

    If values look like 0-100, divide by 100.
    If values already look like 0-1, keep them.
    """
    numeric = clean_numeric_series(s)

    non_null = numeric.dropna()

    if len(non_null) == 0:
        return numeric

    if non_null.median() > 1.5:
        numeric = numeric / 100

    return numeric


def clean_date_series(s):
    """
    Convert a Series to datetime.
    """
    return pd.to_datetime(s, errors="coerce")


def clean_string_series(s):
    """
    Strip whitespace from string columns.
    """
    return s.astype(str).str.strip().replace({"nan": None, "None": None, "": None})


def clean_artist_events(df):
    """
    Clean artist-event level LOFI data.
    """
    df = df.copy()

    string_cols = [
        "artist_id",
        "artist_name",
        "event_id",
        "event_name",
        "genre",
        "kind",
        "event_type",
        "event_status",
    ]

    numeric_cols = [
        "total_visitors",
        "actual_tickets",
        "ticketing_revenue",
        "bar_revenue",
        "total_revenue",
        "total_cost",
        "event_result",
        "artist_costs",
    ]

    for col in string_cols:
        if col in df.columns:
            df[col] = clean_string_series(df[col])

    for col in numeric_cols:
        if col in df.columns:
            df[col] = clean_numeric_series(df[col])

    if "occupancy_rate" in df.columns:
        df["occupancy_rate"] = clean_percentage_series(df["occupancy_rate"])

    if "event_date" in df.columns:
        df["event_date"] = clean_date_series(df["event_date"])

    df = df.dropna(subset=["artist_id", "event_id"])

    return df


def clean_artists(df):
    """
    Clean artist-level LOFI data.
    """
    df = df.copy()

    string_cols = ["artist_id", "artist_name", "genres"]

    numeric_cols = [
        "event_count",
        "avg_visitors",
        "avg_tickets",
        "avg_event_result",
        "total_event_result",
    ]

    date_cols = ["first_event_date", "last_event_date"]

    for col in string_cols:
        if col in df.columns:
            df[col] = clean_string_series(df[col])

    for col in numeric_cols:
        if col in df.columns:
            df[col] = clean_numeric_series(df[col])

    if "avg_occupancy_rate" in df.columns:
        df["avg_occupancy_rate"] = clean_percentage_series(df["avg_occupancy_rate"])

    for col in date_cols:
        if col in df.columns:
            df[col] = clean_date_series(df[col])

    return df


def clean_events(df):
    """
    Clean event-level LOFI data.
    """
    df = df.copy()

    string_cols = [
        "event_id",
        "event_name",
        "weekday",
        "kind",
        "event_type",
        "event_status",
        "genre",
        "Lineup",
        "Line-up (artiesten) (DB)",
        "Timetable",
        "artist_source",
    ]

    numeric_cols = [
        "year",
        "month",
        "quarter",
        "visitor_capacity",
        "total_visitors",
        "actual_tickets",
        "ticketing_revenue",
        "bar_revenue",
        "total_revenue",
        "total_sales",
        "total_cost",
        "event_result",
        "artist_costs",
        "ticket_forecast",
        "visitor_forecast",
        "result_forecast",
        "ticket_forecast_error",
        "visitor_forecast_error",
        "result_forecast_error",
    ]

    for col in string_cols:
        if col in df.columns:
            df[col] = clean_string_series(df[col])

    for col in numeric_cols:
        if col in df.columns:
            df[col] = clean_numeric_series(df[col])

    if "occupancy_rate" in df.columns:
        df["occupancy_rate"] = clean_percentage_series(df["occupancy_rate"])

    if "event_date" in df.columns:
        df["event_date"] = clean_date_series(df["event_date"])

    return df