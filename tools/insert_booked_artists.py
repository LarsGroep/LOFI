"""
Insert missing booked artists into tinder.artists and flag them for scraping.
Also updates near-matches (diacritic variants already in DB) to status=booked.
Also bulk-updates all artists from the lineup that already exist in DB to status=booked.
"""
import os, re, io, sys, unicodedata
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ── 1. Artists to INSERT (genuinely not in DB, deduplicated, corrected) ──────
# "TLM  Airlines" was one artist split by the parser — merged back.
# "Ryan Elliot" (typo) deduped to "Ryan Elliott".
# "TAFKAMP" deduped to "Tafkamp".
# "Airlines" and "TLM" (parser artefacts) replaced with "TLM Airlines".
# "Norbak" = Nørbak (already in DB) → excluded, handled in near-matches below.
# Rob Black, Vanille, YONES confirmed as separate artists from the fuzzy hits.

NEW_BOOKED = [
    "Rebuke",
    "Recondite",
    "Reflex Blue",
    "Regularfantasy",
    "Reiss",
    "Reptant",
    "Retromigration",
    "REZarin",
    "Richard Akingbehin",
    "Richie Hawtin",
    "Rob Black",
    "Robert Bergman",
    "Robert Hood",
    "Rocinha",
    "ROD",
    "Roger Gerressen",
    "Roi Perez",
    "Ron Obvious",
    "Ron Trent",
    "RONI",
    "Rosa Red",
    "Rosati",
    "Rossi.",
    "Roza Terenzi",
    "Rozaly",
    "Rozie",
    "Running Hot",
    "Ryan Elliott",
    "Rødhåd",
    "S.A.M.",
    "S3PPA",
    "Sadar Bahar",
    "Sally C",
    "SALOME",
    "Sam Alfred",
    "SAMA",
    "Samaʼ Abdulhadi",
    "SAMOH",
    "Samuel Deep",
    "Sandor",
    "Sandrien",
    "Sandwell District",
    "Sansibar",
    "Sarkawt Hamad",
    "Sassy J",
    "Satoshi",
    "Satoshi Tomiie",
    "Schwesta P",
    "Seb H.",
    "SECONDS (Phara)",
    "SECONDS (Setaoc Mass)",
    "Selene",
    "Sepehr",
    "Serti",
    "Setaoc Mass",
    "Sex Wax",
    "Shanti",
    "Shanti Celeste",
    "Sherelle",
    "Shoal",
    "Shoal & Vand",
    "Shonky",
    "Sisi",
    "Skee Mask",
    "Soft Break",
    "SOLIT",
    "Somewhen",
    "Sonja Moonear",
    "Sophia Violet",
    "Sozef",
    "Spacer Woman",
    "Speedy J",
    "Spekki Webu",
    "spikey lee",
    "Spray",
    "Steffi",
    "Stella Zekri",
    "Stephanie Sykes",
    "STERAC",
    "Steve Rachmad",
    "Stojche",
    "Storm Mollison",
    "Stranger",
    "Sugar Free",
    "Sunil Sharpe",
    "Sunju Hargun",
    "Supergloss",
    "Surf 2 Glory",
    "Swarobski",
    "Sweely",
    "SWIM",
    "Sybil",
    "Syreeta",
    "Tafkamp",
    "Talismann",
    "Tama Sumo",
    "Tammo Hesselink",
    "Tasha",
    "Tauceti",
    "Technoslave 69",
    "Temudo",
    "THC",
    "The Darkraver",
    "The Ghost",
    "The Lady Machine",
    "The Trip",
    "Thomas P. Heckmann",
    "Tida Kamara",
    "Tim Reaper",
    "Timmerman",
    "Timnah",
    "Timo Nikson",
    "TINS",
    "Tjade",
    "TLM Airlines",
    "Toman",
    "Tommy Chikara",
    "Tommy Gold",
    "Tonco",
    "Tonno Disko",
    "Toobris",
    "Traumer",
    "Travis",
    "Trikk",
    "Trippy Tins",
    "Tsepo",
    "TSHA",
    "TWIENA",
    "u.r. trax",
    "UFO95",
    "Umwelt",
    "Uni Son",
    "upsammy",
    "Us Two",
    "UVB",
    "Valeby",
    "Valody",
    "Vanille",
    "Vardae",
    "Varuna Agosti",
    "VEL",
    "Velasco",
    "Vera Grace",
    "Vera Logdanidi",
    "Vera Moro",
    "Verity",
    "Victor Ruiz",
    "Victoria De Angelis",
    "VIL",
    "Vince",
    "Virginia",
    "Vlada",
    "VNTM",
    "Voigtmann",
    "VRIL",
    "Wata Igarashi",
    "Weska",
    "Westside Gunn",
    "Weval",
    "Wispelturig",
    "Woo York",
    "Woody92",
    "X CLUB.",
    "X-COAST",
    "Xiaolin",
    "Yanamaste",
    "YASMIN REGISFORD",
    "Yazzus",
    "YONES",
    "Yoshiko",
    "Young Marco & Max Frimout",
    "Yulia Niko",
    "Yung Singh",
    "Zenker Brothers",
    "Zisko",
    "Âme",
]

