from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

def h1(text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.color.rgb = RGBColor(0x6B, 0x21, 0xA8)
    return p

def h2(text):
    return doc.add_heading(text, level=2)

def body(text):
    p = doc.add_paragraph(text)
    p.runs[0].font.size = Pt(10.5)
    return p

def bullet(text):
    p = doc.add_paragraph(text, style="List Bullet")
    p.runs[0].font.size = Pt(10.5)
    return p

def caption(text):
    p = doc.add_paragraph(text)
    p.runs[0].font.size = Pt(9)
    p.runs[0].font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
    return p

# TITLE
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run("LOFI Artist Intelligence Platform")
run.bold = True
run.font.size = Pt(20)
run.font.color.rgb = RGBColor(0x6B, 0x21, 0xA8)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub.add_run("Samenvatting voor intern gebruik  |  Juni 2026  |  Repository: LarsGroep/LOFI").font.size = Pt(9)

doc.add_paragraph()

# 1
h1("1. Wat doet het systeem?")
body("Het LOFI Artist Intelligence Platform is een intern data- en dashboard-systeem dat twee vragen beantwoordt:")
bullet("Wie moeten we nu al in de gaten houden? -- opkomende artiesten herkennen 6-18 maanden voor de rest van de markt.")
bullet("Kan deze artiest tickets verkopen in Amsterdam? -- data-onderbouwing voor boekingsbeslissingen.")
body(
    "Kernprincipe: groeiversnelling telt zwaarder dan absolute grootte. "
    "Een artiest die van 50k naar 80k Spotify-luisteraars groeide in 3 maanden is interessanter "
    "dan iemand die al jaren op 500k staat maar niet beweegt."
)
doc.add_paragraph()

# 2
h1("2. Databronnen")

h2("Altijd beschikbaar (912 artiesten)")
bullet("Chartmetric -- Spotify-luisteraars, Instagram- en TikTok-volgers, groeipercentages (30/90/180 dagen), groeiversnelling, genre-tags, CPP-score, editorial playlists, top tracks.")
bullet("Partyflock -- Nederlandse eventgeschiedenis en fanbase. Primair signaal voor Amsterdam-vraag.")
bullet("Last.fm -- genre-tags, luisteraantallen, vergelijkbare artiesten. Basis voor de Genre Trends pagina.")
bullet("Resident Advisor -- eventgeschiedenis (venue, stad, land, capaciteit, headliner). 632 van de 912 artiesten hebben RA-data.")

h2("Live detectie (automatisch)")
bullet("YouTube Monitor (elke 30 min) -- detecteert sets op Boiler Room, H.O.R. Berlin, Mixmag, The Lot Radio, Rinse FM, Book Club Radio en BE-AT.TV.")
bullet("Beatport Charts (elke 6 uur) -- top 100 in Techno, Tech House, Melodic, Afro House en Organic House.")
bullet("RA Podcast (dagelijks) -- detecteert eerste RA Podcast-aflevering per artiest.")
bullet("BBC Essential Mix (wekelijks) -- detecteert eerste Essential Mix per artiest.")

h2("Gedeeltelijk beschikbaar")
bullet("NL publiek % (Instagram/TikTok country breakdown) -- beschikbaar voor 282 van de 912 artiesten.")
bullet("Uitgebreide Chartmetric-data (playlists, tracks, Shazam, demographics) -- 282/912 artiesten.")

h2("Nog niet geautomatiseerd")
bullet("Agency-vertegenwoordiging -- geen publieke API. Wordt handmatig ingevuld via het dashboard.")
bullet("LOFI intern kaartverkoop -- wordt in een latere fase gekoppeld.")
doc.add_paragraph()

# 3
h1("3. Scores")
body("Elke artiest krijgt vijf scores (0-100), iedere nacht herberekend:")

h2("De vijf scores")
bullet("Momentum -- groeit de buzz nu? (Spotify 30d, cross-platform, trending sets)")
bullet("Groei -- gaat de groei omhoog? (groeiversnelling weegt 50%)")
bullet("Marktpositie -- hoe groot is de artiest nu? (CM-rank, CPP-score, Spotify-luisteraars)")
bullet("Potentieel -- waar gaat dit naartoe? (groeiversnelling + CPP-trend + ML-voorspelling)")
bullet("Data -- hoeveel data hebben we? (hoe meer platforms ingevuld, hoe hoger de betrouwbaarheid)")

h2("Booking Signalen -- drie composiet-signalen")
bullet("GROEI SIGNAAL (40%) -- XGBoost ML-model voorspelt de CPP-groei in de komende 90 dagen.")
bullet("SCENE SIGNAAL (35%) -- combinatie van validatie-events (Ibiza, Awakenings, RA Podcast, BBC), NL-score en RA-eventgeschiedenis.")
bullet("LOFI FIT (25%) -- past de sound bij LOFI-programmering (dark techno, driving, melodic, organic, minimal)?")
caption("De Booking Signalen staan bovenaan elk artiestprofiel, direct na de header.")
doc.add_paragraph()

# 4
h1("4. Het dashboard")
body("Start met: streamlit run lofi_pipeline.py  (in de lofi-tinder/ map)  |  http://localhost:8501")

h2("Pagina 1: Overzicht")
body("De hoofdpagina. Alle artiesten als compact kaartjes-raster (6 kolommen).")
bullet("Kaartjes tonen: foto, naam, statusbadge, RA-events, Spotify 90d groei, XGBoost-voorspelling.")
bullet("Filter op status, genre en loopbaanfase. Zoek op naam.")
bullet("Klik een kaartje om het volledige artiestprofiel uit te klappen.")

h2("Artiestprofiel (uitklapbaar)")
bullet("Header -- foto, genres, stad, label, booking agent, social links.")
bullet("Scores + Booking Signalen -- vijf scores en drie composiet-signalen.")
bullet("NL / Amsterdam signaal -- NL-percentage uit Instagram/TikTok country breakdown.")
bullet("Groeimetrieken + grafieken -- Spotify 30d/90d/180d %, groeiversnelling, per-platform lijngrafieken.")
bullet("Shows -- RA-eventhistorie (filter NL/Ibiza/headliner), Partyflock NL-events, externe events.")
bullet("Mijlpalen -- eerste Ibiza, eerste headline 500+, RA Podcast, BBC Essential Mix etc.")
bullet("Vergelijkbare artiesten -- Last.fm similar + Chartmetric related.")

h2("Pagina 2: Groei Leaderboard")
body("Gesorteerde tabel: wie beweegt er nu het hardst? Alle vijf scores, Spotify 30d %, XGBoost-voorspelling.")

h2("Pagina 3: Genre Trends")
body("Welke genres groeien in artiestenaantal en gemiddeld luisteraarsvolume? Klik een genre om alle bijbehorende artiesten met scores te zien.")

h2("Pagina 4: Artiest Recommender")
body("Geef een artiest op -- het systeem vindt vergelijkbare artiesten op basis van feature-vectors (FAISS) en RA co-lineup data (wie staat er vaker samen op de poster?).")
doc.add_paragraph()

# 5
h1("5. Automatisering")
bullet("Elke 30 min -- YouTube Monitor: trending sets detecteren.")
bullet("Elke 6 uur -- Beatport Charts: top 100 in 5 genres bijwerken.")
bullet("Dagelijks -- RA Podcast checken + vijf scores herberekenen voor alle 912 artiesten.")
bullet("Wekelijks (zondag) -- BBC Essential Mix detecteren.")
bullet("Op aanvraag -- Chartmetric backfill, XGBoost model retraining, nieuwe artiesten toevoegen.")
body("Draait via GitHub Actions. Vereiste secrets: SUPABASE_URL, SUPABASE_KEY, YOUTUBE_API_KEY, CM_REFRESH_TOKEN.")
doc.add_paragraph()

# 6
h1("6. Nieuwe artiest toevoegen")
bullet("Stap 1 -- Zoek het Chartmetric artist ID op via chartmetric.com.")
bullet("Stap 2 -- Voer uit: python tools/insert_booked_artists.py met het Chartmetric ID.")
bullet("Stap 3 -- Stel candidate_status in (watching / hot / emerging) en vul metadata in (label, booking agent, stad).")
bullet("Stap 4 -- Trigger backfill_booked.yml in GitHub Actions.")
bullet("Stap 5 -- Artiest verschijnt bij de volgende herlaad. Scores worden nachtelijk berekend, RA-events de volgende ochtend.")
body("De discovery_queue toont artiesten gevonden in trending YouTube-content of Beatport-charts die nog niet in de database staan.")
doc.add_paragraph()

# 7
h1("7. Bekende datahiaten")
bullet("NL publiek % -- beschikbaar voor 282/912 artiesten. Dashboard toont melding als het ontbreekt.")
bullet("Agency-vertegenwoordiging -- geen API. Handmatige invoer. Hoge prioriteit: agency-tier is een sterke leading indicator.")
bullet("Fan cities (Chartmetric) -- kolom bestaat maar is leeg voor alle artiesten. Nog niet gevuld door Chartmetric.")
bullet("F2F TV YouTube -- channel ID ontbreekt nog, wordt geskipt door de YouTube Monitor.")
bullet("LOFI intern kaartverkoop -- nog niet gekoppeld. Gepland voor latere fase.")
doc.add_paragraph()

footer = doc.add_paragraph()
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer.add_run("LOFI Artist Intelligence Platform  |  LarsGroep/LOFI  |  Juni 2026").font.size = Pt(8)

doc.save(r"C:\Users\larsv\Desktop\LOFI repo NL samenvatting.docx")
print("Saved.")
