# LOFI Line-up Recommender

## Purpose

This feature is part of the larger LOFI Artist Intelligence project.

The goal of the Line-up Recommender is to help LOFI programmers explore artist suggestions based on:

1. Historical LOFI artist performance
2. Artists that have played together in LOFI line-ups
3. External scene validation from sources such as Resident Advisor and Partyflock
4. Eventually: user-selected artist context, genre, event type, budget, and confidence filters

This is not meant to be a fully autonomous booking system. It is a decision-support feature for programmers.

The intended interaction is:

```text
User selects an artist
        ↓
System recommends artists that may fit well in the same line-up
        ↓
Recommendation is explained using historical LOFI data and external scene data
```

Example:

```text
Selected artist: Rossi.
Recommended:
- Traumer
- Luuk van Dijk
- Noach
- Similar/co-occurring artists from external line-up data
```

The system should always show *why* an artist is recommended.

---

## Current Status

The feature currently has three working building blocks.

### 1. Historical LOFI Performance Score

Script:

```bash
python scripts/build_historical_scores.py
```

Output:

```text
data/processed/artist_historical_performance_scores.csv
```

This table ranks artists based on historical LOFI event performance.

Main output columns:

```text
artist_id
artist_name
event_count
genres
avg_occupancy_rate
avg_total_visitors
avg_event_result
avg_artist_costs
reliability_score
confidence_score
historical_lofi_score
score_explanation
```

This score is not a causal proof that an artist sold tickets by themselves. It is an interpretable proxy for historical LOFI fit and performance.

Important interpretation:

```text
historical_lofi_score = how strongly the artist is associated with good LOFI event outcomes
confidence_score = how much we trust that signal
```

A high score with low confidence should be treated carefully.

---

### 2. Parsed LOFI Line-ups

Script:

```bash
python scripts/build_lineup_tables.py
```

Output:

```text
data/interim/parsed_event_lineups.csv
```

This parses the `artist_source` column from `events_clean.csv` into one row per event-artist combination.

Target columns:

```text
event_id
event_name
event_date
genre
kind
event_type
artist_name_raw
artist_name_clean
source_column
position_in_lineup
```

This table is used to understand which artists appeared in the same LOFI line-up.

---

### 3. LOFI Artist Co-occurrence

Script:

```bash
python scripts/build_cooccurrence.py
```

Outputs:

```text
data/interim/parsed_event_lineups_with_artist_ids.csv
data/interim/event_artists.csv
data/processed/lofi_artist_cooccurrence.csv
```

The co-occurrence table contains artist pairs that appeared together in LOFI events.

Main output columns:

```text
artist_id_a
artist_name_a
artist_id_b
artist_name_b
cooccur_count
first_played_together
last_played_together
events_together
avg_total_visitors_together
avg_event_result_together
avg_occupancy_rate_together
```

This table allows us to answer:

```text
Which artists historically appeared together?
Which combinations were associated with strong LOFI events?
```

---

## Important Current Issue: Artist Aliases

The current co-occurrence output shows some duplicate alias problems, for example:

```text
HUNEE / Hunee
NewTone / Newtone
Francesco Del Garda / Francesco del Garda
```

This causes fake pairings where an artist appears to co-occur with themselves.

Next step before recommender logic:

```text
Fix artist name normalization and alias handling.
```

Suggested fixes:

1. Normalize all artist names to lowercase.
2. Strip extra spaces.
3. Remove duplicate artist aliases within the same event.
4. Add manual alias mapping later for difficult cases.

Example alias table:

```text
raw_name,canonical_name
HUNEE,Hunee
NewTone,Newtone
Francesco del Garda,Francesco Del Garda
KI/KI,KI/KI
KIKI,KI/KI
```

Eventually this can become:

```text
data/manual/artist_aliases.csv
```

---

## Folder Structure

Current recommended structure:

