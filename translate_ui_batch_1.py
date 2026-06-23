from pathlib import Path

APP_PATH = Path("lofi_pipeline.py")

if not APP_PATH.exists():
    raise FileNotFoundError("Could not find lofi_pipeline.py. Run this script from the project root.")

text = APP_PATH.read_text(encoding="utf-8")

replacements = {
    # Sidebar / general
    "Vernieuwen": "Refresh",
    "Artiest toevoegen": "Add artist",
    "Naam": "Name",
    "Artiestnaam…": "Artist name...",
    "Scraper status": "Scraper status",
    "Laatste scrape": "Last scrape",
    "In wachtrij": "In queue",
    "Uitgebreid": "Extended",
    "RA events": "RA events",

    # Overview navigation and filters
    "Overzicht": "Overview",
    "Groei Leaderboard": "Growth Leaderboard",
    "Sorteren": "Sort",
    "Score (hoog→laag)": "Score high to low",
    "Groei 90d ↓": "90d growth ↓",
    "Groei 30d ↓": "30d growth ↓",
    "A → Z": "A to Z",
    "Alle": "All",
    "Kandidaat": "Candidate",
    "Geboekt": "Booked",
    "Artiesten": "Artists",
    "Gevolgd": "Tracked",

    # Search / artist profile basics
    "Zoek artiest...": "Search artist...",
    "Zoek artiest": "Search artist",
    "Typ een artiestnaam hierboven om te beginnen.": "Type an artist name above to start.",
    "Geen artiestdata beschikbaar.": "No artist data available.",
    "Geen data beschikbaar.": "No data available.",
    "Geen artiest gevonden": "No artist found",
    "Geen artiest genaamd": "No artist named",
    "gevonden in de database.": "found in the database.",
    "Selecteer": "Select",
    "Selecteer artiest": "Select artist",
    "Weergave": "Showing",
    "Artiest niet gevonden?": "Artist not found?",
    "Voeg": "Add",
    "toe als nieuw": "as new",
    "Toevoegen & scrapen": "Add and scrape",
    "Kandidaatstatus instellen": "Set candidate status",

    # Header metrics
    "CM Rang": "CM Rank",
    "SP Luisteraars": "SP Listeners",

    # Main artist sections
    "Scores": "Scores",
    "Booking Signalen": "Booking Signals",
    "Signaal breakdown": "Signal breakdown",
    "Groei": "Growth",
    "Platformen": "Platforms",
    "Shows": "Shows",
    "Mijlpalen": "Milestones",
    "Vergelijkbare artiesten": "Similar artists",
    "Nummers & Playlists": "Tracks & Playlists",
    "Nummers": "Tracks",
    "Naam": "Name",
    "Uitgebracht": "Released",
    "Afspeellijsten": "Playlists",
    "Geen playlist plaatsingen.": "No playlist placements.",
    "Nog geen nummers gevonden.": "No tracks found yet.",

    # NL / Amsterdam section
    "NL / Amsterdam Publiek": "NL / Amsterdam Audience",
    "Ams. events": "Amsterdam events",
    "NL events totaal": "Total NL events",
    "Social demographics niet beschikbaar": "Social demographics unavailable",
    "NL-score gebaseerd op venue-aanwezigheid": "NL score based on venue presence",

    # Booking labels
    "Boeken": "Book",
    "Veelbelovend": "Promising",
    "Twijfelachtig": "Uncertain",
    "Niet aanbevolen": "Not recommended",
    "composiet": "composite",
    "Groei (XGB)": "Growth (XGB)",
    "Scene": "Scene",
    "LOFI Fit": "LOFI Fit",
    "geen data": "no data",
    "Lage data-betrouwbaarheid": "Low data reliability",

    # Growth forecast
    "Wat verwachten we?": "What do we expect?",
    "Model opnieuw trainen": "Retrain model",
    "Model trainen": "Train model",
    "Herbereken voorspelling": "Recalculate prediction",
    "Voorspelling herberekenen...": "Recalculating prediction...",
    "Nieuwe voorspelling": "New prediction",
    "Nog geen model getraind.": "No model has been trained yet.",
    "Verwachte CPP groei (90 dagen)": "Expected CPP growth (90 days)",
    "Modelonzekerheid (±)": "Model uncertainty (±)",
    "Positie in database": "Position in database",
    "Beter dan": "Better than",
    "Wat drijft deze voorspelling": "What drives this prediction",

    # Genre pages
    "Welke genres groeien?": "Which genres are growing?",
    "Genres gevolgd": "Tracked genres",
    "Stijgend": "Rising",
    "Stabiel": "Stable",
    "Dalend": "Declining",
    "Genre momentum": "Genre momentum",
    "Snelst groeiend": "Fastest growing",
    "Grootste genres": "Largest genres",
    "Inzoomen op een genre": "Drill down into a genre",
    "Kies een genre": "Choose a genre",
    "Alle genres": "All genres",
    "Groei (%)": "Growth (%)",
    "% Groeiend": "% growing",
    "Gem. Luisteraars": "Avg. listeners",

    # YouTube page
    "Kanaal": "Channel",
    "Zoek op titel of artiest": "Search by title or artist",
    "Totaal views": "Total views",
    "Trending nu": "Trending now",
    "Bekende artiesten": "Known artists",
    "Geen sets gevonden.": "No sets found.",

    # Feedback
    "Label / Feedback Toevoegen": "Add label / feedback",
    "Label opslaan": "Save label",
    "Bestaande labels": "Existing labels",
}

changed = 0
for old, new in replacements.items():
    if old in text:
        count = text.count(old)
        text = text.replace(old, new)
        changed += count

backup = APP_PATH.with_suffix(".py.bak_translate_batch_1")
backup.write_text(APP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
APP_PATH.write_text(text, encoding="utf-8")

print(f"Done. Replaced {changed} occurrences.")
print(f"Backup written to: {backup}")
