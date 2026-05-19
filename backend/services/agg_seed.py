"""Seed data for the public aggregator. 28 residential real estate publishers.

Run on startup via aggregator_cron.ensure_seed(). Idempotent — only inserts a
publisher if its slug is not already in the collection. Existing rows are not
overwritten so an admin can tune them via /admin without being reset.
"""

# Each tuple: name, slug, category, feed_url, homepage_url, display_mode, permission_status
SEED_PUBLISHERS = [
    ("Inman",                   "inman",            "national_trade", "https://www.inman.com/feed/",                          "https://www.inman.com",            "headline_only",         "pending"),
    ("The Real Deal",           "the-real-deal",    "national_trade", "https://therealdeal.com/feed/",                        "https://therealdeal.com",           "headline_and_snippet",  "pending"),
    ("HousingWire",             "housingwire",      "national_trade", "https://www.housingwire.com/feed/",                    "https://www.housingwire.com",       "headline_only",         "pending"),
    ("RISMedia",                "rismedia",         "national_trade", "https://www.rismedia.com/feed/",                       "https://www.rismedia.com",          "headline_and_snippet",  "pending"),
    ("Realtor.com News",        "realtor-com",      "national_trade", "https://www.realtor.com/news/feed/",                   "https://www.realtor.com/news",      "headline_only",         "pending"),
    ("TRD New York",            "trd-nyc",          "regional",       "https://therealdeal.com/new-york/feed",                "https://therealdeal.com/new-york",  "headline_and_snippet",  "pending"),
    ("TRD Los Angeles",         "trd-la",           "regional",       "https://therealdeal.com/la/feed",                      "https://therealdeal.com/la",        "headline_and_snippet",  "pending"),
    ("TRD Miami",               "trd-miami",        "regional",       "https://therealdeal.com/miami/feed",                   "https://therealdeal.com/miami",     "headline_and_snippet",  "pending"),
    ("TRD Chicago",             "trd-chicago",      "regional",       "https://therealdeal.com/chicago/feed",                 "https://therealdeal.com/chicago",   "headline_and_snippet",  "pending"),
    ("TRD San Francisco",       "trd-sf",           "regional",       "https://therealdeal.com/sanfrancisco/feed",            "https://therealdeal.com/sanfrancisco","headline_and_snippet","pending"),
    ("TRD Texas",               "trd-texas",        "regional",       "https://therealdeal.com/texas/feed",                   "https://therealdeal.com/texas",     "headline_and_snippet",  "pending"),
    ("Brownstoner",             "brownstoner",      "regional",       "https://www.brownstoner.com/feed/",                    "https://www.brownstoner.com",       "headline_and_snippet",  "not_required"),
    ("Curbed",                  "curbed",           "regional",       "https://www.curbed.com/rss/index.xml",                 "https://www.curbed.com",            "headline_only",         "pending"),
    ("Notorious R.O.B.",        "notorious-rob",    "industry_blog",  "https://www.notoriousrob.com/feed/",                   "https://www.notoriousrob.com",      "headline_and_snippet",  "not_required"),
    ("Mike DelPrete",           "mike-delprete",    "industry_blog",  "https://www.mikedp.com/articles?format=rss",           "https://www.mikedp.com",            "headline_and_snippet",  "not_required"),
    ("1000Watt",                "1000watt",         "industry_blog",  "https://1000watt.net/feed",                            "https://1000watt.net",              "headline_and_snippet",  "not_required"),
    ("Vendor Alley",            "vendor-alley",     "industry_blog",  "https://www.vendoralley.com/feed/",                    "https://www.vendoralley.com",       "headline_and_snippet",  "not_required"),
    ("Geek Estate Blog",        "geek-estate",      "industry_blog",  "https://geekestateblog.com/feed",                      "https://geekestateblog.com",        "headline_and_snippet",  "not_required"),
    ("Keeping Current Matters", "kcm",              "industry_blog",  "https://www.keepingcurrentmatters.com/feed",           "https://www.keepingcurrentmatters.com","headline_only",      "pending"),
    ("The Close",               "the-close",        "industry_blog",  "https://theclose.com/feed/",                           "https://theclose.com",              "headline_and_snippet",  "not_required"),
    ("BiggerPockets Blog",      "biggerpockets",    "industry_blog",  "https://www.biggerpockets.com/blog/feed",              "https://www.biggerpockets.com/blog","headline_only",         "pending"),
    ("Calculated Risk",         "calculated-risk",  "data_research",  "https://calculatedrisk.substack.com/feed",             "https://calculatedrisk.substack.com","headline_and_snippet", "not_required"),
    ("Wolf Street",             "wolf-street",      "data_research",  "https://wolfstreet.com/feed/",                         "https://wolfstreet.com",            "headline_and_snippet",  "not_required"),
    ("Altos Research",          "altos",            "data_research",  "https://blog.altosresearch.com/rss.xml",               "https://blog.altosresearch.com",    "headline_only",         "pending"),
    ("Redfin News",             "redfin",           "data_research",  "https://www.redfin.com/blog/feed/",                    "https://www.redfin.com/blog",       "headline_only",         "pending"),
    ("Zillow Press",            "zillow-press",     "data_research",  "https://zillow.mediaroom.com/rss-feeds",               "https://zillow.mediaroom.com",      "headline_only",         "pending"),
    ("Mortgage News Daily",     "mnd",              "mortgage",       "https://www.mortgagenewsdaily.com/rss/full",           "https://www.mortgagenewsdaily.com",  "headline_and_snippet", "not_required"),
    ("National Mortgage News",  "nmn",              "mortgage",       "https://www.nationalmortgagenews.com/feed",            "https://www.nationalmortgagenews.com","headline_only",       "pending"),
    # ── 2026-02-16: Added per spec for the upgraded RSS aggregator ──
    ("CNBC Real Estate",        "cnbc-realestate",  "national_trade", "https://www.cnbc.com/id/10000115/device/rss/rss.html", "https://www.cnbc.com/real-estate",   "headline_and_snippet", "pending"),
    ("MarketWatch Real Estate", "marketwatch-re",   "national_trade", "https://feeds.content.dowjones.io/public/rss/mw_realestate", "https://www.marketwatch.com/real-estate", "headline_and_snippet", "pending"),
    ("Commercial Observer",     "commercial-observer","national_trade","https://commercialobserver.com/feed/",                "https://commercialobserver.com",     "headline_and_snippet", "pending"),
    ("Multi-Housing News",      "multi-housing",    "national_trade", "https://www.multihousingnews.com/feed/",               "https://www.multihousingnews.com",   "headline_and_snippet", "pending"),
    ("Eye on Housing",          "eye-on-housing",   "industry_blog",  "https://eyeonhousing.org/feed/",                       "https://eyeonhousing.org",           "headline_and_snippet", "not_required"),
    ("ResiClub",                "resiclub",         "newsletter",     "https://www.resiclub.com/feed",                        "https://www.resiclub.com",           "headline_and_snippet", "not_required"),
    # 2026-02-16: Additional newsletter sources seeded for the newsletter category.
    ("Real Estate News",        "realestatenews",   "newsletter",     "https://www.realestatenews.com/feed",                  "https://www.realestatenews.com",     "headline_and_snippet", "pending"),
    ("Notebook by Brad Inman",  "brad-inman",       "newsletter",     "https://www.inman.com/category/brad-inman/feed/",      "https://www.inman.com/category/brad-inman", "headline_and_snippet", "pending"),
    # 2026-05-18: Major mainstream publisher. TheStreet's full feed is mixed-topic; the housing-specific feed is blocked. We use the full feed and rely on downstream filtering.
    ("TheStreet",               "thestreet",        "national_trade", "https://www.thestreet.com/.rss/full/",                  "https://www.thestreet.com/real-estate", "headline_and_snippet", "pending"),
    # 2026-05-18: Commercial real estate breadth.
    ("Bisnow",                  "bisnow",           "commercial_re",  "https://www.bisnow.com/rss",                            "https://www.bisnow.com",            "headline_and_snippet", "pending"),
    ("GlobeSt",                 "globest",          "commercial_re",  "https://feeds.feedblitz.com/globest/new-york",          "https://www.globest.com",            "headline_and_snippet", "pending"),
    # 2026-05-18: Housing & real estate Substacks (curated, on-topic).
    ("Real Estate Writer",      "real-estate-writer","industry_blog", "https://realestatewriter.substack.com/feed",            "https://realestatewriter.substack.com", "headline_and_snippet", "not_required"),
    ("Glenn Felson",            "glenn-felson",     "commercial_re",  "https://glennfelson.substack.com/feed",                 "https://glennfelson.substack.com",  "headline_and_snippet", "not_required"),
    ("Hate The Game",           "hate-the-game",    "data_research",  "https://hatethegame.substack.com/feed",                 "https://hatethegame.substack.com",  "headline_and_snippet", "not_required"),
    ("LP Lessons",              "lp-lessons",       "data_research",  "https://www.lplessons.co/feed",                         "https://www.lplessons.co",           "headline_and_snippet", "not_required"),
]


