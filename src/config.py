"""
Configuration settings for Gold, Silver & Platinum Bullion Dashboard.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_DIR = PROJECT_ROOT / "data"

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY", "")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
EXCHANGERATE_API_KEY = os.getenv("EXCHANGERATE_API_KEY", "")

# Metal settings (Indian bullion units — no GST, no making charges)
GOLD_UNIT = 10       # grams  (standard bullion bar reference)
SILVER_UNIT = 1000   # grams  (1 kg bar)
PLATINUM_UNIT = 1    # gram   (platinum quoted per gram in India)

# Conversion constant
TROY_OZ_TO_GRAM = 31.1035

# Metals tracked
METALS = ['gold', 'silver', 'platinum']

# API Endpoints (paid / key-based)
GOLDAPI_URL = "https://www.goldapi.io/api"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
EXCHANGERATE_URL = "https://v6.exchangerate-api.com/v6"

# Free API endpoints (no key required)
METALS_LIVE_URL = "https://api.metals.live/v1/spot"
FREE_EXCHANGE_URL = "https://api.exchangerate-api.com/v4/latest/USD"

# Currencies to track against INR
TRACKED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'SGD']

# RSS Feeds for news
RSS_FEEDS = [
    {
        "name": "Reuters Commodities",
        "url": "https://www.reutersagency.com/feed/?best-topics=commodities&post_type=best"
    },
    {
        "name": "Economic Times Gold",
        "url": "https://economictimes.indiatimes.com/markets/commodities/rssfeeds/49044718.cms"
    },
    {
        "name": "Moneycontrol Commodities",
        "url": "https://www.moneycontrol.com/rss/commodities.xml"
    },
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"
    },
    {
        "name": "Google News - Precious Metals",
        "url": "https://news.google.com/rss/search?q=precious+metals+gold+silver+platinum&hl=en-IN&gl=IN&ceid=IN:en"
    },
    {
        "name": "Google News - Global Economy",
        "url": "https://news.google.com/rss/search?q=global+economy+geopolitics+trade+war&hl=en-IN&gl=IN&ceid=IN:en"
    }
]

# News query sets for NewsAPI
NEWS_QUERIES = [
    "gold price OR gold bullion OR gold investment",
    "silver price OR silver bullion OR platinum price OR precious metals",
    "global economy OR geopolitics OR trade war OR sanctions OR tariff",
    "federal reserve OR interest rate OR central bank OR monetary policy"
]

# Historical data settings
HISTORY_YEARS = 5
WEEKLY_DATAPOINTS = True

# Timezone
TIMEZONE = "Asia/Kolkata"
