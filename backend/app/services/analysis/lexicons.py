"""Hand-built lexicons. Transparent on purpose: every label the page shows can be traced to a word list here.

Tuned by reading the real corpus (Sept 2026 #mamdani / #mamdanifixthis TikToks). They are heuristics, and the
page says so.
"""

# --- Genre: what kind of video is this? -----------------------------------------------------------------
NEWS_HANDLES = frozenset({
    "cnn", "nbcnewyork", "abc7ny", "ny1", "newsweek", "politiconews", "fox5newyork", "dailymailpolitics",
    "1010wins923", "cspanofficial", "nytimes", "nypost", "pix11news", "cbsnewyork", "gothamist", "thecity",
    "nbcnews", "abcnews", "foxnews", "cbsnews", "apnews", "reuters", "washingtonpost", "wsj", "bloomberg",
})
ENTERTAINMENT_HANDLES = frozenset({"nbcsnl", "jimmykimmellive", "fallontonight", "colbertlateshow"})
OFFICIAL_HANDLES = frozenset({"zohrankmamdani", "nycmayor", "zohran_k_mamdani"})

# Physical, place-bound problems (a service ask is one of these + an ask).
PROBLEM_TERMS = (
    "pothole", "potholes", "flood", "flooded", "flooding", "sidewalk", "swings", "swing", "playground",
    "elevator", "escalator", "pole", "streetlight", "street light", "traffic light", "trash", "garbage", "rats",
    "rat", "leak", "sewer", "drain", "hydrant", "construction", "scaffolding", "noise", "factory",
    "clean air", "air quality", "fumes", "dust", "heat", "hot water", "mold", "roof", "bench", "fountain",
    "crosswalk", "bike lane", "bus stop", "subway", "block", "road", "street", "wet", "puddle", "curb",
)
ASK_TERMS = (
    "fix", "fix this", "fix it", "fixed", "help", "send help", "please", "pls", "we need", "i need",
    "do something", "can you", "stop this", "has to go", "gotta do", "save us", "come fix",
)
COMMENTARY_TERMS = (
    "netanyahu", "zionist", "zionism", "israel", "palestine", "socialism", "socialist", "communist",
    "marxist", "leftist", "leftists", "imperial", "empire", "trump", "republican", "republicans",
    "democrat", "democratic", "vote", "voting", "election", "elected", "campaign", "promised", "lied",
    "liar", "compromised", "controlled opposition", "antisemitism", "anti semitism", "antisemitic",
    "midterms", "politics", "politician", "politicians", "policies", "capitalism", "free buses", "srg",
    "tax the rich", "pied", "gop", "president", "blakeman",
)
NEWS_TERMS = (
    "announced", "announce", "announcing", "unveiled", "unveils", "launched", "launching", "ruling", "judge",
    "lawsuit", "lawsuits", "press conference", "commissioner", "today we", "top stories", "breaking",
    "fast fact", "reporter", "city hall", "administration", "million", "billion", "opening", "jobs center",
    "job center",
)
FANDOM_TERMS = (
    "love", "loved", "my mayor", "our mayor", "hot", "hottest", "sexy", "attractive", "goat", "king",
    "appreciation", "fan", "standing ovation", "birthday", "bday", "president", "down bad", "role model",
    "doing a good job", "great job", "proud", "recommendation", "recommends", "🥹", "💛", "❤️",
)
MEME_TERMS = (
    "meme", "edit", "edits", "satire", "parody", "skit", "snl", "kimmel", "animation", "aftereffects",
    "lol", "😭", "😂", "🤣", "bikini bottom", "reality-show", "ding dong", "slime", "writing", "harry styles",
    "dancing", "rock and roll", "matchup", "magically appear", "greenscreen", "relateable", "relatable",
)
# Playful or personal asks: the trend's form ("Mamdani fix this") applied to non-city things.
PERSONAL_ASK_TERMS = (
    "fix my life", "close school", "i spent too much money", "ice cream", "call me", "overstimulated",
    "my life", "dating life", "love life", "depressed", "turn me into", "fixmylife", "mamdanifixmylife", "my grades",
    "my sleep", "my ex",
)
MAYOR_TERMS = ("mamdani", "momdani", "mondani", "mandani", "madani", "mamdany", "zohran", "zoran", "donnie", "mayor")

# Someone saying a problem got fixed, or that the mayor's team responded: closes the loop.
CLOSURE_TERMS = (
    "finally fixed", "they fixed", "you fixed", "he fixed", "got fixed", "fixed it", "thank you for fixing",
    "it's fixed", "thanks for fixing", "came and fixed", "fixed in", "fixed within", "responding directly",
    "they came out", "already fixed", "it got fixed", "has been fixed", "was fixed",
)

