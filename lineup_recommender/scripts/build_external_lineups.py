from pathlib import Path
import sys

import pandas as pd

CURRENT_FILE = Path(__file__).resolve()
FEATURE_ROOT = CURRENT_FILE.parents[1]
SRC_DIR = FEATURE_ROOT / "src"

sys.path.append(str(SRC_DIR))

from config import (
    PARTYFLOCK_EVENTS_PATH,
    PARTYFLOCK_LINEUPS_PATH,
    RA_EVENTS_PATH,
    RA_LINEUPS_PATH,
    EXTERNAL_EVENT_ARTISTS_PATH,
    INTERIM_DIR,
)

from external_lineups import (
    parse_partyflock_events,
    parse_partyflock_lineups,
    parse_ra_events_and_lineups,
    combine_external_event_artists,
)


def read_wrapped_semicolon_csv(path):
    """
    Reads files where every full row may be wrapped as one quoted string.
    This is needed for partyflock_lineups.csv, which pandas otherwise reads as 1 column.
    """
    import csv

    last_error = None

    for encoding in ["utf-8-sig", "utf-8", "utf-16", "latin1"]:
        try:
            rows = []

            with open(path, encoding=encoding) as f:
                for line in f:
                    line = line.rstrip("\n").rstrip("\r")

                    if not line:
                        continue

                    # Some exports wrap the whole row in quotes.
                    if len(line) >= 2 and line[0] == '"' and line[-1] == '"':
                        line = line[1:-1]

                    # Restore doubled quotes.
                    line = line.replace('""', '"')

                    parsed = next(
                        csv.reader(
                            [line],
                            delimiter=";",
                            quotechar='"',
                            doublequote=True,
                        )
                    )

                    rows.append(parsed)

            if not rows:
                raise ValueError("No rows found.")

            header = rows[0]
            data = rows[1:]

            bad_rows = [row for row in data if len(row) != len(header)]

            if bad_rows:
                raise ValueError(
                    f"Found {len(bad_rows)} malformed rows. "
                    f"Expected {len(header)} columns, got examples like: {bad_rows[:2]}"
                )

            return pd.DataFrame(data, columns=header)

        except Exception as error:
            last_error = error

    raise ValueError(f"Could not read wrapped semicolon CSV: {path}. Last error: {last_error}")


def read_csv_if_exists(path, label):
    print(f"\nChecking {label}:")
    print(f"Path: {path}")
    print(f"Exists: {path.exists()}")

    if not path.exists():
        print(f"Skipping missing file: {path}")
        return None

    if path.stat().st_size == 0:
        print(f"Skipping empty file: {path}")
        return None

    print(f"File size: {path.stat().st_size} bytes")

    try:
        if label == "Partyflock Events":
            df = pd.read_csv(
                path,
                sep=";",
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="warn",
            )

        elif label == "Partyflock Lineups":
            df = read_wrapped_semicolon_csv(path)

        elif label == "RA Events":
            df = pd.read_csv(
                path,
                sep=";",
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="warn",
            )

            if "link" in df.columns:
                df["id"] = (
                    df["link"]
                    .astype(str)
                    .str.extract(r"/events/(\d+)")[0]
                    .astype("string")
                )

        elif label == "RA Lineups":
            df = pd.read_csv(
                path,
                sep=";",
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="warn",
                dtype={"id": "string"},
            )

            if "id" in df.columns:
                df["id"] = df["id"].astype("string")

        else:
            df = pd.read_csv(
                path,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                on_bad_lines="warn",
            )

    except UnicodeDecodeError:
        print("UTF-8 failed, retrying latin1...")

        df = pd.read_csv(
            path,
            sep=";",
            engine="python",
            encoding="latin1",
            on_bad_lines="warn",
        )

    except pd.errors.EmptyDataError:
        print(f"Skipping unreadable/empty file: {path}")
        return None

    print(f"Loaded {label}: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(df.head(3))

    return df

def main():
    print("=" * 80)
    print("BUILD EXTERNAL LINEUPS")
    print("=" * 80)

    print(f"Current file: {CURRENT_FILE}")
    print(f"Feature root: {FEATURE_ROOT}")
    print(f"Source dir: {SRC_DIR}")
    print(f"Interim dir: {INTERIM_DIR}")
    print(f"Output path: {EXTERNAL_EVENT_ARTISTS_PATH}")

    partyflock_events = read_csv_if_exists(
        PARTYFLOCK_EVENTS_PATH,
        "Partyflock Events",
    )

    partyflock_lineups = read_csv_if_exists(
        PARTYFLOCK_LINEUPS_PATH,
        "Partyflock Lineups",
    )

    ra_events = read_csv_if_exists(
        RA_EVENTS_PATH,
        "RA Events",
    )

    ra_lineups = read_csv_if_exists(
        RA_LINEUPS_PATH,
        "RA Lineups",
    )

    print("\nParsing Partyflock Events...")
    pf_events_parsed = parse_partyflock_events(partyflock_events)
    print(f"Parsed Partyflock Events rows: {len(pf_events_parsed)}")

    print("\nParsing Partyflock Lineups...")
    if partyflock_lineups is not None:
        pf_lineups_parsed = parse_partyflock_lineups(partyflock_lineups)
    else:
        pf_lineups_parsed = pd.DataFrame()
    print(f"Parsed Partyflock Lineups rows: {len(pf_lineups_parsed)}")

    print("\nParsing RA Events + RA Lineups...")
    if ra_lineups is not None:
        ra_parsed = parse_ra_events_and_lineups(ra_events, ra_lineups)
    else:
        ra_parsed = pd.DataFrame()
    print(f"Parsed RA rows: {len(ra_parsed)}")

    print("\nCombining external event-artist tables...")
    external_event_artists = combine_external_event_artists(
        pf_events_parsed,
        pf_lineups_parsed,
        ra_parsed,
    )

    print(f"Combined rows: {len(external_event_artists)}")

    if external_event_artists.empty:
        print("\nERROR: external_event_artists is empty.")
        print("This means either:")
        print("1. Input files are missing.")
        print("2. Column names do not match the parser.")
        print("3. The parser found no artist/lineup columns.")
        raise ValueError("No external event-artist rows were generated.")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    external_event_artists.to_csv(EXTERNAL_EVENT_ARTISTS_PATH, index=False)

    print("\nSaved external event-artists table.")
    print(f"Output path: {EXTERNAL_EVENT_ARTISTS_PATH}")
    print(f"Rows: {len(external_event_artists)}")
    print(f"Unique external events: {external_event_artists['external_event_id'].nunique()}")
    print(f"Unique artists: {external_event_artists['artist_name_clean'].nunique()}")

    print("\nSources:")
    print(external_event_artists["source"].value_counts(dropna=False))

    print("\nPreview:")
    print(external_event_artists.head(30))

    print("=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()