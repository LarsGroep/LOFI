"""
Ensure all artists from the provided lineup are marked candidate_status='booked'.
Parses the raw lineup text, deduplicates, cross-references DB, and bulk-updates.
"""
import io, os, sys, unicodedata, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ── Raw lineup (as provided by user) ─────────────────────────────────────────
RAW = """Nørbak
Pariah
Wata Igarashi
Rødhåd
Polygonia
Abstract Division
JEANS
Nelly
Quelza
Cobahn
Human Space Machine
Eric Cloutier
Woody92 Nelly
Woody92
Dennis Quin
Kerri Chandler
Joyhauser
MYRA
Bart Skils
Colyn Colyn
Sunil Sharpe
u.r. trax
Paula Temple
Vera Grace
Morgan
Noach
Luuk van Dijk
Running Hot
Rossi.
D Stone
Benjamin Berg
Juliana X
Christian AB
Reiss
Malika
Francesco del Garda
Ben UFO
Ae:ther
Woo York
Beswerda
8Kays
VNTM Beswerda
VNTM
Identified Patient
Celeste
Fafi Abdel Nour
Jasmín
Cinnaman
Marcel Dettmann
Casper Tielrooij
Nèna
Nala Brown
Steffi
Beau Didier
Ben Sims
Alarico
ANNĒ
Maceo Plex
Franc Fala
Boris Coelman
Spacer Woman
Merve
Kyra Khaldi
De Sluwe Vos
Laidlaw
Benny Rodrigues
Newtone
Chloé Robinson Chloé Robinson
Cormac
Curses
Daniel Monaco
Spekki Webu
Efdemin
Garçon
Feral
Shoal
Luke Slater
Jephta
Laura BCR
Loek Frey
DJ Red
DJ Maria.
Anthony Linell
Talismann Efdemin
Talismann
Cynthia Spiering
Vince
Pila
The Darkraver
Olive Anguz
Bass-D
Da Mouth of Madness
Kyle Starkey
Tjade
Jenny Cara
Essy Essy
Cybersex
X CLUB.
Slimfit
Jensen Interceptor
Lolsnake
Timo Nikson
Sansibar
Sandrien
Doudou MD
Anthony Parasole
Samuel Deep
Blasha & Allatt
CHEWCHEW
HUNEE
Aletha
Adam Pits
Verity
Satoshi
DJ Marcelle
Tammo Hesselink
Virginia
Carlos Valdes
Oceanic
Naone
Robert Bergman Carlos Valdes
Robert Bergman
Courtesy
MCR-T
Clara Cuvé
Baraka
ALCATRAZ
Mietze Conte
DJ Gigola
Pablo Bozzi
ace of demons
Mila Black Pablo Bozzi
Mila Black
Tasha
Lea Occhi
Chlär
JSPRV35
Stephanie Sykes
TAFKAMP Stephanie Sykes
TAFKAMP
Kalle Pablo
Juri Miralles
Cinema Royale
Tonno Disko
Barbara Boeing
Bibi Seck
Brass Rave Unit
Cromby
BELLA
Berkan V8
Trippy Tins
Lola Edo
DPR
Reflex Blue
cap
DJ Senc
D'Julz
Coast 2 Coast
Charmaine
Chaos in The CBD
Daiki
Moxie
Antal
Daphni
Sisi
DJ Almelo
Margie
Kamma Sisi
Kamma
I-RO
Marcal
Comrade Winston
Rosati
Chrissie
Arthur Robert
Pink Concrete Chrissie
Pink Concrete
Moxes
Emvae
Schwesta P
Baron Von Trax
YONES
Vera Moro
Hoesephine
PietNormaal
Desire
Eva Vrijdag
spikey lee
lucia lu
acidheaven
cryptofauna
Yazzus
Sarkawt Hamad
JASSS
Soft Break
Djrum
mad miran Sarkawt Hamad
mad miran
Rocinha
Mbé
Nicolas Lutz
Hannecart
Paul Lution
Craig Richards
Midland
Gabbs
Among trees
Mystral
Denver
Developer
Beatrice
Matrixxman
Aadja
Alci
Traumer
Kai King
Toman
Regularfantasy
Marie Malarie
Emmz
FAFF
Lewis Taylor
Tjade Tjade
Velasco
Ron Obvious
Fonte
D. Tiffany
Mauro Moreno
Inoz
Sugar Free
Wispelturig
Ignez
Nick Moody
Ø [Phase] Sandrien
Ø [Phase]
Diffrent
MALUGI
Helena Lauwaert
MALOU
Dangerous Dreaming
Moody Mehran
CRUSH3d
ferrari rot
Rozie
evin Moody Mehran
evin
Just Lauren
Recondite
Mathew Jonson
Patrice Baumel
Max Cooper
Nadia Struiwigh
Jasmín Nadia Struiwigh
Combined Type
Gene On Earth
Stella Zekri
Across Boundaries
Sonja Moonear
Automatic Writing
Perc
Lobster
Laura van Hal
Megan Leber
Colin Benders
Vera Logdanidi
French II
Hitam
Barker
Vardae
Olivia Mendez
Chami
NDRX
DVS1
Marco Shuttle
GiGi FM
Konduku
Andy Garvey
Nera
VRIL
JakoJako
D-Leria Nera
D-Leria
Dungeon Meat
Daniele Temperilli
Carlita
Phone Traxxx
Somewhen
Yoshiko
Bushbaby
Krampf
Flansie
Nene H
angelboy
Dissolver
Paul Seul
Yung Singh
LB aka LABAT Dissolver
LB aka LABAT
Parris
Selene
Altinbas
Dimi Angélis
Setaoc Mass
Justine Perry Selene
Justine Perry
VIL
DAX J
Thomas P. Heckmann
UVB
Umwelt
Grace Dahl
CRAVO
Chontane Dax J
Chontane
TLM Airlines TLM Airlines
DJ TOOL
mul/ANNA
Amanda Mussi
Kaiser
Yanamaste mul/ANNA
Yanamaste
Matisa
Demi Riquísimo
Tsepo
Luuk van Dijk Kyra Khaldi
DJ MELL G
Zenker Brothers
Philippa Pacho Nala Brown
Philippa Pacho
Philou Celaries
Marino Canal
Ae:ther Philou Celaries
Voigtmann
Locklead
Tommy Chikara
Julian Anthony
Reiss Reiss
Diora
Jennifer Cardini
Juicy Romance
Bauernfeind
Boys Noize
Ellen Allien
MRD
Daria Kolosova
MCR-T DJ Gigola
Ryan Elliott
Junki Inoue
Shanti Celeste
Mia Cecille
Dresden
Peach
Ogazón
PLO Man Reiss
PLO Man
Aldonna
Audrey Danza
Spray
Amaliah
Sam Alfred
Maara
Danielle Tjade
Danielle
Coco Maria
Sassy J
Kléo
DJ Kampire
Kaidi Tatham
Antal Antal
Ron Trent
Serti
Oscar Mulero
Reptant
Dj Nobu
Kia
Jane Fitz
Sybil
Clarisa Kimskii Serti
Clarisa Kimskii
Superstrings
ADIEL
P.E.A.R.L.
Carmen Electro
Héctor Oaks
Not A Headliner Héctor Oaks
Not A Headliner
Essets
Fais Le Beau
Freakenstein
DJ Killing
Mano Le Tough
Jasper Tygner
Weval
Aletha Weval
EMILIJA
DART
Speedy J
MARRØN
Najel
Mareena
Prance
Konstantin Sibold
Bart Skils Bart Skils
ISAbella
Gerd Janson
HAAi Gerd Janson
HAAi
Lin C
Surf 2 Glory
Valeby
Cincity
Lerato Tsotetsi
Philou Louzolo
Rayzir Philou Louzolo
Gabrielle Kwarteng
Quest
Helena Hauff
Harry McCanna
The Ghost
SOLIT
Flo Massé
AIDA Tjade
AIDA
Liane
Temudo
Fireground
Laure Croft Liane
Laure Croft
STERAC
ROD
KiNK
VNTM VNTM
Julian Muller
CAIVA
Bebe Bad
Swimming Paul
Priori
Stranger
Roger Gerressen
DJ Pete
Polygonia Roger Gerressen
Boris Acket
Mary Lake
Portrait XO
Enequist
Maarten Vos & Max Frimout
CARISTA
Robert Hood
Bae Blade
Victor Ruiz
Lyrae
Ollie Lishman
Sophia Violet
Miguel de Bois
Lennart
Queen Saba
Janis Zielinski
Rosa Red
Benwal
Anetha
VEL
A Strange Wedding
Mac Declos
DJ Leoni
Luna Ludmila
Kevin De Vries
Joris Voorn
Collabs 3000
Beste Hira
Move D
Ays
Danilo Plessow (MCDE)
Liam Palmer
Naomi
Elliot Schooling
Partiboi69
Loods
Maruwa
Âme
Eli Verveine
Djeff
Jaden Thompson
Adam Beyer
Maï-Linh
Julie Desire
upsammy
Agonis
Dasha Rush
Aurora Halal
Bas Dobbelaer
Na Nich
OCCA
Seb H.
Aaron J
Mella Dee
Alex Kassian
Anz
Sherelle
Byron Yeates
Bambounou
Bashkka
Hyperaktivist
Delano Legito
FJAAK
Jack Fresia
Fadi Mohem
Planetary Assault Systems
Dr Rubinstein
Orpheu The Wizard
Bella Claxton
Faster Horses
SWIM
Sex Wax
Prins Thomas
Kikiorix
Luke Una
Kamma & Masalo
Sadar Bahar
LUXE
John Talabot
Leon Vynehall
Alexia Glensy
Shoal & Vand
Storm Mollison
Inafekt
Olympe4000
Dan Shake
Essy
Leo Sanderson
Cassian
Rebuke
Hedda Stenberg
Tonco
Victoria De Angelis
Patrick Mason
Sozef
22 Interns
Hidde van Wee
Enzo Jeff
Milion
Jimi Jua
Olivia Lensen
Freddi
Uni Son
Grace Sands
Timmerman
LYLO
Laurent Garnier
Steve Rachmad
nthng
Kessler
Oberman
D.Dan
Sandwell District
Costanza
Richard Akingbehin
Bradley Zero
Jordan Brando
Elias Mazian
Jolani Jhones
Major Lazer
Kybba
LSDXOXO
Travis
Raven
IFIF
Rob Black
BIIANCO
HoneyLuv
LevyM
Syreeta
Kurashi Soundsystem
Sandor
Westside Gunn
LIL 'VIC
Tida Kamara
Varuna Agosti
TWIENA
Parrish Smith
Ben Klock
Jesse G
Adriana Lopez
Collé
BLOND:ISH
Florinsz
Papa Nugs
Laura Meester
Kaufman
Marco Faraone
S.A.M.
Jennifer Loveless
Ploy
NIKS
Dyed Soundorom
Hervé
DJ Spit
Shonky
DJ Fart in the Club
Paramida
Job de Jong
Sweely
Joya Astou
Richie Hawtin
Gyatso
Tommy Gold
dj sweet6teen
PHIA
Retromigration
Denis Sulta
TSHA
Pangaea
Moopie
Jorg Kuning (live)
Impérieux
Interpol
THC
Mordi
RONI
Match Box
Tama Sumo
Louie Vega
Lakuti
Brandfee
Xiaolin
Objekt
Sepehr
CCL
KREAM
Joy Orbison
BSS
Nick Leon
Pearson Sound
Prosumer
DJ BORING
Gabriel Muñoz
LoveFoxy
Esi
DJ Hyperdrive
DJ Shoplifter
Pegassi
Swarobski
Justin Tinderdate
Elotrance
Alexandria
Anil Aras
Chris Stussy
Fumi
Technoslave 69
ØTTA
Malindi
TINS
Rozaly
Bibtiana
Andy Martin
Donato Dozzy
Marius Bø
Paquita Gordon
Young Marco & Max Frimout
Maarten Vos
Colyn
SAMOH
Carmen Lisa
Charlotte de Witte
Mau P
Vanille
Dixon
Weska
Boris Werner
Pan-Pot
Sally C
Mall Grab
Mees Javois
Tim Reaper
Darwin
Josey Rebelle
LINSKA
Kara Okay
Paige Tomlinson
Us Two
DAF
Bontan
X-COAST
YASMIN REGISFORD
KTK
Supergloss
Honey Dijon
Skee Mask
Hysteria Temple Foundation
Jorge Fons
Timnah
Floorplan
Makam
Gizem
Antonio Ruscito & Luigi Tozzi
Andrea Oliva
Atmos Blaq
Isabel Soto
Claudio PRC
Bakio
J:Me
Benji
Marsolo
Phil de Janeiro
Roza Terenzi
Bitter Babe
D.Tiffany
Roi Perez
Mind Against
Kerrie
LazerGazer
BLANKA
Zisko
SAMA
Julia Maria
Amotik
Stojche
Karina Schneider
Function
Hot Since 82
Kim April
Ranger Trucco
Ranger Trucco
Kim April
Test Joël
Karel
DJ PAULÃO
Musclecars
Satoshi Tomiie
Giles Peterson
Marlon Hoffstadt
CVNTS
Sellout bonus Marlon
Saidah
Benny2
Agents of Time
Herr Krank
DJ Frank
Kendal
Re-Type
Brina Knauss
REZarin
CRYME
The Lady Machine
DJ Fuckoff
SALOME
PORNCEPTUAL
Lilya Mandre
KUKU
MoBlack
Laolu
Samaʼ Abdulhadi
Fiene
The Trip
Merel Helderman
Tauceti
Polar Inertia
Kangding Ray
Faustin
DJ Yazi
Beatrice M.
Luke Vibert
Monophonik
Vlada
Innersha
Garcon
oma totem
Sunju Hargun
Decoder
Trikk
Yulia Niko
Massano
Sellout
AMORAL
UFO95
Valody
Toobris
BIANKA
Norbak
SECONDS (Setaoc Mass)
SECONDS (Phara)
Roger Geressen
Oliver Huntemann
Hostingfee
Arthur Rober
Martinou
Entasia
Miamor
S3PPA
THELMA
Ryan Elliot"""

