# %% [markdown]
# # LOFI Line-up Recommender v1: Historical Performance Scoring
# 
# **Objective**: Load three cleaned CSV files, validate schemas, clean columns, and compute historical performance scores for each artist.
# 
# This notebook is designed for exploration and debugging. Later iterations will convert validated logic into production scripts and Supabase uploads.

# %%
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Configure pandas display for wider inspection
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 100)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', 50)

# %% [markdown]
# ## 1. Load CSV Files

# %%
from pathlib import Path
import pandas as pd

# Notebook zit waarschijnlijk in ./lineup_recommender
notebook_dir = Path.cwd()

# Als ./data niet bestaat, probeer één niveau omhoog
if (notebook_dir / "data").exists():
    project_root = notebook_dir
elif (notebook_dir.parent / "data").exists():
    project_root = notebook_dir.parent
else:
    raise FileNotFoundError(
        f"Could not find data folder in {notebook_dir} or {notebook_dir.parent}"
    )

data_dir = project_root / "data"

ARTIST_EVENTS_PATH = data_dir / "artist_events_clean.csv"
ARTISTS_PATH = data_dir / "artists_clean.csv"
EVENTS_PATH = data_dir / "events_clean.csv"

print(f"Notebook directory: {notebook_dir}")
print(f"Project root: {project_root}")
print(f"Data directory: {data_dir}")

print(f"Artist-Events path: {ARTIST_EVENTS_PATH}")
print(f"Artists path: {ARTISTS_PATH}")
print(f"Events path: {EVENTS_PATH}")

# Check files before loading
for path in [ARTIST_EVENTS_PATH, ARTISTS_PATH, EVENTS_PATH]:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

# Load CSVs
artist_events_df = pd.read_csv(ARTIST_EVENTS_PATH)
artists_df = pd.read_csv(ARTISTS_PATH)
events_df = pd.read_csv(EVENTS_PATH)

print("\n✓ All CSV files loaded successfully.")

print("artist_events_df:", artist_events_df.shape)
print("artists_df:", artists_df.shape)
print("events_df:", events_df.shape)

# %% [markdown]
# ## 2. Schema Validation

# %%
def validate_columns(df, required_columns, table_name):
    """
    Validate that a dataframe has all required columns.
    
    Args:
        df: DataFrame to validate
        required_columns: List of column names that must exist
        table_name: Name of the table (for messaging)
    
    Raises:
        ValueError: If any required columns are missing
    """
    df_columns = set(df.columns)
    required = set(required_columns)
    
    missing = required - df_columns
    extra = df_columns - required
    
    if missing:
        print(f"❌ {table_name}: Missing columns: {missing}")
        raise ValueError(f"{table_name} is missing required columns: {missing}")
    
    if extra:
        print(f"⚠️  {table_name}: Extra columns (not required): {extra}")
    
    print(f"✓ {table_name}: Schema valid ({len(required)} required columns present)")


# Define expected columns for each table
artist_events_columns = [
    'artist_id', 'artist_name', 'event_id', 'event_name', 'event_date', 
    'genre', 'kind', 'event_type', 'event_status', 'total_visitors', 
    'actual_tickets', 'ticketing_revenue', 'bar_revenue', 'total_revenue', 
    'total_cost', 'event_result', 'artist_costs', 'occupancy_rate'
]

artists_columns = [
    'artist_id', 'artist_name', 'event_count', 'first_event_date', 'last_event_date',
    'genres', 'avg_visitors', 'avg_tickets', 'avg_event_result', 'total_event_result', 
    'avg_occupancy_rate'
]

events_columns = [
    'event_id', 'Lineup', 'Line-up (artiesten) (DB)', 'Timetable', 'event_name', 'event_date',
    'weekday', 'year', 'month', 'quarter', 'kind', 'event_type', 'event_status', 'genre',
    'visitor_capacity', 'total_visitors', 'actual_tickets', 'ticketing_revenue', 'bar_revenue',
    'total_revenue', 'total_sales', 'total_cost', 'event_result', 'artist_costs',
    'ticket_forecast', 'visitor_forecast', 'result_forecast', 'occupancy_rate',
    'ticket_forecast_error', 'visitor_forecast_error', 'result_forecast_error', 'artist_source'
]