# --- Place: in NYC or not? -------------------------------------------------------------------------------
NYC_PLACE_TERMS = (
    "new york", "nyc", "brooklyn", "bronx", "queens", "manhattan", "staten island", "harlem", "astoria",
    "bushwick", "far rockaway", "farrockaway", "rockaway", "kings highway", "kingshighway", "lexington",
    "melrose", "penn station", "flatbush", "bed-stuy", "williamsburg", "jamaica", "flushing", "nycha",
)
NON_NYC_PLACE_TERMS = (
    "houston", "texas", "tbilisi", "beverly hills", "west hollywood", "hollywood", "los angeles", "atlantic city",
    "long island", "dallas", "ireland", "london", "chicago", "new jersey", "jersey city", "philadelphia",
    "toronto", "miami", "boston", "san francisco", "georgia", "#la", "uhd", "downtownhouston", "indonesia",
    "gijón", "gijon", "spain", "stockton", "colorado", "omaha", "nebraska", "nebraksa", "charlotte", "california",
    "newjersey", "#colorado", "philly", "detroit", "atlanta", "canada", "mexico", "india", "pakistan", "uganda",
)

# --- Themes: what is being talked about, and does 311 have a box for it? --------------------------------
# fit: "app" = our SR_TYPES taxonomy covers it; "311" = real NYC 311 has a type our app doesn't draft yet;
#      "none" = no 311 path (policy, schools, out of jurisdiction, personal).
THEMES: dict[str, dict] = {
    "street_flooding": {
        "label": "Street & sidewalk flooding",
        "terms": ("flood", "flooded", "flooding", "wet", "puddle", "storm", "bikini bottom", "☔", "rain", "el nino"),
        "fit": "311", "sr_hint": "Sewer › Catch Basin Clogged/Flooding (DEP)",
    },
    "potholes_streets": {
        "label": "Potholes & street condition",
        "terms": ("pothole", "potholes", "road", "asphalt", "street condition", "hole in the road"),
        "fit": "app", "sr_hint": "Street Condition › Pothole (DOT)",
    },
    "street_fixtures": {
        "label": "Poles, signs & lights",
        "terms": ("pole", "streetlight", "street light", "sign", "traffic light", "lamp"),
        "fit": "app", "sr_hint": "Street Light / Street Sign Condition (DOT)",
    },
    "parks_play": {
        "label": "Playgrounds & parks",
        "terms": ("swings", "swing", "playground", "playgrounds", "park", "slide", "community garden", "fountain",
                  "water fountain", "seesaw", "seesaws", "bench", "benches"),
        "fit": "app", "sr_hint": "Maintenance or Facility (Parks)",
    },
    "air_environment": {
        "label": "Air quality & industrial neighbors",
        "terms": ("clean air", "air quality", "concrete factory", "factory", "fumes", "dust", "asthma", "pollution",
                  "idling", "contamination", "noise pollution"),
        "fit": "311", "sr_hint": "Air Quality (DEP), not in the app's draft taxonomy yet",
    },
    "elevators_access": {
        "label": "Elevators & accessibility",
        "terms": ("elevator", "escalator", "wheelchair", "ramp", "accessible", "stroller"),
        "fit": "311", "sr_hint": "Elevator (DOB) or MTA; route depends on building",
    },
    "housing_nycha": {
        "label": "Housing, NYCHA & rent",
        "terms": ("housing", "nycha", "rent", "rental", "landlord", "affordable", "units", "heating", "hot water",
                  "preservation trust", "tenants", "apartment"),
        "fit": "311", "sr_hint": "HEAT/HOT WATER etc. (HPD) for individual units; policy otherwise",
    },
    "transit_fares": {
        "label": "Transit & fares",
        "terms": ("bus", "buses", "train", "subway", "fare", "mta", "penn station", "free buses"),
        "fit": "none", "sr_hint": "MTA is state-run; fares are policy",
    },
    "schools_kids": {
        "label": "Schools & kids",
        "terms": ("school", "schools", "pre k", "pre-k", "kids", "children", "education", "teacher", "teaching",
                  "hip hop school", "students"),
        "fit": "none", "sr_hint": "DOE, not a 311 category",
    },
    "jobs_services": {
        "label": "City jobs & services",
        "terms": ("jobs nyc", "job center", "city job", "jobs center", "public service", "ecrj", "delivery workers",
                  "doordash", "hiring", "vendor", "vendors"),
        "fit": "none", "sr_hint": "Program information; not a complaint",
    },
    "taxes_budget": {
        "label": "Taxes (pied-à-terre) & budget",
        "terms": ("tax", "taxes", "pied", "pied-à-terre", "surcharge", "tax the rich", "budget", "taxation"),
        "fit": "none", "sr_hint": "Policy",
    },
    "antisemitism_hate": {
        "label": "Antisemitism & hate-crime strategy",
        "terms": ("antisemitism", "anti semitism", "antisemitic", "anti semitic", "jewish", "hate crime",
                  "hate crimes", "shuls"),
        "fit": "none", "sr_hint": "Policy",
    },
    "israel_foreign": {
        "label": "Netanyahu, Israel & foreign policy",
        "terms": ("netanyahu", "israel", "zionist", "zionists", "zionism", "palestine", "palestinian",
                  "war criminal", "u n", "united nations", "imperialism", "empire"),
        "fit": "none", "sr_hint": "Outside city service delivery",
    },
    "policing": {
        "label": "Policing & protest",
        "terms": ("nypd", "police", "srg", "arrested", "arrest", "protest", "protesters"),
        "fit": "none", "sr_hint": "Policy (non-emergency police matters do exist in 311)",
    },
    "trump_national": {
        "label": "Trump & national politics",
        "terms": ("trump", "republican", "republicans", "midterms", "president", "gop", "democratic party",
                  "washington", "oval office"),
        "fit": "none", "sr_hint": "Outside city service delivery",
    },
    "celebrity_media": {
        "label": "Celebrity & late-night TV",
        "terms": ("snl", "saturday night live", "kimmel", "colbert", "ramy", "nas", "thierry henry", "harry styles",
                  "tv on the radio", "arsenal", "man city"),
        "fit": "none", "sr_hint": "Not actionable",
    },
    "community_events": {
        "label": "Parades, birthdays & community events",
        "terms": ("parade", "birthday", "bday", "celebration", "independence day", "partiful", "festival"),
        "fit": "none", "sr_hint": "Community engagement / events office",
    },
}