# ── Parse: one name per line, deduplicate, skip obvious non-artists ────────────
SKIP = {
    "test joël", "karel", "hostingfee", "sellout bonus marlon", "benny2",
    "cvnts", "arthur rober",  # typo of Arthur Robert
    "roger geressen",         # typo of Roger Gerressen
    "ryan elliot",            # typo of Ryan Elliott
    "norbak",                 # Nørbak (near-match already handled)
    "garcon",                 # Garçon (near-match already handled)
    "d.tiffany",              # D. Tiffany (near-match)
    "ranger trucco\nkim april", # merged cell artifact
}

lineup_names: set[str] = set()
for line in RAW.splitlines():
    name = line.strip().strip('"')
    if not name:
        continue
    if name.lower() in SKIP:
        continue
    lineup_names.add(name)

print(f"Unique lineup names after dedup: {len(lineup_names)}")

# ── Load all DB artists (paginated) ──────────────────────────────────────────
all_artists = []
offset = 0
while True:
    batch = sb.schema("tinder").table("artists").select("id, name, candidate_status").range(offset, offset + 999).execute().data or []
    all_artists.extend(batch)
    if len(batch) < 1000:
        break
    offset += 1000
print(f"Total artists in DB: {len(all_artists)}")
db_map = {r["name"].strip().lower(): r for r in all_artists}

