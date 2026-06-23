import pandas as pd

from config import ARTIST_EVENTS_PATH, ARTISTS_PATH, EVENTS_PATH


def load_lofi_data():
    for path in [ARTIST_EVENTS_PATH, ARTISTS_PATH, EVENTS_PATH]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required input file: {path}")

    artist_events = pd.read_csv(ARTIST_EVENTS_PATH)
    artists = pd.read_csv(ARTISTS_PATH)
    events = pd.read_csv(EVENTS_PATH)

    print(f"Loaded artist_events: {artist_events.shape}")
    print(f"Loaded artists: {artists.shape}")
    print(f"Loaded events: {events.shape}")

    return artist_events, artists, events