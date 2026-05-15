#!/usr/bin/env python3
"""
Gold, Silver & Platinum Bullion Dashboard — main entry point.

Fetches prices, currency rates, news, runs analysis, and generates
the static HTML dashboard that gets deployed to GitHub Pages.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import REPORTS_DIR, DATA_DIR, TIMEZONE
from src.data_fetcher.price_fetcher import PriceFetcher
from src.data_fetcher.news_fetcher import NewsFetcher
from src.data_fetcher.currency_converter import CurrencyConverter
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.ai_analyzer import AIAnalyzer
from src.reporting.html_generator import HTMLReportGenerator

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_currency_summary(currencies: dict) -> str:
    """Format currency rates into a readable block for the AI prompt."""
    lines = ["💱 CURRENCY RATES (per 1 unit → INR):"]
    for key in sorted(currencies):
        cur = key.replace("_INR", "")
        lines.append(f"   {cur}/INR: ₹{currencies[key]:,.4f}")
    return "\n".join(lines)


def main():
    logger.info("═══ Gold-Silver-Platinum Dashboard — run started ═══")

    # ── 1.  Fetch data ───────────────────────────────────────
    logger.info("▸ Fetching metal prices …")
    price_fetcher = PriceFetcher()
    prices = price_fetcher.get_current_prices()
    logger.info(f"  Source: {prices.get('source', '?')}")

    logger.info("▸ Fetching currency rates …")
    currencies = prices.get('currencies', {})
    currency_summary = build_currency_summary(currencies)

    logger.info("▸ Fetching news …")
    news_fetcher = NewsFetcher()
    news = news_fetcher.get_news(max_articles=30)
    news_summary = news_fetcher.get_news_summary_for_ai()
    logger.info(f"  {len(news)} articles collected")

    logger.info("▸ Loading price history …")
    history = price_fetcher.get_historical_prices(years=2)
    logger.info(f"  {len(history)} weekly data-points")

    # ── 2.  Technical analysis ───────────────────────────────
    logger.info("▸ Running technical analysis …")
    tech = TechnicalAnalyzer()
    gold_tech = tech.analyze_trend(history, 'gold')
    silver_tech = tech.analyze_trend(history, 'silver')
    platinum_tech = tech.analyze_trend(history, 'platinum')
    technical_summary = tech.get_technical_summary(gold_tech, silver_tech, platinum_tech)

    # ── 3.  AI / rule-based recommendations ──────────────────
    logger.info("▸ Running AI analysis …")
    ai = AIAnalyzer()
    analysis = ai.analyze_all_metals(
        prices, news_summary, technical_summary, currency_summary
    )
    for metal in ('gold', 'silver', 'platinum'):
        rec = analysis[metal]
        logger.info(f"  {metal.upper()}: {rec['recommendation']} "
                     f"(buy {rec['confidence']['buy']}% / "
                     f"sell {rec['confidence']['sell']}% / "
                     f"hold {rec['confidence']['hold']}%) "
                     f"[{rec['source']}]")

    # ── 4.  Assemble full data payload ───────────────────────
    import pytz
    ist = pytz.timezone(TIMEZONE)
    now_ist = datetime.now(ist)

    payload = {
        'prices': prices,
        'currencies': currencies,
        'analysis': {
            'gold': analysis['gold'],
            'silver': analysis['silver'],
            'platinum': analysis['platinum'],
        },
        'technical': {
            'gold': gold_tech,
            'silver': silver_tech,
            'platinum': platinum_tech,
        },
        'news': news,
        'history': history,
        'timestamp': now_ist.isoformat(),
        'run_info': {
            'schedule': '4× daily (9 AM, 12 PM, 3 PM, 6 PM IST)',
            'timezone': TIMEZONE,
            'source': prices.get('source', 'unknown'),
        },
    }

    # ── 5.  Persist data JSON ────────────────────────────────
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data_file = DATA_DIR / "latest_data.json"
    with open(data_file, 'w') as f:
        json.dump(payload, f, indent=2, default=str)
    logger.info(f"  Data saved → {data_file}")

    # ── 6.  Generate HTML dashboard ──────────────────────────
    logger.info("▸ Generating HTML report …")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    generator = HTMLReportGenerator()
    html_path = generator.generate(payload, REPORTS_DIR / "index.html")
    logger.info(f"  Report saved → {html_path}")

    # Copy data JSON into reports/ for web access
    reports_data = REPORTS_DIR / "data"
    reports_data.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(data_file, reports_data / "latest_data.json")

    logger.info("═══ Run complete ═══")


if __name__ == "__main__":
    main()
