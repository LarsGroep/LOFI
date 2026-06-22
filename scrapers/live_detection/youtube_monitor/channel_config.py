"""
YouTube channel registry — core platforms for LOFI artist intelligence.
Channel IDs and title-parsing patterns per platform.
"""

CHANNELS = [
    {
        "platform":          "boiler_room",
        "channel_name":      "Boiler Room",
        "youtube_channel_id":"UCGBpxWJr9FNOcFYA5GkKrMg",
        "priority":          "core",
        # "{artist} | Boiler Room {city}"  or  "{artist} b2b {artist} | Boiler Room"
        "title_patterns":    [r"^(.+?)\s*\|?\s*Boiler Room"],
    },
    {
        "platform":          "hor_berlin",
        "channel_name":      "HÖR Berlin",
        "youtube_channel_id":"UCmfF7JZv26UUKyRedViGIlw",
        "priority":          "core",
        # "HÖR - 2024-11-02 - Chlär"
        "title_patterns":    [r"HÖR\s*[-–]\s*[\d\-]+\s*[-–]\s*(.+)$"],
    },
    {
        "platform":          "f2f_tv",
        "channel_name":      "F2F TV",
        "youtube_channel_id": None,   # look up on first run
        "priority":          "core",
        # "F2F | Alignment b2b Anetha | ADE 2024"
        "title_patterns":    [r"F2F\s*\|\s*(.+?)\s*\|"],
    },
    {
        "platform":          "mixmag",
        "channel_name":      "Mixmag",
        "youtube_channel_id":"UCQdCIrTpkhEH5Z8KPsn7NvQ",
        "priority":          "core",
        # "Estella Boersma Live @ Fabric" / "Mixmag Lab: Chlär"
        "title_patterns":    [
            r"^(.+?)\s+(?:Live @|in the Lab|Mixmag Lab)",
            r"Mixmag Lab:\s*(.+)$",
        ],
    },
    {
        "platform":          "the_lot_radio",
        "channel_name":      "The Lot Radio",
        "youtube_channel_id":"UCJOtExbMu0RqIdiE4nMUPxQ",
        "priority":          "core",
        "title_patterns":    [r"^(.+?)\s*[-–@|]"],
    },
    {
        "platform":          "rinse_fm",
        "channel_name":      "Rinse FM",
        "youtube_channel_id":"UCgGfSxNOBkJDtCQ932iQU7Q",
        "priority":          "core",
        # "Sandrien - Rinse FM 2024"
        "title_patterns":    [r"^(.+?)\s*[-–]\s*Rinse"],
    },
    {
        "platform":          "book_club_radio",
        "channel_name":      "Book Club Radio",
        "youtube_channel_id":"UCLmaR7ew57x0XJEe_-REUyg",
        "priority":          "core",
        # "Book Club Radio with Chlär"
        "title_patterns":    [r"Book Club Radio\s+(?:with|presents?)\s+(.+)$"],
    },
    {
        "platform":          "be_at_tv",
        "channel_name":      "BE-AT.TV",
        "youtube_channel_id":"UCOloc4MDn4dQtP_U6asWk2w",
        "priority":          "core",
        "title_patterns":    [r"^(.+?)\s*(?:@|at|live at)\s+", r"^(.+?)\s*\|"],
    },
]

# Views/hour thresholds to flag a video as trending.
# Calibrated per channel — Boiler Room has much higher baseline than Book Club Radio.
TRENDING_THRESHOLDS = {
    "boiler_room":     8_000,   # views/hour in first 48h
    "hor_berlin":      3_000,
    "f2f_tv":          1_500,
    "mixmag":          4_000,
    "the_lot_radio":   1_000,
    "rinse_fm":        1_500,
    "book_club_radio":   800,
    "be_at_tv":        1_000,
    "_default":        1_500,
}

# Separators that split B2B or multi-artist titles
ARTIST_SPLIT_TOKENS = [" b2b ", " B2B ", " b 2 b ", " & ", " x ", " vs ", " + "]
