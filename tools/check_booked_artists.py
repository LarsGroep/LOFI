"""
Cross-reference LOFI booked artist names against tinder.artists in Supabase.
Outputs: which names are found, which are missing, and fuzzy near-matches for misses.
"""
import os, re, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ── Raw lineup data: extract all names from both columns ─────────────────────
RAW = """
Nørbak,Pariah,Wata Igarashi,Rødhåd,Polygonia,Abstract Division,JEANS,Nelly,Quelza,Cobahn,Human Space Machine,Eric Cloutier,Woody92    Nelly,Rødhåd,Abstract Division,Eric Cloutier,Wata Igarashi,JEANS,Nørbak,Quelza,Woody92,Polygonia,Cobahn,Pariah,Human Space Machine
Makèz,Dennis Quin,Kerri Chandler
Joyhauser,MYRA,Bart Skils    MYRA,Bart Skils,Joyhauser
Colyn    Colyn
Sunil Sharpe,u.r. trax,Paula Temple ,Vera Grace    u.r. trax,Paula Temple ,Vera Grace,Sunil Sharpe
Traumer,Morgan ,Noach,Luuk van Dijk ,Running Hot,Rossi.,D Stone ,Benjamin Berg,Juliana X
Alexia Glensy,Christian AB,Reiss,Malika,Francesco del Garda,Ben UFO
Ae:ther,Woo York ,Beswerda,8Kays,VNTM    Beswerda,Ae:ther,8Kays,Woo York ,VNTM
Shanti,Identified Patient,Celeste,Fafi Abdel Nour,Jasmín,Cinnaman,Marcel Dettmann,Casper Tielrooij,Nèna,Nala Brown
Tasha,Steffi,Beau Didier,Ben Sims,Alarico,ANNĒ
Cubicolor,Maceo Plex,Franc Fala
Alex Kassian,Boris Coelman,Spacer Woman,Merve,Kyra Khaldi
De Sluwe Vos,Laidlaw,Benny Rodrigues,Newtone ,Chloé Robinson    Chloé Robinson,De Sluwe Vos,Benny Rodrigues,Laidlaw,Newtone
Budino,Cormac,Curses,Daniel Monaco
Spekki Webu,Efdemin,Garçon,Feral,Shoal,Luke Slater,Jephta,Laura BCR,Loek Frey,DJ Red,DJ Maria.,Anthony Linell,Talismann    Efdemin,Talismann,DJ Red,Anthony Linell,Luke Slater,Shoal,Laura BCR,Garçon,Loek Frey,Jephta,DJ Maria.,Spekki Webu,Feral
Luna,Cynthia Spiering,Vince,Pila,The Darkraver,Olive Anguz,Bass-D,Da Mouth of Madness
Kyle Starkey,Tjade,Jenny Cara,Essy    Essy,Kyle Starkey,Jenny Cara,Tjade
Cybersex,X CLUB.,Slimfit ,Jensen Interceptor,Lolsnake    Cybersex,Lolsnake,X CLUB.,Jensen Interceptor
Ryan Elliott,Timo Nikson,Sansibar,Sandrien,Doudou MD,Anthony Parasole,Samuel Deep,Blasha & Allatt
CHEWCHEW,HUNEE,Aletha,Adam Pits ,Verity,Satoshi,DJ Marcelle,Tammo Hesselink,Virginia,Carlos Valdes,Oceanic,Naone ,Robert Bergman    Carlos Valdes,Virginia,Adam Pits ,Naone ,Aletha,Oceanic,Tammo Hesselink,Verity,HUNEE,DJ Marcelle,CHEWCHEW,Satoshi,Robert Bergman
Courtesy,MCR-T,Clara Cuvé,Baraka,ALCATRAZ,Mietze Conte ,DJ Gigola ,Pablo Bozzi ,ace of demons,Mila Black    Pablo Bozzi ,DJ Gigola ,Baraka,Mila Black,ace of demons,Mietze Conte ,Courtesy,MCR-T,ALCATRAZ,Clara Cuvé
Tasha,Lea Occhi,Chlär,JSPRV35,Stephanie Sykes,TAFKAMP    Stephanie Sykes,Lea Occhi,Chlär,Tasha,TAFKAMP,JSPRV35
Kalle Pablo,Juri Miralles,Cinema Royale,Tonno Disko,Barbara Boeing,Bibi Seck,Brass Rave Unit,Juliana X,Boris Coelman,Cromby,BELLA,Berkan V8,Trippy Tins,Lola Edo
Doudou MD,DPR,Reflex Blue,cap,DJ Senc,D'Julz,Samuel Deep,Christian AB,Coast 2 Coast
Charmaine,Chaos in The CBD,Daiki,Moxie,Antal,Daphni,Sisi,DJ Almelo,Margie,Kamma    Sisi,Moxie,Daphni,Daiki,DJ Almelo,Charmaine,Margie,Kamma,Chaos in The CBD,Antal
I-RO,Marcal,Comrade Winston,Rosati,Chrissie,Arthur Robert,Pink Concrete    Chrissie,I-RO,Pink Concrete,Comrade Winston,Rosati,Arthur Robert,Marcal
Moxes,Emvae,Schwesta P,Baron Von Trax,YONES,Vera Moro,Hoesephine,PietNormaal,Desire
JEANS,Eva Vrijdag,spikey lee,lucia lu,acidheaven,cryptofauna,Yazzus    acidheaven,Eva Vrijdag,lucia lu,Yazzus,spikey lee,cryptofauna,JEANS
Sarkawt Hamad,JASSS,Soft Break ,Djrum,mad miran    Sarkawt Hamad,Soft Break ,mad miran,Djrum,JASSS
DJ K,Rocinha,Mbé
Laurine,Nicolas Lutz,Hannecart,Paul Lution,Craig Richards,Midland,Gabbs,Among trees
Nacho,Mystral,Denver,Developer,Beatrice,Matrixxman,Aadja
Mateo Dufour,Alci,Traumer,Kai King,Toman
Regularfantasy,Marie Malarie ,Emmz,FAFF,Lewis Taylor,Tjade    Tjade,Lewis Taylor,Regularfantasy,FAFF,Marie Malarie ,Emmz
Carlos Valdes,Velasco,Cinnaman,Ron Obvious,Fonte,D. Tiffany,Samuel Deep,Mauro Moreno,Inoz,Sugar Free
Wispelturig,Ignez,Nick Moody,Sandrien,Ø [Phase]    Sandrien,Nick Moody,Ø [Phase],Ignez,Wispelturig
Diffrent,MALUGI,Helena Lauwaert,MALOU,Dangerous Dreaming,Moody Mehran,CRUSH3d,ferrari rot,Rozie,Spacer Woman,evin    Moody Mehran,evin,Helena Lauwaert,CRUSH3d,Dangerous Dreaming,Malugi,Rozie,Spacer Woman,ferrari rot,Diffrent,MALOU
Just Lauren,Recondite,VNTM,Mathew Jonson    Recondite,VNTM,Mathew Jonson,Patrice Baumel,Just Lauren
Max Cooper,Nadia Struiwigh,Jasmín    Nadia Struiwigh,Jasmín,Max Cooper
Moopie,Combined Type ,Hannecart,Gene On Earth,cap,Reiss,Stella Zekri,Across Boundaries,Sonja Moonear,Noach,Automatic Writing
Perc,Lobster,Laura van Hal,Megan Leber,Colin Benders     Colin Benders ,Perc,Lobster,Laura van Hal,Megan Leber
Vera Logdanidi,French II,Hitam,Barker,Vardae,Olivia Mendez,Chami,NDRX,DVS1,Marco Shuttle,GiGi FM,Konduku,Andy Garvey,Nera,VRIL,Tammo Hesselink,JakoJako,D-Leria    Nera,D-Leria,DVS1,JakoJako,Tammo Hesselink,Barker,Konduku,Andy Garvey,French II,Hitam,Vardae,Vera Logdanidi,Marco Shuttle,VRIL,GiGi FM,Chami,Olivia Mendez,NDRX
Georgia,Dungeon Meat,Doudou MD,Samuel Deep,Daniele Temperilli,Carlita,Phone Traxxx,DJ Senc
Somewhen,Yoshiko,Bushbaby,Krampf,DJ Gigola ,Flansie,Nene H,angelboy,Dissolver,Paul Seul,Yung Singh,LB aka LABAT    Dissolver,LB aka LABAT,Yoshiko,Bushbaby,DJ Gigola ,Somewhen,Flansie,Nene H,Yung Singh,angelboy,Krampf,Paul Seul
Alex Kassian,Fafi Abdel Nour,Parris
Selene,Altinbas,Dimi Angélis,Setaoc Mass,Justine Perry    Selene,Dimi Angélis,Altinbas,Justine Perry,Setaoc Mass
VIL,Stephanie Sykes,DAX J,Thomas P. Heckmann,UVB,Umwelt,Grace Dahl,CRAVO,Chontane    Dax J ,Chontane,UVB,Stephanie Sykes,Grace Dahl,Thomas P. Heckmann,Umwelt,VIL,CRAVO
TLM  Airlines
DJ TOOL,mul/ANNA,Amanda Mussi,Kaiser,Yanamaste    mul/ANNA,Amanda Mussi,Kaiser,Yanamaste,DJ TOOL
Matisa ,Demi Riquísimo,Laidlaw,Kyra Khaldi ,Tsepo,Luuk van Dijk     Kyra Khaldi ,Demi Riquísimo,Tsepo,Luuk van Dijk ,Laidlaw,Matisa
DJ MELL G,Zenker Brothers,Woody92,Nala Brown,Philippa Pacho    Nala Brown,Zenker Brothers,Philippa Pacho,Woody92,DJ MELL G
VNTM,Philou Celaries,Marino Canal,Ae:ther    Philou Celaries,Marino Canal,VNTM,Ae:ther
Voigtmann,Locklead,Noach,Carlos Valdes,Tommy Chikara,Julian Anthony,Reiss    Reiss,Noach,Tommy Chikara,Locklead,Carlos Valdes,Julian Anthony,Voigtmann
Diora,Slimfit ,Jennifer Cardini,Juicy Romance,Bauernfeind ,Boys Noize,Ellen Allien ,Courtesy,ALCATRAZ,MRD,Daria Kolosova ,DJ Gigola ,MCR-T    DJ Gigola ,MCR-T,MRD,Jennifer Cardini,Boys Noize,Bauernfeind ,Slimfit ,Courtesy,ALCATRAZ,Juicy Romance,Ellen Allien ,Diora,Daria Kolosova
Ryan Elliott,Junki Inoue,Reiss,Shanti Celeste,Mia Cecille,Gabbs,Dresden,Peach,Ogazón ,PLO Man    Reiss,Peach,Ryan Elliott,Shanti Celeste,Ogazón ,PLO Man,Gabbs,Junki Inoue,Mia Cecille,Dresden
Aldonna,Audrey Danza,Spray ,Berkan V8,Amaliah,Sam Alfred,Maara,Tjade,Danielle    Tjade,Maara,Aldonna,Sam Alfred,Spray ,Berkan V8,Audrey Danza,Danielle,Amaliah
Coco Maria,Sassy J,Kléo,DJ Kampire,Kaidi Tatham ,Antal    Antal,Ron Trent,Kléo,Sassy J,Coco Maria,Kaidi Tatham ,Daniel Monaco
Serti,Oscar Mulero,Quelza,Reptant,Marco Shuttle,Dj Nobu,Garçon,Kia,Nelly,Jane Fitz,Sybil,Clarisa Kimskii    Serti,Clarisa Kimskii,Quelza,Dj Nobu,Oscar Mulero,Marco Shuttle,Jane Fitz,Nelly,Kia,Reptant,Garçon,Sybil
ADIEL,P.E.A.R.L.,Carmen Electro,Héctor Oaks,Not A Headliner    Héctor Oaks,ADIEL,Carmen Electro,P.E.A.R.L.,Not A Headliner
Morgan ,Essets,Moxes,Berkan V8,Fais Le Beau,Moody Mehran,Freakenstein,DJ Killing
Mano Le Tough,Jasper Tygner,Weval,Aletha    Weval,Mano Le Tough,Jasper Tygner,Aletha
EMILIJA,Rozie,Dangerous Dreaming,Newtone ,DART
Speedy J,Lea Occhi,MARRØN,Najel,Mareena,Prance    Speedy J,MARRØN,Mareena,Najel,Prance,Lea Occhi
Konstantin Sibold,Bart Skils    Bart Skils,Konstantin Sibold
ISAbella,Gerd Janson,Oceanic,HAAi    Gerd Janson,ISAbella,HAAi,Oceanic
Eva Vrijdag,Lin C,Surf 2 Glory ,Valeby,Spacer Woman,Helena Lauwaert
Cincity,Lerato Tsotetsi,Philou Louzolo,Rayzir    Philou Louzolo,Cincity
Craig Richards,Peach,Gabrielle Kwarteng,Christian AB,Quest,Carlita,Francesco del Garda,Helena Hauff,Carlos Valdes,Naone ,Harry McCanna,Doudou MD,The Ghost,Samuel Deep,Reiss
Jennifer Cardini
Tjade,SOLIT,Flo Massé,AIDA    Tjade,Flo Massé,AIDA,SOLIT
Liane,Temudo,Matrixxman,Fireground,Alarico,Laure Croft    Liane,Fireground,Alarico,Matrixxman,Temudo,Laure Croft
HUNEE,Antal    Antal,HUNEE
STERAC ,ROD,Megan Leber,KiNK,VNTM    VNTM,KiNK,STERAC ,ROD,Megan Leber
Loek Frey,Shoal,Ogazón ,Spekki Webu,Priori,Stranger,Philippa Pacho,Roger Gerressen,DJ Pete,DJ Red,Djrum,Polygonia    Roger Gerressen,DJ Pete,Ogazón ,Stranger,Philippa Pacho,Spekki Webu,DJ Red,Priori,Loek Frey,Shoal,Polygonia,Djrum
Colin Benders ,Boris Acket
Mary Lake,Portrait XO
Oceanic,Sandrien,Enequist
Maarten Vos & Max Frimout,Polygonia
Samuel Deep,CARISTA,Robert Hood
Juicy Romance,Schwesta P,Superstrings,Bae Blade
Bart Skils,Victor Ruiz
Lyrae ,Moxes,Ollie Lishman,Sophia Violet ,Miguel de Bois,Lennart,Queen Saba,Janis Zielinski  ,Rosa Red,Benwal
JEANS,Anetha ,VEL,A Strange Wedding,Mac Declos,DJ Leoni
Luna Ludmila,Kevin De Vries
Joris Voorn
Collabs 3000,Beste Hira
Move D,Margie,Ays,Danilo Plessow (MCDE)
Liam Palmer,Luuk van Dijk ,Naomi,Benjamin Berg,Elliot Schooling
CARISTA
Partiboi69,Moxes,Loods,Maruwa
VNTM,Âme,Eli Verveine
Djeff,Philou Louzolo,Jaden Thompson
Bart Skils,Adam Beyer
Maï-Linh,Newtone ,Tjade,Julie Desire
upsammy,Vera Logdanidi,Agonis,Dasha Rush,Aurora Halal,Bas Dobbelaer,DVS1,Oscar Mulero,Na Nich,OCCA,Seb H.,Aaron J
Mella Dee,Noach,Luuk van Dijk ,Morgan ,Alex Kassian,Locklead
Anz,Moxie,Sherelle,Chaos in The CBD,D Stone ,Byron Yeates,Bambounou,Bashkka,Courtesy,Naone ,Doudou MD
Cobahn,Quelza,Hyperaktivist,Nene H,Delano Legito ,FJAAK,Jack Fresia,Fadi Mohem,Comrade Winston,I-RO,Planetary Assault Systems,Dr Rubinstein,Lobster
Orpheu The Wizard,Parris,Kyra Khaldi ,Daphni,Berkan V8
Superstrings,Bella Claxton,Faster Horses,CRUSH3d,SWIM ,Sex Wax
HUNEE,Prins Thomas
Kikiorix,Daiki,Luke Una,Kamma & Masalo,Sadar Bahar ,Ays,Antal,Gerd Janson
LUXE,John Talabot,Weval,Leon Vynehall,Alexia Glensy
VNTM,Mano Le Tough,Recondite
Steffi,Shoal & Vand,Efdemin,Eric Cloutier
Tjade,Storm Mollison,Inafekt,MALOU,Spacer Woman,Olympe4000,Dan Shake ,Essy,Leo Sanderson
Cassian,Rebuke,Hedda Stenberg,Tonco,VNTM
Victoria De Angelis,angelboy,Cybersex,Daria Kolosova ,Patrick Mason
Benny Rodrigues,Emvae,Sozef,22 Interns,Hidde van Wee,Enzo Jeff,Milion,Jimi Jua
Rozie,Olivia Lensen,Freddi,Moody Mehran
BELLA,Uni Son,Grace Sands,Timmerman,LYLO
Laurent Garnier,Steve Rachmad,Naone
Jane Fitz,Garçon,Talismann,nthng,Andy Garvey,Kessler,Oberman,Reptant,D.Dan,Konduku,Sandwell District,Costanza,JakoJako,Woody92,Eric Cloutier,Richard Akingbehin,Human Space Machine,Pariah
Bradley Zero,Jordan Brando,Luuk van Dijk ,Bibi Seck,Elias Mazian
Jolani Jhones,Major Lazer,Kybba
LSDXOXO,Travis,Raven,bebe bad,IFIF,Tsepo,Rob Black,Lola Edo,BIIANCO
HoneyLuv,LevyM,Syreeta,Philou Louzolo
Kurashi Soundsystem ,Sandor,Westside Gunn,LIL 'VIC,Tida Kamara
Varuna Agosti,TWIENA,Parrish Smith,Ben Klock,DJ Pete,Hitam,Rosati,Mareena,Jesse G,Altinbas,Adriana Lopez,Amanda Mussi,Abstract Division
Cincity,Collé,BLOND:ISH
Florinsz,Reiss,Papa Nugs,Moxes,Emvae,Laura Meester
Kaufman,Marco Faraone,S.A.M.,Bart Skils
Jennifer Loveless ,Ploy,NIKS,Dyed Soundorom,Hervé,Anz,DJ Spit,Shonky,Kyra Khaldi ,Elias Mazian ,Doudou MD,DJ Fart in the Club
Noach,Paramida,Tommy Chikara,Job de Jong,Sweely
Polygonia,Joya Astou,Prance,JEANS,Richie Hawtin,Olivia Mendez,MARRØN
Gyatso,Tommy Gold,Richie Hawtin,Ignez,u.r. trax
dj sweet6teen,D Stone ,PHIA,Luuk van Dijk ,Tsepo,Julian Anthony,Storm Mollison,Retromigration,Denis Sulta ,TSHA
mad miran,Christian AB,Pangaea,Amaliah,Ploy,Moopie,Naone ,Jorg Kuning (live),Impérieux,Ben UFO
Interpol,THC,DART,Kyle Starkey,Bae Blade,Mordi,RONI,Match Box
Antal,Tama Sumo ,Louie Vega,HUNEE,Lakuti,Coco Maria
Rødhåd,Serti,Xiaolin,Wata Igarashi,Sarkawt Hamad,DJ Red,Dj Nobu,GiGi FM,Objekt,Sepehr,Priori,CCL
KREAM
VNTM
Efdemin,Jasmín,Nene H,Colin Benders ,Quelza
Joy Orbison ,CARISTA,BSS,Nick Leon
Kléo,Richard Akingbehin,Marcel Dettmann,Pearson Sound,Peach,Prosumer,Antal
DJ BORING,Gabriel Muñoz,LoveFoxy,Esi,Milion,Faster Horses
DJ Hyperdrive,Eva Vrijdag,VEL,DJ Shoplifter,Pegassi ,Swarobski,Justin Tinderdate,Elotrance
Alexandria,Hidde van Wee,Anil Aras,Chris Stussy
HUNEE,Antal
Daria Kolosova ,Fumi,Technoslave 69,Lolsnake,ØTTA,BIIANCO
Bambounou,Malindi,Tsepo,Boris Coelman,Gabrielle Kwarteng,TINS,Rozaly,Cormac,Bibtiana
Aaron J,Andy Martin,Donato Dozzy,Nelly,Marius Bø,Oceanic,Paquita Gordon,Sandrien,Marco Shuttle
Young Marco & Max Frimout,VRIL
JakoJako,Maarten Vos
Shoal,Dasha Rush,Spekki Webu
Collé,Colyn
SAMOH,Carmen Lisa,Charlotte de Witte,Selene
Mau P
Héctor Oaks,Vanille,Patrick Mason,Prance
Tsepo,Dixon
Weska,Bart Skils,Boris Werner,Pan-Pot
Bradley Zero,Kyra Khaldi ,Berkan V8,Sally C
Mall Grab,Mees Javois,Lola Edo
Tim Reaper,GiGi FM,Pariah,Darwin,DJ Pete
Richie Hawtin,DVS1,Josey Rebelle,Samuel Deep
LINSKA,Kevin De Vries
Kara Okay,Paige Tomlinson,Julie Desire,Tjade
Philou Louzolo,Us Two,DAF,Bontan
Bae Blade,X-COAST,YASMIN REGISFORD,EMILIJA,Essy,KTK,Supergloss
Honey Dijon,Carlos Valdes
mad miran,Skee Mask,Luna Ludmila,Efdemin,Hysteria Temple Foundation ,Oscar Mulero,Polygonia,Jorge Fons,Altinbas,Timnah
Floorplan,CARISTA,Makam
JakoJako,VNTM,Gizem,Antonio Ruscito & Luigi Tozzi
Andrea Oliva,Cincity,Atmos Blaq,LevyM
Isabel Soto,Speedy J,Claudio PRC,Megan Leber
Bakio,Hannecart,Voigtmann,J:Me,Benji,Noach,Marsolo,Phil de Janeiro,Julian Anthony,Job de Jong
Mia Cecille,Sugar Free,Roza Terenzi,Bashkka,HUNEE,Bitter Babe,D.Tiffany,Roi Perez,Paquita Gordon,John Talabot
Mind Against
Kerrie,LazerGazer,BLANKA,Zisko,SAMA,Wata Igarashi,Julia Maria,Sarkawt Hamad,Amotik,Stojche,Karina Schneider,Delano Legito ,Function
Hot Since 82,Kim April,Ranger Trucco,Karel
DJ PAULÃO,Coco Maria,Musclecars,Kikiorix,Satoshi Tomiie,Giles Peterson,Antal,Kléo
Surf 2 Glory,Marlon Hoffstadt
Marlon Hoffstadt,CVNTS,Sellout bonus Marlon,Saidah,Benny2
Agents of Time
Quelza
Schwesta P,Tjade,Herr Krank,DJ Frank,Kendal,NewTone,Bella Claxton,Jenny Cara,Olivia Lensen
nthng,VNTM,Luna Ludmila,Andy Martin,VRIL
Cassian,Stranger,Re-Type,Tasha,Brina Knauss,REZarin,Joris Voorn
Spacer Woman,CRYME,Matrixxman,Slimfit ,The Lady Machine,DJ Fuckoff,SALOME,PORNCEPTUAL
Lilya Mandre,KUKU,MoBlack,Laolu
Âme,Samaʼ Abdulhadi
Moody Mehran,Essy
LSDXOXO,Fiene,BIIANCO,Supergloss
The Trip,Luuk van Dijk,DJ Boring,Merel Helderman
Tauceti,Polar Inertia,D.Dan,Kangding Ray,Faustin,DJ Yazi,JakoJako,Kia,Beatrice M.,Luke Vibert,Monophonik,Vlada,Innersha,Garcon,Agonis,Priori,oma totem,Spekki Webu,Sunju Hargun,Decoder
Philou Louzolo,Trikk,Yulia Niko,LYLO
Massano,Sellout
AMORAL,UFO95,Talismann,VIL,Valody,Tafkamp,Nick Moody,Mary Lake,Amanda Mussi,Toobris,BIANKA,Norbak,Olivia Mendez,Ignez,SECONDS (Setaoc Mass),SECONDS (Phara)
Bart Skils,Roger Geressen,Victor Ruiz,Oliver Huntemann
Barker,Vera Logdanidi,Arthur Rober,Martinou,VNTM
Paquita Gordon,Christian AB,Francesco Del Garda,Marco Shuttle
Entasia,DART,Miamor,Tjade,Fiene,S3PPA,NewTone
Ron Trent,Antal
Andy Martin
Ryan Elliot
DAX J
Antal,Hunee
Moody Mehran,Essy
LSDXOXO,Fiene,BIIANCO,Supergloss
The Trip,Luuk van Dijk,DJ Boring,Merel Helderman
Philou Louzolo,Trikk,Yulia Niko,LYLO
"""