# Validate all three tables
print("=" * 80)
print("SCHEMA VALIDATION")
print("=" * 80)
validate_columns(artist_events_df, artist_events_columns, "artist_events_df")
validate_columns(artists_df, artists_columns, "artists_df")
validate_columns(events_df, events_columns, "events_df")
print("=" * 80)

# %% [markdown]
# ## 3. Basic Inspection & Diagnostics

# %%
def inspect_dataframe(df, table_name):
    """Print comprehensive diagnostics for a dataframe."""
    print(f"\n{'=' * 80}")
    print(f"{table_name.upper()}")
    print(f"{'=' * 80}")
    
    print(f"\nShape: {df.shape}")
    
    print(f"\nFirst few rows:")
    print(df.head())
    
    print(f"\nData types:")
    print(df.dtypes)
    
    print(f"\nMissing values (%):")
    missing_pct = (df.isnull().sum() / len(df) * 100).round(2)
    missing_pct = missing_pct[missing_pct > 0].sort_values(ascending=False)
    if len(missing_pct) > 0:
        print(missing_pct)
    else:
        print("No missing values")
    
    print(f"\nDuplicated rows: {df.duplicated().sum()}")
    
    # Check for key duplicates
    if 'artist_id' in df.columns and 'event_id' not in df.columns:
        dup_artist_ids = df['artist_id'].duplicated().sum()
        print(f"Duplicated artist_id: {dup_artist_ids}")
    
    if 'event_id' in df.columns and 'artist_id' not in df.columns:
        dup_event_ids = df['event_id'].duplicated().sum()
        print(f"Duplicated event_id: {dup_event_ids}")
    
    if 'artist_id' in df.columns and 'event_id' in df.columns:
        dup_pairs = df[['artist_id', 'event_id']].duplicated().sum()
        print(f"Duplicated (artist_id, event_id) pairs: {dup_pairs}")


# Inspect all three dataframes
inspect_dataframe(artist_events_df, "artist_events_df")
inspect_dataframe(artists_df, "artists_df")
inspect_dataframe(events_df, "events_df")

# %% [markdown]
# ## 4. Cleaning Helper Functions

# %%
def clean_numeric_series(s):
    """
    Convert a series to numeric, handling currency symbols, commas, percent signs.
    
    Args:
        s: pandas Series
    
    Returns:
        pandas Series with numeric values
    """
    if s.dtype in ['int64', 'int32', 'float64', 'float32']:
        return s
    
    # Convert to string and remove common symbols
    s_str = s.astype(str)
    s_str = s_str.str.replace('€', '').str.replace('$', '')
    s_str = s_str.str.replace('%', '').str.replace(',', '.')
    s_str = s_str.str.strip()
    
    return pd.to_numeric(s_str, errors='coerce')


def clean_percentage_series(s):
    """
    Convert a series to numeric percentage, converting 0-100 to 0-1 if needed.
    
    Args:
        s: pandas Series
    
    Returns:
        pandas Series with normalized percentage values (0-1 range)
    """
    numeric_s = clean_numeric_series(s)
    
    # Check if values appear to be in 0-100 range
    non_null_values = numeric_s.dropna()
    if len(non_null_values) > 0:
        median_val = non_null_values.median()
        if median_val > 1.5:
            numeric_s = numeric_s / 100.0
    
    return numeric_s


def clean_date_series(s):
    """
    Convert a series to datetime.
    
    Args:
        s: pandas Series
    
    Returns:
        pandas Series with datetime values
    """
    return pd.to_datetime(s, errors='coerce')


def clean_string_series(s):
    """
    Strip whitespace from a string series.
    
    Args:
        s: pandas Series
    
    Returns:
        pandas Series with stripped strings
    """
    if s.dtype == 'object':
        return s.str.strip()
    return s


