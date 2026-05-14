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
]


CATEGORIES = ["national_trade", "regional", "industry_blog", "data_research", "mortgage", "commercial_re"]
