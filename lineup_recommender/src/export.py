from config import PROCESSED_DIR


def save_processed(df, path):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)