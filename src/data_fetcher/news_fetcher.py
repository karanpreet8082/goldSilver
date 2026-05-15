"""
News fetcher for precious-metals, global-affairs and market news.
Uses NewsAPI and RSS feeds — all free sources.
"""

import requests
import feedparser
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

from ..config import NEWSAPI_KEY, NEWSAPI_URL, RSS_FEEDS, NEWS_QUERIES, DATA_DIR

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Fetches categorised news from multiple free sources."""

    def __init__(self):
        self.cache_file = DATA_DIR / "news_cache.json"
        self._cached_news: Optional[List[Dict]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._load_cache()

    # ── cache ────────────────────────────────────────────────
    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self._cached_news = data.get('news', [])
                    ts = data.get('timestamp')
                    if ts:
                        self._cache_timestamp = datetime.fromisoformat(ts)
            except Exception as e:
                logger.warning(f"Failed to load news cache: {e}")

    def _save_cache(self, news: List[Dict]):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'news': news,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save news cache: {e}")

    # ── public API ───────────────────────────────────────────
    def get_news(self, max_articles: int = 30) -> List[Dict]:
        all_news: List[Dict] = []

        newsapi = self._fetch_from_newsapi()
        if newsapi:
            all_news.extend(newsapi)

        rss = self._fetch_from_rss_feeds()
        if rss:
            all_news.extend(rss)

        if not all_news and self._cached_news:
            logger.warning("Using cached news as fallback")
            return self._cached_news[:max_articles]

        all_news = self._deduplicate(all_news)
        all_news = sorted(all_news, key=lambda x: x.get('date', ''), reverse=True)
        all_news = all_news[:max_articles]

        self._save_cache(all_news)
        return all_news

    # ── NewsAPI ──────────────────────────────────────────────
    def _fetch_from_newsapi(self) -> List[Dict]:
        if not NEWSAPI_KEY or NEWSAPI_KEY == "your_newsapi_key_here":
            logger.warning("NewsAPI key not configured")
            return []

        articles: List[Dict] = []
        try:
            for query in NEWS_QUERIES:
                params = {
                    'q': query,
                    'apiKey': NEWSAPI_KEY,
                    'language': 'en',
                    'sortBy': 'publishedAt',
                    'pageSize': 8,
                }
                resp = requests.get(NEWSAPI_URL, params=params, timeout=10)
                if resp.status_code == 200:
                    for a in resp.json().get('articles', []):
                        articles.append({
                            'title': a.get('title', ''),
                            'description': a.get('description', '') or '',
                            'url': a.get('url', ''),
                            'source': a.get('source', {}).get('name', 'Unknown'),
                            'date': (a.get('publishedAt', '') or '')[:10],
                            'image': a.get('urlToImage', ''),
                            'category': self._categorize(
                                f"{a.get('title', '')} {a.get('description', '')}"
                            ),
                        })
                else:
                    logger.warning(f"NewsAPI status {resp.status_code}")
        except Exception as e:
            logger.error(f"NewsAPI fetch failed: {e}")
        return articles

    # ── RSS feeds ────────────────────────────────────────────
    def _fetch_from_rss_feeds(self) -> List[Dict]:
        articles: List[Dict] = []
        for feed_info in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_info['url'])
                for entry in feed.entries[:8]:
                    date_str = ''
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        date_str = datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d')
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        date_str = datetime(*entry.updated_parsed[:6]).strftime('%Y-%m-%d')

                    title = entry.get('title', '')
                    desc = entry.get('description', entry.get('summary', ''))
                    text = f"{title} {desc}".lower()

                    keywords = [
                        'gold', 'silver', 'platinum', 'precious metal', 'bullion',
                        'commodity', 'metal price', 'dollar', 'rupee', 'inflation',
                        'fed', 'interest rate', 'central bank', 'geopolit', 'war',
                        'trade war', 'sanction', 'tariff', 'economy', 'recession',
                    ]
                    if any(kw in text for kw in keywords):
                        articles.append({
                            'title': title,
                            'description': desc[:300],
                            'url': entry.get('link', ''),
                            'source': feed_info['name'],
                            'date': date_str,
                            'image': '',
                            'category': self._categorize(text),
                        })
            except Exception as e:
                logger.warning(f"RSS feed {feed_info['name']} failed: {e}")
        return articles

    # ── categorisation ───────────────────────────────────────
    def _categorize(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ['war', 'conflict', 'tension', 'military', 'geopolit',
                                 'sanction', 'tariff', 'trade war', 'nato']):
            return 'geopolitics'
        if any(w in t for w in ['fed', 'interest rate', 'central bank', 'monetary',
                                 'rbi', 'ecb', 'boj', 'rate cut', 'rate hike']):
            return 'central_bank'
        if any(w in t for w in ['dollar', 'usd', 'currency', 'forex', 'rupee',
                                 'yuan', 'euro', 'yen']):
            return 'currency'
        if any(w in t for w in ['inflation', 'cpi', 'price index', 'deflation']):
            return 'inflation'
        if any(w in t for w in ['demand', 'supply', 'import', 'export', 'production',
                                 'mining', 'etf inflow', 'etf outflow']):
            return 'supply_demand'
        if any(w in t for w in ['platinum', 'palladium']):
            return 'platinum'
        if any(w in t for w in ['gold', 'silver', 'bullion', 'precious metal']):
            return 'metals'
        return 'market'

    # ── dedup ────────────────────────────────────────────────
    def _deduplicate(self, articles: List[Dict]) -> List[Dict]:
        seen = set()
        unique = []
        for a in articles:
            key = a['title'].lower()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(a)
        return unique

    # ── AI-ready summary ─────────────────────────────────────
    def get_news_summary_for_ai(self) -> str:
        news = self.get_news(max_articles=20)
        if not news:
            return "No recent news available."

        by_cat: Dict[str, List[Dict]] = {}
        for a in news:
            by_cat.setdefault(a.get('category', 'market'), []).append(a)

        labels = {
            'geopolitics':  '🌍 Geopolitical / Global Affairs',
            'central_bank': '🏦 Central Bank & Interest Rates',
            'currency':     '💱 Currency / Forex',
            'inflation':    '📈 Inflation',
            'supply_demand':'⚖️ Supply & Demand',
            'metals':       '🥇 Precious Metals',
            'platinum':     '⚪ Platinum / PGMs',
            'market':       '📊 General Market',
        }

        parts = []
        for cat, articles in by_cat.items():
            parts.append(f"\n{labels.get(cat, cat.title())}:")
            for a in articles[:3]:
                parts.append(f"  - {a['title'][:120]}")
        return '\n'.join(parts)