# --- Severity & register ---------------------------------------------------------------------------------
HAZARD_TERMS = (
    "flooding", "flooded", "flood", "open manhole", "exposed wire", "gas leak", "collapsed", "sinkhole", "fire",
)
HARM_TERMS = (
    "someone's gonna get hurt", "someone going to get hurt", "get hurt", "hurt", "injured", "dangerous", "unsafe",
    "fell", "accident", "emergency", "health", "clean air", "asthma", "can't breathe", "fumes",
)
VULNERABLE_TERMS = (
    "kids", "children", "child", "school", "pre k", "three and four year olds", "students", "seniors",
    "elderly", "wheelchair", "disabled", "pregnant", "baby", "my education", "stroller",
)
PERSISTENCE_TERMS = (
    "every day", "everyday", "again", "still hasn't", "still not", "never put back", "since orientation",
    "enough is enough", "i brought this issue", "for years", "whole block", "whole sidewalk", "another pothole",
)
FRUSTRATION_TERMS = (
    "enough is enough", "tired of", "what the fuck", "wtf", "stop slacking", "slacking", "sick of", "🥀",
    "what is this", "come on", "cmon", "has to go", "i don't know how else",
)
# People saying the formal channel already failed them: the core evidence for a "voice gap".
TRIED_CHANNELS_TERMS = (
    "311 calls", "3 1 1 calls", "called 311", "call 311", "called 3 1 1", "311 complaint", "filed a complaint",
    "community board", "brought this issue to your attention", "reached out", "emailed", "nothing is getting done",
    "people report", "reported it", "we reported", "i reported", "nobody came", "no one came",
)
HOPE_TERMS = ("thank you", "goat", "please", "🙏", "praying", "let him work", "i believe", "hopefully")
DURATION_RE = (
    r"(?:for|been|over|almost|nearly|since)\s+(?:about\s+|like\s+)?"
    r"(a|an|one|two|three|four|five|six|\d+)\s+(day|week|month|year)s?"
)

# --- Self-described speaker cues (never inferred) ---------------------------------------------------------
SPEAKER_CUES: dict[str, dict] = {
    "parent": {"label": "Parent / caregiver", "terms": ("my daughter", "my son", "my kids", "my child", "as a mom",
                                                         "as a dad", "as a parent", "my baby")},
    "child_voice": {"label": "Child speaking", "terms": ("my daddy", "my mommy", "my education", "we're bored dad",
                                                          "across the street from our school")},
    "educator": {"label": "Teacher / educator", "terms": ("public school teacher", "finished teaching", "i'm a teacher",
                                                           "as a teacher", "my students")},
    "social_worker": {"label": "Social / care worker", "terms": ("social worker", "foster care", "nurse")},
    "worker": {"label": "Worker (self-described job)", "terms": ("dollar tree", "i work at", "my job", "my shift",
                                                                "delivery worker")},
    "student": {"label": "Student", "terms": ("i'm a student", "as a student", "my professor", "my campus",
                                            "came in orientation", "since orientation", "my college", "my class")},
    "faith_identity": {"label": "Self-described faith/community identity",
                       "terms": ("as a jewish new yorker", "representing lagos", "my people", "as a muslim")},
    "visitor": {"label": "Visitor / non-resident", "terms": ("came all the way from", "i live in los angeles",
                                                              "i actually live on long island", "i'll visit new york",
                                                              "otw nyc", "trip")},
    "native": {"label": "Long-time New Yorker", "terms": ("born & raised", "born and raised", "my hometown",
                                                           "grew up in")},
}