def parse_names(raw: str) -> set[str]:
    names: set[str] = set()
    skip = {"unnamed record", "superstrings", "sellout", "hostingfee", "brandfee",
            "test joël", "slimfit", "22 interns", "kamma & masalo"}
    for line in raw.splitlines():
        # split on tab or 2+ spaces (column separator) then on comma
        parts = re.split(r'\t|  +', line)
        for part in parts:
            for token in part.split(','):
                name = token.strip().strip(' ')
                if not name:
                    continue
                lower = name.lower()
                if lower in skip or lower.startswith('unnamed'):
                    continue
                # skip obvious non-artist tokens
                if lower in {'sellout bonus marlon', 'benny2', 'saidah', 'cvnts'}:
                    continue
                names.add(name)
    return names

INPUT_NAMES = sorted(parse_names(RAW), key=str.lower)
print(f"Unique artist names parsed from lineup data: {len(INPUT_NAMES)}")

# ── Load all artists from Supabase ───────────────────────────────────────────
rows = sb.schema("tinder").table("artists") \
    .select("id, name, candidate_status") \
    .order("name").execute()
db_artists = rows.data or []

# Build lookup: lowercase name → (id, candidate_status)
db_map: dict[str, tuple[str, str]] = {}
for a in db_artists:
    db_map[a["name"].strip().lower()] = (a["id"], a.get("candidate_status", ""))