print("✓ Cleaning helper functions defined")

# %% [markdown]
# ## 5. Clean artist_events_df

# %%
artist_events = artist_events_df.copy()

# Clean datetime columns
artist_events['event_date'] = clean_date_series(artist_events['event_date'])

# Clean numeric columns
numeric_cols_ae = [
    'total_visitors', 'actual_tickets', 'ticketing_revenue', 'bar_revenue',
    'total_revenue', 'total_cost', 'event_result', 'artist_costs'
]
for col in numeric_cols_ae:
    artist_events[col] = clean_numeric_series(artist_events[col])

# Clean percentage column
artist_events['occupancy_rate'] = clean_percentage_series(artist_events['occupancy_rate'])

# Clean string columns (strip whitespace)
string_cols_ae = ['artist_id', 'artist_name', 'event_id', 'event_name', 'genre', 'kind', 'event_type', 'event_status']
for col in string_cols_ae:
    artist_events[col] = clean_string_series(artist_events[col])

# Drop rows where artist_id or event_id is missing
artist_events = artist_events.dropna(subset=['artist_id', 'event_id'])

print(f"artist_events shape after cleaning: {artist_events.shape}")
print(f"Rows dropped due to missing artist_id/event_id: {len(artist_events_df) - len(artist_events)}")
print("✓ artist_events cleaned")

# %% [markdown]
# ## 6. Clean artists_df

# %%
artists = artists_df.copy()

# Clean datetime columns
artists['first_event_date'] = clean_date_series(artists['first_event_date'])
artists['last_event_date'] = clean_date_series(artists['last_event_date'])

# Clean numeric columns
numeric_cols_a = [
    'event_count', 'avg_visitors', 'avg_tickets', 'avg_event_result',
    'total_event_result', 'avg_occupancy_rate'
]
for col in numeric_cols_a:
    if col in artists.columns:
        artists[col] = clean_numeric_series(artists[col])

# Handle occupancy_rate as percentage
if 'avg_occupancy_rate' in artists.columns:
    artists['avg_occupancy_rate'] = clean_percentage_series(artists['avg_occupancy_rate'])

# Clean string columns
string_cols_a = ['artist_id', 'artist_name', 'genres']
for col in string_cols_a:
    if col in artists.columns:
        artists[col] = clean_string_series(artists[col])

print(f"artists shape: {artists.shape}")
print("✓ artists cleaned")

# %% [markdown]
# ## 7. Clean events_df

# %%
events = events_df.copy()

# Clean datetime columns
events['event_date'] = clean_date_series(events['event_date'])

# Clean numeric columns (date/time related)
for col in ['year', 'month', 'quarter']:
    if col in events.columns:
        events[col] = clean_numeric_series(events[col])

# Clean financial numeric columns
numeric_cols_e = [
    'visitor_capacity', 'total_visitors', 'actual_tickets', 'ticketing_revenue',
    'bar_revenue', 'total_revenue', 'total_sales', 'total_cost', 'event_result',
    'artist_costs', 'ticket_forecast', 'visitor_forecast', 'result_forecast',
    'ticket_forecast_error', 'visitor_forecast_error', 'result_forecast_error'
]
for col in numeric_cols_e:
    if col in events.columns:
        events[col] = clean_numeric_series(events[col])

# Clean percentage column
if 'occupancy_rate' in events.columns:
    events['occupancy_rate'] = clean_percentage_series(events['occupancy_rate'])

# Clean key string columns (but keep lineup/timetable/artist_source dirty for later parsing)
key_string_cols = ['event_id', 'event_name', 'weekday', 'kind', 'event_type', 'event_status', 'genre']
for col in key_string_cols:
    if col in events.columns:
        events[col] = clean_string_series(events[col])

print(f"events shape: {events.shape}")
print("✓ events cleaned")

# %% [markdown]
# ## 8. Base Performance Features

# %%
# Create derived performance metrics, handling division by zero safely