CATEGORIES = ["national_trade", "regional", "industry_blog", "data_research", "mortgage", "newsletter", "commercial_re"]


# Per-publisher keyword filters — applied to article TITLES at ingest time so
# that mixed-topic feeds only contribute housing-relevant items. Slug → list.
KEYWORD_FILTERS: dict[str, list[str]] = {
    "thestreet": [
        "housing", "mortgage", "mortgages", "real estate", "home price",
        "home prices", "home sales", "homebuyer", "homebuyers", "homeowner",
        "homeowners", "renter", "renters", "rental", "rentals", "landlord",
        "landlords", "apartment", "apartments", "condo", "condos", "listing",
        "listings", "realtor", "realtors", "builder", "builders", "homebuilding",
        "homebuilders", "construction", "property", "properties", "zillow",
        "redfin", "compass", "fannie mae", "freddie mac", "hud", "fha", "mls",
        "foreclosure", "foreclosures", "refinance", "refinancing", "refi",
        "interest rate", "interest rates", "fed rate", "fed cut", "fed hike",
        "house", "houses", "single-family", "multifamily", "multi-family",
        "affordability",
    ],
    # GlobeSt's Feedblitz feeds mix in ALM legal/litigation content (parent
    # company is American Lawyer Media). Filter to commercial real estate signal.
    "globest": [
        "real estate", "property", "properties", "office", "industrial",
        "retail", "multifamily", "apartment", "apartments", "hotel", "hotels",
        "warehouse", "warehouses", "logistics", "data center", "data centers",
        "lease", "leasing", "leased", "tenant", "tenants", "landlord",
        "development", "developer", "developers", "construction", "investor",
        "investors", "REIT", "reit", "loan", "loans", "financing", "mortgage",
        "broker", "brokerage", "deal", "deals", "acquisition", "acquires",
        "sells", "sold", "buys", "purchase", "purchased", "tower", "building",
        "campus", "portfolio", "sf", "square feet", "psf",
    ],
    # Hate The Game is ~70% housing — light filter to drop occasional off-topic
    # culture/book/tour posts.
    "hate-the-game": [
        "housing", "home", "homes", "house", "houses", "mortgage", "mortgages",
        "rent", "rental", "rentals", "real estate", "buyers", "buyer",
        "sellers", "seller", "price", "prices", "market", "fed", "rate",
        "rates", "inflation", "tax", "taxes", "bubble", "crash", "boom",
        "construction", "build", "builder", "builders", "investor", "investors",
        "wall street", "wealth", "neighborhood", "neighborhoods", "city",
        "cities", "region", "regional",
    ],
}
