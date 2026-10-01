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

ID_PREFIXES = {"source": "src_", "observation": "obs_", "signal": "sig_", "service_request": "sr_"}

MAX_AUDIO_SECONDS = 300
LOW_CONFIDENCE_THRESHOLD = 0.5
FALLBACK_CONFIDENCE = 0.3
MIN_SIGNAL_GROUP_SIZE = 2
UNKNOWN_BOROUGH = "Unknown"
DEFAULT_LANGUAGE = "en"
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]

# --- "Mamdani, fix this" workflow -------------------------------------------------
DEFAULT_WINDOW_DAYS = 5
MAYOR_HANDLES = ("zohrankmamdani", "nycmayor")
# Includes common ASR/typo renderings seen in the corpus ("Mom Donnie, fix this pothole").
MAYOR_KEYWORDS = ("mamdani", "zohran", "mayor", "mandani", "momdani", "mondani", "mondami",
                  "mom donnie", "mom, donnie", "mom donny", "mom, donny")
# Corpus relevance labels on Source.relevance. Only fix requests become Observations / 311 drafts.
RELEVANCE_FIX = "fix_request"
RELEVANCE_MAYOR = "mayor_related"
RELEVANCE_UNRELATED = "unrelated"
RELEVANCE_OUTSIDE = "outside_nyc"  # a fix request, but about another city/country (the trend spread)
RELEVANCE_LABELS = (RELEVANCE_FIX, RELEVANCE_OUTSIDE, RELEVANCE_MAYOR, RELEVANCE_UNRELATED)
FIX_KEYWORDS = ("fix this", "fixthis", "fix it", "please fix", "can you fix", "fix these", "fix that",
                "fix our", "fix my", "fix dis", "come fix", "pls fix", "plz fix", "get this fixed")

# Official Instagram handles we recognise when a poster tags them. Used only to show
# who the poster already addressed; nothing is ever sent to these accounts.
AGENCY_HANDLES: dict[str, str] = {
    "nycdot": "NYC DOT",
    "nycsanitation": "NYC DSNY",
    "nycparks": "NYC Parks",
    "nycwater": "NYC DEP",
    "nychpd": "NYC HPD",
    "nypdnews": "NYPD",
    "nycbuildings": "NYC DOB",
    "nychealthy": "NYC DOHMH",
    "mta": "MTA",
    "mtanyctransit": "MTA",
    "nyc311": "NYC 311",
}

# topic -> (311 complaint type, default descriptor, agency). Complaint types follow the
# NYC 311 Service Request taxonomy; staff can change them before filing.
SR_TYPES: dict[str, tuple[str, str, str]] = {
    "streetlights": ("Street Light Condition", "Street Light Out", "NYC DOT"),
    "roads": ("Street Condition", "Pothole", "NYC DOT"),
    "sidewalks": ("Sidewalk Condition", "Broken Sidewalk", "NYC DOT"),
    "transportation": ("Traffic Signal Condition", "Controller", "NYC DOT"),
    "accessibility": ("Curb Condition", "Pedestrian Ramp Defective", "NYC DOT"),
    "trash": ("Dirty Condition", "Trash", "NYC DSNY"),
    "rats": ("Rodent", "Rat Sighting", "NYC DOHMH"),
    "parks": ("Maintenance or Facility", "Structure - Outdoors", "NYC Parks"),
    "water": ("Water System", "Leak (Use Comments)", "NYC DEP"),
    "noise": ("Noise - Street/Sidewalk", "Loud Talking", "NYPD"),
    "housing": ("HEAT/HOT WATER", "Apartment Only", "NYC HPD"),
    "construction": ("General Construction/Plumbing", "Working Contrary To Stop Work Order", "NYC DOB"),
    "public_safety": ("Non-Emergency Police Matter", "Other (complaint details)", "NYPD"),
    "public_facilities": ("Maintenance or Facility", "Structure - Indoors", "NYC Parks"),
    "public_transit": ("MTA (not a 311 agency)", "Route via MTA customer feedback", "MTA"),
    "other": ("General Question", "Other", "NYC 311"),
}