# Revenue per visitor
artist_events['revenue_per_visitor'] = np.where(
    artist_events['total_visitors'] > 0,
    artist_events['total_revenue'] / artist_events['total_visitors'],
    np.nan
)

# Ticket revenue per visitor
artist_events['ticket_revenue_per_visitor'] = np.where(
    artist_events['total_visitors'] > 0,
    artist_events['ticketing_revenue'] / artist_events['total_visitors'],
    np.nan
)

# Bar revenue per visitor
artist_events['bar_revenue_per_visitor'] = np.where(
    artist_events['total_visitors'] > 0,
    artist_events['bar_revenue'] / artist_events['total_visitors'],
    np.nan
)

# Profit margin
artist_events['profit_margin'] = np.where(
    artist_events['total_revenue'] > 0,
    artist_events['event_result'] / artist_events['total_revenue'],
    np.nan
)

# Cost ratio
artist_events['cost_ratio'] = np.where(
    artist_events['total_revenue'] > 0,
    artist_events['total_cost'] / artist_events['total_revenue'],
    np.nan
)

# Artist cost ratio
artist_events['artist_cost_ratio'] = np.where(
    artist_events['total_revenue'] > 0,
    artist_events['artist_costs'] / artist_events['total_revenue'],
    np.nan
)

print("✓ Base performance features created")

# %% [markdown]
# ## 9. Recency Features

# %%
# Use max event_date as reference point
reference_date = artist_events['event_date'].max()
print(f"Reference date: {reference_date}")

# Calculate months since event
artist_events['months_since_event'] = np.where(
    artist_events['event_date'].notna(),
    (reference_date - artist_events['event_date']).dt.days / 30.44,
    np.nan
)

# Calculate recency weight: exponential decay over 24 months
# exp(-0) = 1.0 (most recent)
# exp(-1.0) ≈ 0.37 (24 months ago)
artist_events['recency_weight'] = np.exp(-artist_events['months_since_event'] / 24)

print(f"Recency weight range: {artist_events['recency_weight'].min():.3f} to {artist_events['recency_weight'].max():.3f}")
print("✓ Recency features created")

# %% [markdown]
# ## 10. Percentile Scoring Functions

# %%
def compute_percentile_score(s, higher_is_better=True):
    """
    Convert a series to percentile scores (0-100).
    
    Args:
        s: pandas Series with numeric values
        higher_is_better: if True, higher values get higher scores; if False, lower is better
    
    Returns:
        pandas Series with percentile scores (0-100)
    """
    if higher_is_better:
        # rank in ascending order, so higher values get higher percentiles
        return s.rank(pct=True, na_option='keep') * 100
    else:
        # rank in descending order, so lower values get higher percentiles
        return (1 - s.rank(pct=True, na_option='keep')) * 100


# Create global percentile scores for key metrics
artist_events['occupancy_score'] = compute_percentile_score(artist_events['occupancy_rate'], higher_is_better=True)
artist_events['event_result_score'] = compute_percentile_score(artist_events['event_result'], higher_is_better=True)
artist_events['revenue_per_visitor_score'] = compute_percentile_score(artist_events['revenue_per_visitor'], higher_is_better=True)
artist_events['profit_margin_score'] = compute_percentile_score(artist_events['profit_margin'], higher_is_better=True)

print("✓ Percentile scores computed")
print(f"Occupancy score (non-null): {artist_events['occupancy_score'].notna().sum()}")
print(f"Event result score (non-null): {artist_events['event_result_score'].notna().sum()}")
print(f"Revenue per visitor score (non-null): {artist_events['revenue_per_visitor_score'].notna().sum()}")
print(f"Profit margin score (non-null): {artist_events['profit_margin_score'].notna().sum()}")

# %% [markdown]
# ## 11. Historical Event Score

# %%
# Combine component scores into historical event score
# Weighted combination: occupancy, profit margin, revenue per visitor, event result
artist_events['historical_event_score'] = (
    0.30 * artist_events['occupancy_score']
    + 0.25 * artist_events['profit_margin_score']
    + 0.20 * artist_events['revenue_per_visitor_score']
    + 0.15 * artist_events['event_result_score']
)