```text
lineup_recommender/
│
├── data/
│   ├── lofi/
│   │   ├── artist_events_clean.csv
│   │   ├── artists_clean.csv
│   │   └── events_clean.csv
│   │
│   ├── external/
│   │   ├── resident_advisor_lineups.csv
│   │   └── partyflock_lineups.csv
│   │
│   ├── manual/
│   │   └── artist_aliases.csv
│   │
│   ├── interim/
│   │   ├── parsed_event_lineups.csv
│   │   ├── parsed_event_lineups_with_artist_ids.csv
│   │   └── event_artists.csv
│   │
│   └── processed/
│       ├── artist_historical_performance_scores.csv
│       ├── lofi_artist_cooccurrence.csv
│       ├── external_artist_cooccurrence.csv
│       └── lineup_recommendation_candidates.csv
│
├── notebooks/
│   └── experiments.ipynb
│
├── scripts/
│   ├── build_historical_scores.py
│   ├── build_lineup_tables.py
│   ├── build_cooccurrence.py
│   ├── build_external_cooccurrence.py
│   └── build_recommendation_candidates.py
│
└── src/
    ├── __init__.py
    ├── config.py
    ├── load_data.py
    ├── clean_data.py
    ├── performance_scoring.py
    ├── lineup_parsing.py
    ├── cooccurrence.py
    ├── external_lineups.py
    ├── recommendation.py
    └── export.py
```

---

## How the Final Feature Should Work

The feature should not just output a global ranking.

The actual recommender should work like this:

```text
Input:
- selected_artist_name or selected_artist_id
- optional genre filter
- optional event_type filter
- optional minimum confidence
- optional include_external_data flag

Output:
Ranked recommended artists
```

Example:

```text
recommend_artists_for("Rossi.")
```

Should return artists based on:

1. Artists that played with Rossi. at LOFI
2. Artists that appear in similar external line-ups
3. Artists with strong historical LOFI performance
4. Artists with enough confidence
5. Artists in a similar genre or event context

---

## Recommended Scoring Formula

For a selected anchor artist, each candidate artist can receive a recommendation score.

Suggested first formula:

```text
recommendation_score =
    0.35 * lofi_cooccurrence_score
  + 0.30 * historical_lofi_score
  + 0.20 * external_scene_score
  + 0.10 * genre_match_score
  + 0.05 * confidence_score
```

Where:

```text
lofi_cooccurrence_score =
    how often candidate appeared with selected artist at LOFI
    plus how well those shared events performed

historical_lofi_score =
    candidate's general LOFI performance score

external_scene_score =
    how often candidate appears near the selected artist in external line-ups
    from Resident Advisor / Partyflock

genre_match_score =
    whether candidate shares genre/event context

confidence_score =
    reliability of candidate's LOFI data
```

Important:

External line-up data has no sales data, so it should not be treated as performance data.

External data should be used as:

```text
scene validation
similarity signal
ecosystem signal
```

Not as:

```text
proof that an artist sells tickets
```

---

## External Data Plan

We have external line-up data from sources such as:

```text
Resident Advisor
Partyflock
```

This data likely contains:

```text
event_name
event_date
venue
city
country
lineup artists
source
```

External data should be transformed into the same basic format as LOFI parsed line-ups:

```text
external_event_id
source
event_name
event_date
venue
city
country
artist_name_raw
artist_name_clean
position_in_lineup
```

Then build an external co-occurrence table:

```text
artist_name_a
artist_name_b
external_cooccur_count
sources_together
venues_together
cities_together
first_seen_together
last_seen_together
```

This allows the recommender to answer:

```text
Which artists appear in the same wider scene as the selected artist?
```

Example:

```text
Selected artist: PAWSA
External data may show repeated co-occurrence with other tech-house artists
from RA/Partyflock line-ups.
```

This becomes an external scene signal.

---

## Next Immediate Tasks

### Task 1: Fix alias handling in LOFI co-occurrence

Problem:

```text
HUNEE and Hunee appear as separate artists.
```

Action:

1. Add stronger artist name normalization.
2. Remove duplicate normalized artists within the same event.
3. Optionally create `data/manual/artist_aliases.csv`.

Goal:

```text
No artist should be paired with itself under different casing.
```

Test:

```python
import pandas as pd

df = pd.read_csv("data/processed/lofi_artist_cooccurrence.csv")

bad = df[
    df["artist_name_a"].str.lower().str.strip()
    == df["artist_name_b"].str.lower().str.strip()
]

print(bad)
```

Expected:

```text
Empty DataFrame
```

---

### Task 2: Build first recommender function

