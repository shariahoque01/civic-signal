"""Shared enums and lookup tables. No magic strings elsewhere."""

APP_VERSION = "0.1.0"

PLATFORMS = ("tiktok", "instagram", "upload")
PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "tiktok": ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"),
    "instagram": ("instagram.com", "instagr.am"),
}

OBSERVATION_TYPES = ("issue", "request", "idea", "praise", "information", "other")
TOPICS = (
    "streetlights", "transportation", "trash", "rats", "parks", "sidewalks",
    "roads", "public_transit", "housing", "public_safety", "water", "noise",
    "construction", "accessibility", "public_facilities", "other",
)
BOROUGHS = ("Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island")
URGENCIES = ("low", "medium", "high")
STATUSES = ("new", "reviewed", "rejected")
PRIORITIES = ("low", "medium", "high")
TRENDS = ("increasing", "stable", "decreasing")

AGENCIES = (
    "NYC DOT", "NYC DSNY", "NYC Parks", "NYC DEP", "NYC HPD", "NYPD",
    "NYC DOB", "NYC DOHMH", "MTA", "NYC 311",
)

# Deterministic fallback used when the model proposes no agency.
TOPIC_AGENCY_MAP: dict[str, str] = {
    "streetlights": "NYC DOT",
    "transportation": "NYC DOT",
    "trash": "NYC DSNY",
    "rats": "NYC DOHMH",
    "parks": "NYC Parks",
    "sidewalks": "NYC DOT",
    "roads": "NYC DOT",
    "public_transit": "MTA",
    "housing": "NYC HPD",
    "public_safety": "NYPD",
    "water": "NYC DEP",
    "noise": "NYC DEP",
    "construction": "NYC DOB",
    "accessibility": "NYC DOT",
    "public_facilities": "NYC 311",
    "other": "NYC 311",
}

ID_PREFIXES = {"source": "src_", "observation": "obs_", "signal": "sig_"}

MAX_AUDIO_SECONDS = 300
LOW_CONFIDENCE_THRESHOLD = 0.5
FALLBACK_CONFIDENCE = 0.3
MIN_SIGNAL_GROUP_SIZE = 2
UNKNOWN_BOROUGH = "Unknown"
DEFAULT_LANGUAGE = "en"
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