# Create recency-weighted version
artist_events['weighted_historical_event_score'] = (
    artist_events['historical_event_score'] * artist_events['recency_weight']
)

print(f"Historical event score range: {artist_events['historical_event_score'].min():.2f} to {artist_events['historical_event_score'].max():.2f}")
print(f"Weighted historical event score range: {artist_events['weighted_historical_event_score'].min():.2f} to {artist_events['weighted_historical_event_score'].max():.2f}")
print("✓ Historical event scores created")

# %% [markdown]
# ## 12. Aggregate to Artist Level

# %%
# Aggregate event-level data to artist level
artist_agg = artist_events.groupby(['artist_id', 'artist_name']).agg({
    'event_id': 'nunique',
    'event_date': ['min', 'max'],
    'genre': lambda x: ', '.join(x.dropna().unique()),
    'occupancy_rate': 'mean',
    'total_visitors': 'mean',
    'actual_tickets': 'mean',
    'ticketing_revenue': 'mean',
    'bar_revenue': 'mean',
    'total_revenue': 'mean',
    'total_cost': 'mean',
    'event_result': 'mean',
    'artist_costs': 'mean',
    'revenue_per_visitor': 'mean',
    'profit_margin': 'mean',
    'historical_event_score': 'mean',
    'weighted_historical_event_score': 'sum',
    'recency_weight': 'sum',
}).reset_index()

# Flatten column names
artist_agg.columns = [
    'artist_id', 'artist_name', 'event_count', 'first_event_date', 'last_event_date',
    'genres', 'avg_occupancy_rate', 'avg_total_visitors', 'avg_actual_tickets',
    'avg_ticketing_revenue', 'avg_bar_revenue', 'avg_total_revenue', 'avg_total_cost',
    'avg_event_result', 'avg_artist_costs', 'avg_revenue_per_visitor', 'avg_profit_margin',
    'avg_historical_event_score', 'sum_weighted_score', 'sum_recency_weight'
]

# Calculate recency-weighted average: sum(weighted_score) / sum(recency_weight)
artist_agg['recency_weighted_score'] = np.where(
    artist_agg['sum_recency_weight'] > 0,
    artist_agg['sum_weighted_score'] / artist_agg['sum_recency_weight'],
    np.nan
)

# Clean up temporary columns
artist_agg = artist_agg.drop(columns=['sum_weighted_score', 'sum_recency_weight'])

print(f"Aggregated to {len(artist_agg)} unique artists")
print("✓ Artist-level aggregation complete")

# %% [markdown]
# ## 13. Reliability and Confidence Scores

# %%
# Reliability score based on event count
max_event_count = artist_agg['event_count'].max()
artist_agg['reliability_score'] = (
    np.log1p(artist_agg['event_count']) / np.log1p(max_event_count) * 100
).round(2)

# Data completeness: percentage of non-null values across key performance columns
key_performance_cols = ['avg_occupancy_rate', 'avg_total_revenue', 'avg_event_result', 
                        'avg_total_visitors', 'avg_artist_costs']
artist_agg['data_completeness'] = (
    artist_agg[key_performance_cols].notna().sum(axis=1) / len(key_performance_cols) * 100
).round(2)

# Recency confidence based on months since last event
artist_agg['months_since_last_event'] = (
    (reference_date - artist_agg['last_event_date']).dt.days / 30.44
)
artist_agg['recency_confidence'] = (
    np.exp(-artist_agg['months_since_last_event'] / 24) * 100
).round(2)

# Combined confidence score
artist_agg['confidence_score'] = (
    0.50 * np.minimum(artist_agg['event_count'] / 5, 1) * 100
    + 0.25 * artist_agg['data_completeness']
    + 0.25 * artist_agg['recency_confidence']
).round(2)

print("✓ Reliability and confidence scores computed")
print(f"Reliability score range: {artist_agg['reliability_score'].min():.2f} to {artist_agg['reliability_score'].max():.2f}")
print(f"Confidence score range: {artist_agg['confidence_score'].min():.2f} to {artist_agg['confidence_score'].max():.2f}")