print(f"Artists in Supabase: {len(db_map)}")
print()

# ── Cross-reference ──────────────────────────────────────────────────────────
found: list[tuple[str, str, str]] = []
missing: list[str] = []

for name in INPUT_NAMES:
    key = name.strip().lower()
    if key in db_map:
        aid, status = db_map[key]
        found.append((name, aid, status))
    else:
        missing.append(name)

# ── Fuzzy near-matches for missing names ─────────────────────────────────────
from difflib import get_close_matches

near: dict[str, list[str]] = {}
db_keys = list(db_map.keys())
for name in missing:
    key = name.strip().lower()
    matches = get_close_matches(key, db_keys, n=3, cutoff=0.75)
    if matches:
        near[name] = [db_map[m][0] + f" ({m})" for m in matches]

# ── Output ───────────────────────────────────────────────────────────────────
print(f"{'='*60}")
print(f"FOUND IN DB ({len(found)}/{len(INPUT_NAMES)})")
print(f"{'='*60}")
for name, aid, status in sorted(found, key=lambda x: x[0].lower()):
    print(f"  YES  {name:<35} [{status}]")

print()
print(f"{'='*60}")
print(f"NOT IN DB ({len(missing)}/{len(INPUT_NAMES)})")
print(f"{'='*60}")
for name in missing:
    fuzzy = near.get(name, [])
    hint = f"  -> near: {', '.join(fuzzy)}" if fuzzy else ""
    print(f"  NO   {name}{hint}")

print()
print(f"Summary: {len(found)} found, {len(missing)} missing out of {len(INPUT_NAMES)} unique names")