# ── Match lineup names to DB ──────────────────────────────────────────────────
to_update   = []  # (id, name) — in DB, not booked
not_in_db   = []  # name — not found in DB at all

for name in sorted(lineup_names):
    key = name.strip().lower()
    r = db_map.get(key)
    if r:
        if r["candidate_status"] != "booked":
            to_update.append((r["id"], r["name"], r["candidate_status"]))
    else:
        not_in_db.append(name)

already_booked = len(lineup_names) - len(to_update) - len(not_in_db)
print(f"  Already booked:         {already_booked}")
print(f"  Need status update:     {len(to_update)}")
print(f"  Not found in DB:        {len(not_in_db)}")

# ── Update status to booked ───────────────────────────────────────────────────
if to_update:
    print(f"\nUpdating {len(to_update)} artists to booked...")
    updated = errors = 0
    for aid, name, old_status in to_update:
        try:
            sb.schema("tinder").table("artists").update({
                "candidate_status": "booked",
                "needs_scraping":   True,
            }).eq("id", aid).execute()
            updated += 1
            print(f"  {old_status:10} -> booked  {name}")
        except Exception as e:
            errors += 1
            print(f"  ERROR {name}: {e}")
    print(f"\nUpdated {updated} artists ({errors} errors)")

# ── Report names not in DB ────────────────────────────────────────────────────
if not_in_db:
    print(f"\nNot found in DB ({len(not_in_db)} names — many are combined-cell artifacts):")
    for n in sorted(not_in_db):
        print(f"  {n}")