# Keyword fallback used only when no Gemini key is configured; results are low-confidence.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "streetlights": ("streetlight", "street light", "lamp post", "light is out", "lights out", "light pole"),
    "roads": ("pothole", "road", "asphalt", "crater"),
    "sidewalks": ("sidewalk", "curb", "tripped"),
    "trash": ("trash", "garbage", "litter", "overflowing", "dumping", "sanitation"),
    "rats": ("rat", "rats", "rodent", "mice", "roach"),
    "parks": ("park", "playground", "fountain", "bench", "tree", "swing", "swings", "slide", "jungle gym"),
    "water": ("water main", "leak", "flood", "sewer", "hydrant", "drain"),
    "noise": ("noise", "loud", "music", "honking"),
    "housing": ("heat", "hot water", "landlord", "mold", "apartment", "nycha"),
    "construction": ("construction", "scaffold", "scaffolding", "crane"),
    "public_transit": ("subway", "bus", "train", "station", "mta", "elevator"),
    "public_safety": ("unsafe", "dangerous", "crime"),
    "transportation": ("traffic light", "signal", "crosswalk", "bike lane", "street sign", "sign", "pole"),
    "accessibility": ("wheelchair", "ramp", "accessible", "stroller"),
}

BORO_CODES = {1: "Manhattan", 2: "Bronx", 3: "Brooklyn", 4: "Queens", 5: "Staten Island"}
MAX_COMMUNITY_DISTRICT = 18  # BoroCD values above x18 are parks/airports with no board
SR_STATUSES = ("draft", "approved", "filed", "declined")
GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"
ARCGIS_BASE = "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services"
PORTAL_311_URL = "https://portal.311.nyc.gov/"

# Places people tag Mamdani about that are outside NYC 311 jurisdiction. Regexes over lowercased text
# (hashtags included). Names that are also NYC streets/places are guarded or left out
# (Jamaica, Washington, Columbus, Austin, Houston St, Kings Highway, Lebanon St...).
NON_NYC_PLACES = (
    # US
    "los angeles", "beverly hills", "west hollywood", "hollywood", "chicago", "philadelphia", "philly",
    "new jersey", "jersey city", "hoboken", "newark", "boston", "miami", "san francisco", "long island(?! city)",
    "westchester", "#la\\b", "\\bl\\.a\\.", "california", "texas", "florida", "ohio", "georgia", "atlanta",
    "arizona", "colorado", "denver", "nebraska", "omaha", "missouri", "seattle", "portland",
    "detroit", "baltimore", "nashville", "orlando", "tampa", "daytona", "dallas", "san antonio",
    "las vegas", "new orleans", "minneapolis", "pittsburgh", "cleveland, oh", "columbus,? ohio", "cleveland ave",
    "stockton", "sacramento", "san diego", "raleigh", "\\bhtx\\b", "downtownhouston",
    "houston(?!\\s*(?:st|street))", "connecticut", "pennsylvania", "michigan", "virginia", "maryland",
    # elsewhere
    "london", "england", "manchester", "scotland", "ireland", "dublin", "paris", "france", "spain", "madrid",
    "barcelona", "gij[oó]n", "germany", "berlin", "italy", "rome", "amsterdam", "netherlands", "finland",
    "helsinki", "sweden", "norway", "tbilisi", "istanbul", "lebanon(?!\\s*st)", "beirut", "dubai",
    "egypt", "cairo", "nigeria", "lagos", "ghana", "accra", "kenya", "nairobi", "south africa", "india",
    "mumbai", "delhi", "pakistan", "karachi", "lahore", "bangladesh", "dhaka", "indonesia", "jakarta",
    "malaysia", "kuala lumpur", "singapore", "philippines", "manila", "australia", "canberra", "sydney",
    "melbourne", "toronto", "canada", "vancouver", "montreal", "mexico", "guadalajara", "brazil", "argentina",
    "colombia", "japan", "tokyo", "korea", "seoul", "china", "uganda", "kampala",
)
# Evidence the post is about NYC, checked in caption/transcript text with hashtags removed (everyone adds #nyc).
NYC_SIGNAL_RE = (
    r"new york|\bnyc\b|\bny\b|brooklyn|queens|\bbronx\b|manhattan|staten island|\bmta\b|subway|"
    r"\b1(?:0[0-4]|1[0-6])\d\d\b"  # NYC ZIP codes
)
NYC_LOCATION_TAG_RE = r"new york|\bny\b|brooklyn|queens|bronx|manhattan|staten island|\bkings\b|richmond"