Create:

```text
src/recommendation.py
```

Start with this function:

```python
def recommend_artists_for_artist(
    selected_artist_name,
    historical_scores,
    lofi_cooccurrence,
    min_confidence=40,
    top_n=20,
):
    ...
```

First version should:

1. Find all co-occurrence pairs containing selected artist.
2. Convert the pair table into candidate artists.
3. Merge candidate artists with historical performance scores.
4. Calculate simple recommendation score.
5. Return top candidates.

First formula:

```text
recommendation_score =
    0.50 * cooccurrence_strength
  + 0.35 * historical_lofi_score
  + 0.15 * confidence_score
```

This first version does not need external data yet.

Expected output columns:

```text
selected_artist
candidate_artist
cooccur_count
historical_lofi_score
confidence_score
avg_event_result_together
avg_occupancy_rate_together
recommendation_score
recommendation_reason
```

---

### Task 3: Create recommender script

Create:

```text
scripts/test_recommend_artist.py
```

Example usage:

```bash
python scripts/test_recommend_artist.py "Rossi."
```

Expected terminal output:

```text
Top recommendations for Rossi.:

1. Traumer
2. Luuk van Dijk
3. Noach
...
```

This confirms the feature works before building a UI.

---

### Task 4: Add external line-up parser

Create:

```text
src/external_lineups.py
scripts/build_external_cooccurrence.py
```

Goal:

```text
Resident Advisor / Partyflock raw data
        ↓
standardized external event-artist table
        ↓
external_artist_cooccurrence.csv
```

External output:

```text
data/processed/external_artist_cooccurrence.csv
```

Suggested columns:

```text
artist_name_a
artist_name_b
external_cooccur_count
source_count
sources_together
venues_together
cities_together
first_seen_together
last_seen_together
```

---

### Task 5: Combine LOFI and external recommendation signals

Once external co-occurrence exists, update the recommender formula:

```text
recommendation_score =
    0.35 * lofi_cooccurrence_score
  + 0.30 * historical_lofi_score
  + 0.20 * external_scene_score
  + 0.10 * genre_match_score
  + 0.05 * confidence_score
```

The recommender should explain each recommendation.

Example:

```text
Recommended because:
- Played with selected artist 2 times at LOFI
- Shared events had high occupancy
- Candidate has strong historical LOFI score
- Also appears in external RA/Partyflock line-ups with similar artists
```

---

## Short-Term Deliverable

The next short-term deliverable should be:

```text
Given one selected artist, return a ranked recommendation table.
```

Input:

```text
selected_artist = "Rossi."
```

Output:

```text
candidate_artist
recommendation_score
cooccur_count
historical_lofi_score
confidence_score
recommendation_reason
```

This can first be a terminal script or notebook cell. It does not need Streamlit yet.

---

## Later Supabase Tables

Eventually the processed CSVs can become Supabase tables:

```text
artist_historical_performance_scores
lofi_artist_cooccurrence
external_artist_cooccurrence
lineup_recommendation_candidates
artist_aliases
```

The app can then query Supabase directly.

Example app logic:

```text
User selects artist
        ↓
Query co-occurrence table
        ↓
Merge with historical score table
        ↓
Add external scene validation
        ↓
Return ranked recommendation list
```

---

## Current Commands

Run these in order from:

```text
lineup_recommender/scripts
```

### Build historical artist scores

```bash
python build_historical_scores.py
```

Creates:

```text
data/processed/artist_historical_performance_scores.csv
```

### Build parsed LOFI line-ups

```bash
python build_lineup_tables.py
```

Creates:

```text
data/interim/parsed_event_lineups.csv
```

### Build LOFI co-occurrence

```bash
python build_cooccurrence.py
```

Creates:

```text
data/processed/lofi_artist_cooccurrence.csv
```

---

## Notes

The current system is intentionally simple.

Do not add machine learning yet.

The useful first recommender is based on interpretable signals:

```text
historical LOFI performance
co-occurrence with selected artist
external scene proximity
confidence
```

This is enough for a first version.

Do not claim that the system predicts the objectively best artist.

Claim:

```text
The system recommends artists based on historical LOFI fit, previous line-up context, and external scene proximity.
```

That framing is defensible and useful.