# ── 2. Near-matches: already in DB under ASCII-stripped name, just mark booked ─
# UUIDs from the cross-reference output.
NEAR_MATCH_IDS = [
    "d6c58b5c-0239-4bf4-8d9c-6b90a433e89e",  # Chloe Robinson → Chloé Robinson
    "79e91708-3aa7-4547-9c09-0f70b4bf733e",  # Chlar → Chlär
    "77f79927-7cb6-4c6b-8285-c01387ccca2e",  # Clara Cuve → Clara Cuvé
    "0af886d1-eddb-42d0-9d5d-252b8c7f2733",  # Colle → Collé
    "be50051e-26cf-411b-b510-928ef808306f",  # D.Tiffany → D. Tiffany
    "553908ca-52e9-4346-8d6c-9fe7634db995",  # Demi Riquisimo → Demi Riquísimo
    "e184ed4d-6266-4caa-80e3-2f6f769c1c72",  # Dimi Angelis → Dimi Angélis
    "48f4fc22-6859-4bd3-ab16-9c3d122ff48b",  # Flo Masse → Flo Massé
    "77fa66bb-3191-4888-bdbc-e6e69ec1a203",  # Gabriel Munoz → Gabriel Muñoz
    "4f6b7fc2-4c95-4f8b-8649-c333358eea4a",  # Garcon → Garçon
    "9c08a5c5-df9b-4048-9b43-3090f0e809d5",  # Herve → Hervé
    "6b08b2c7-4731-49fd-8e8d-392e30e6d928",  # Hector Oaks → Héctor Oaks
    "7f2208a6-1d40-4c37-bd67-31433caf2b43",  # Jasmin → Jasmín
    "9e0a3b79-15a5-4672-bd20-db691bd17635",  # Kleo → Kléo
    "7969f2bd-80fc-419c-a154-50b49529254f",  # LIL VIC → LIL 'VIC
    "9288a7d5-141e-4e49-aa92-d2e9a1feb91e",  # Mai-Linh → Maï-Linh
    "f4eb110f-4cc0-417b-b873-6a305e59c2cc",  # Norbak → Nørbak
]

# ── Slug helper ───────────────────────────────────────────────────────────────
def _make_slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    n = n.encode("ascii", "ignore").decode("ascii")
    n = re.sub(r"[^\w\s-]", "", n).strip().lower()
    return re.sub(r"[\s_-]+", "-", n)

def _unique_slug(base: str) -> str:
    slug = base
    existing = {r["slug"] for r in (sb.schema("tinder").table("artists").select("slug").execute().data or [])}
    i = 2
    while slug in existing:
        slug = f"{base}-{i}"
        i += 1
    return slug

# ── Load current DB names for dedup check ────────────────────────────────────
existing = sb.schema("tinder").table("artists").select("id, name, candidate_status").execute().data or []
existing_lower = {r["name"].strip().lower(): r for r in existing}

# ── Step 1: INSERT new artists ────────────────────────────────────────────────
inserted = 0
skipped = 0
for name in NEW_BOOKED:
    key = name.strip().lower()
    if key in existing_lower:
        skipped += 1
        print(f"  SKIP (already exists): {name}")
        continue
    slug = _unique_slug(_make_slug(name))
    row = {
        "name": name,
        "slug": slug,
        "candidate_status": "booked",
        "needs_scraping": True,
    }
    try:
        sb.schema("tinder").table("artists").insert(row).execute()
        inserted += 1
        print(f"  INSERT: {name}")
    except Exception as e:
        print(f"  ERROR inserting {name}: {e}")

print(f"\nInserted {inserted} new artists ({skipped} already existed)")

# ── Step 2: Mark near-match records as booked ─────────────────────────────────
near_updated = 0
for uid in NEAR_MATCH_IDS:
    try:
        sb.schema("tinder").table("artists") \
            .update({"candidate_status": "booked"}) \
            .eq("id", uid).execute()
        near_updated += 1
    except Exception as e:
        print(f"  ERROR updating {uid}: {e}")
print(f"Updated {near_updated} near-match records to booked")

# ── Step 3: Bulk-update all lineup artists already in DB to booked ────────────
# These are the 454 pending + 3 accepted that matched exactly by name.
# Load them from the original cross-reference list.
LINEUP_NAMES_FILE = "check_booked_output.txt"
lineup_found_names = set()
for line in open(LINEUP_NAMES_FILE, encoding="utf-8"):
    if "  YES  " in line:
        parts = line.strip().split("[")
        name = parts[0].replace("YES", "").strip()
        lineup_found_names.add(name.lower())

bulk_updated = 0
for r in existing:
    if r["name"].strip().lower() in lineup_found_names and r.get("candidate_status") != "booked":
        try:
            sb.schema("tinder").table("artists") \
                .update({"candidate_status": "booked"}) \
                .eq("id", r["id"]).execute()
            bulk_updated += 1
        except Exception as e:
            print(f"  ERROR bulk-updating {r['name']}: {e}")
print(f"Bulk-updated {bulk_updated} existing artists to booked status")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print(f"New artists inserted:       {inserted}")
print(f"Near-matches marked booked: {near_updated}")
print(f"Existing updated to booked: {bulk_updated}")
print(f"Total affected:             {inserted + near_updated + bulk_updated}")
print()
print("Next: run scrape_flagged.py to scrape the new artists.")