# %% [markdown]
# ## 14. Final Historical LOFI Score

# %%
# Compute historical LOFI score with fallback logic
def compute_historical_lofi_score(row):
    """
    Compute final historical LOFI score with weighted average and fallback.
    
    Primary: 0.85 * recency_weighted_score + 0.15 * reliability_score
    Fallback (if recency_weighted_score is NaN): 0.85 * avg_historical_event_score + 0.15 * reliability_score
    """
    if pd.notna(row['recency_weighted_score']):
        score = 0.85 * row['recency_weighted_score'] + 0.15 * row['reliability_score']
    else:
        score = 0.85 * row['avg_historical_event_score'] + 0.15 * row['reliability_score']
    
    return round(score, 2) if pd.notna(score) else np.nan


artist_agg['historical_lofi_score'] = artist_agg.apply(compute_historical_lofi_score, axis=1)

print(f"Historical LOFI score range: {artist_agg['historical_lofi_score'].min():.2f} to {artist_agg['historical_lofi_score'].max():.2f}")
print(f"Artists with valid scores: {artist_agg['historical_lofi_score'].notna().sum()}")
print("✓ Final historical LOFI scores computed")

# %% [markdown]
# ## 15. Score Explanation Generator

# %%
def generate_score_explanation(row):
    """
    Generate a human-readable explanation of the artist's score.
    """
    score = row['historical_lofi_score']
    confidence = row['confidence_score']
    event_count = row['event_count']
    occupancy = row['avg_occupancy_rate']
    profit_margin = row['avg_profit_margin']
    
    # Handle NaN scores
    if pd.isna(score):
        return "Insufficient data for scoring."
    
    # Low confidence
    if confidence < 40:
        return "Low confidence: limited or incomplete LOFI history."
    
    # Single event
    if event_count == 1:
        return "Single LOFI appearance, interpret carefully."
    
    # Strong performer
    if score >= 75 and confidence >= 60:
        if pd.notna(occupancy) and pd.notna(profit_margin):
            if occupancy > 70 and profit_margin > 0:
                return "Strong historical LOFI performance with solid confidence."
            elif occupancy > 70 and profit_margin <= 0:
                return "Strong attendance signal, but weaker profitability."
        return "Strong historical LOFI performance with solid confidence."
    
    # Moderate performer
    if score >= 50:
        return "Moderate historical LOFI performance based on available event data."
    
    # Weak performer
    return "Limited historical LOFI performance. Could indicate newer or inconsistent events."


artist_agg['score_explanation'] = artist_agg.apply(generate_score_explanation, axis=1)

print("✓ Score explanations generated")
print(artist_agg['score_explanation'].value_counts())

# %% [markdown]
# ## 16. Build Final Output Table

# %%
# Create final output dataframe with selected columns in desired order
artist_historical_performance_scores = artist_agg[[
    'artist_id',
    'artist_name',
    'event_count',
    'first_event_date',
    'last_event_date',
    'genres',
    'avg_occupancy_rate',
    'avg_total_visitors',
    'avg_actual_tickets',
    'avg_ticketing_revenue',
    'avg_bar_revenue',
    'avg_total_revenue',
    'avg_total_cost',
    'avg_event_result',
    'avg_artist_costs',
    'avg_revenue_per_visitor',
    'avg_profit_margin',
    'reliability_score',
    'data_completeness',
    'recency_confidence',
    'confidence_score',
    'historical_lofi_score',
    'score_explanation',
]].copy()

# Sort by historical_lofi_score descending
artist_historical_performance_scores = artist_historical_performance_scores.sort_values(
    'historical_lofi_score', ascending=False, na_position='last'
).reset_index(drop=True)

print(f"Final output table shape: {artist_historical_performance_scores.shape}")
print("\nFirst 10 artists (highest scores):")
print(artist_historical_performance_scores.head(10))

# %%



