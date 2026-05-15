"""
Gold, Silver & Platinum price fetcher.
Uses multiple APIs with fallback support.
Prices are bullion spot rates (no GST, no making charges).
"""

import requests
import json
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from pathlib import Path
import random

from ..config import (
    GOLDAPI_KEY, GOLDAPI_URL, METALS_LIVE_URL, DATA_DIR,
    GOLD_UNIT, SILVER_UNIT, PLATINUM_UNIT, TROY_OZ_TO_GRAM
)
from .currency_converter import CurrencyConverter

logger = logging.getLogger(__name__)


class PriceFetcher:
    """Fetches gold, silver and platinum prices from multiple sources."""

    def __init__(self):
        self.currency_converter = CurrencyConverter()
        self.cache_file = DATA_DIR / "price_cache.json"
        self.history_file = DATA_DIR / "price_history.json"
        self._cached_prices = None
        self._cache_timestamp = None
        self._load_cache()

    # ── cache helpers ────────────────────────────────────────
    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self._cached_prices = data.get('prices')
                    ts = data.get('timestamp')
                    if ts:
                        self._cache_timestamp = datetime.fromisoformat(ts)
            except Exception as e:
                logger.warning(f"Failed to load price cache: {e}")

    def _save_cache(self, prices: Dict):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'prices': prices,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save price cache: {e}")

    # ── public API ───────────────────────────────────────────
    def get_current_prices(self) -> Dict:
        """
        Return current bullion spot prices for gold, silver, platinum.
        Both international (USD/oz) and Indian equivalent (INR/gram).
        """
        prices = self._fetch_from_goldapi()

        if not prices:
            prices = self._fetch_from_metals_live()

        if not prices:
            if self._cached_prices:
                logger.warning("Using cached prices as fallback")
                return self._cached_prices
            logger.warning("Using approximate fallback prices")
            return self._get_fallback_prices()

        self._save_cache(prices)
        self._update_history(prices)
        return prices

    # ── GoldAPI.io (paid-tier, 300 req/month free) ───────────
    def _fetch_from_goldapi(self) -> Optional[Dict]:
        if not GOLDAPI_KEY or GOLDAPI_KEY == "your_goldapi_key_here":
            logger.warning("GoldAPI key not configured")
            return None

        try:
            headers = {
                "x-access-token": GOLDAPI_KEY,
                "Content-Type": "application/json"
            }

            symbols = {
                'gold':     'XAU/USD',
                'silver':   'XAG/USD',
                'platinum': 'XPT/USD',
            }
            raw: Dict[str, Dict] = {}
            for metal, sym in symbols.items():
                resp = requests.get(f"{GOLDAPI_URL}/{sym}", headers=headers, timeout=10)
                resp.raise_for_status()
                raw[metal] = resp.json()

            return self._process_goldapi_data(raw)
        except Exception as e:
            logger.error(f"GoldAPI fetch failed: {e}")
            return None

    def _process_goldapi_data(self, raw: Dict[str, Dict]) -> Dict:
        usd_inr = self.currency_converter.get_usd_to_inr_rate()
        currencies = self.currency_converter.get_all_rates()

        def _metal_block(data, unit_g, unit_label):
            usd_oz = data.get('price', 0)
            per_gram_inr = (usd_oz / TROY_OZ_TO_GRAM) * usd_inr
            block = {
                'price_per_gram_inr': round(per_gram_inr, 2),
                'price_usd_oz': round(usd_oz, 2),
                'change_percent': round(data.get('chp', 0), 2),
                'change_value_usd': round(data.get('ch', 0), 2),
            }
            if unit_g == GOLD_UNIT:
                block['price_per_10g_inr'] = round(per_gram_inr * unit_g, 2)
            elif unit_g == SILVER_UNIT:
                block['price_per_kg_inr'] = round(per_gram_inr * unit_g, 2)
            return block

        gold_usd = raw['gold'].get('price', 0)
        silver_usd = raw['silver'].get('price', 0)
        gs_ratio = round(gold_usd / silver_usd, 2) if silver_usd else 0

        return {
            'gold': _metal_block(raw['gold'], GOLD_UNIT, '10g'),
            'silver': _metal_block(raw['silver'], SILVER_UNIT, 'kg'),
            'platinum': _metal_block(raw['platinum'], PLATINUM_UNIT, 'g'),
            'currencies': currencies,
            'gold_silver_ratio': gs_ratio,
            'timestamp': datetime.now().isoformat(),
            'source': 'GoldAPI',
        }

    # ── metals.live (free, no key) ───────────────────────────
    def _fetch_from_metals_live(self) -> Optional[Dict]:
        try:
            resp = requests.get(METALS_LIVE_URL, timeout=10, verify=False)
            resp.raise_for_status()
            data = resp.json()

            usd_inr = self.currency_converter.get_usd_to_inr_rate()
            currencies = self.currency_converter.get_all_rates()

            spot: Dict[str, float] = {}
            for item in data:
                for key in ('gold', 'silver', 'platinum'):
                    if key in item:
                        spot[key] = item[key]

            if not (spot.get('gold') and spot.get('silver')):
                return None

            def _block(usd_oz, unit_g, unit_key):
                per_gram = (usd_oz / TROY_OZ_TO_GRAM) * usd_inr
                b = {
                    'price_per_gram_inr': round(per_gram, 2),
                    'price_usd_oz': round(usd_oz, 2),
                    'change_percent': 0,
                    'change_value_usd': 0,
                }
                if unit_key == '10g':
                    b['price_per_10g_inr'] = round(per_gram * unit_g, 2)
                elif unit_key == 'kg':
                    b['price_per_kg_inr'] = round(per_gram * unit_g, 2)
                return b

            gold_usd = spot['gold']
            silver_usd = spot['silver']
            plat_usd = spot.get('platinum', 950)

            return {
                'gold': _block(gold_usd, GOLD_UNIT, '10g'),
                'silver': _block(silver_usd, SILVER_UNIT, 'kg'),
                'platinum': _block(plat_usd, PLATINUM_UNIT, 'g'),
                'currencies': currencies,
                'gold_silver_ratio': round(gold_usd / silver_usd, 2) if silver_usd else 0,
                'timestamp': datetime.now().isoformat(),
                'source': 'metals.live',
            }
        except Exception as e:
            logger.error(f"metals.live fetch failed: {e}")
        return None

    # ── fallback (hardcoded approximations) ──────────────────
    def _get_fallback_prices(self) -> Dict:
        usd_inr = self.currency_converter.get_usd_to_inr_rate()
        currencies = self.currency_converter.get_all_rates()

        approx = {'gold': 2400, 'silver': 30, 'platinum': 980}

        def _block(usd_oz, unit_g, unit_key):
            per_gram = (usd_oz / TROY_OZ_TO_GRAM) * usd_inr
            b = {
                'price_per_gram_inr': round(per_gram, 2),
                'price_usd_oz': usd_oz,
                'change_percent': 0,
                'change_value_usd': 0,
            }
            if unit_key == '10g':
                b['price_per_10g_inr'] = round(per_gram * unit_g, 2)
            elif unit_key == 'kg':
                b['price_per_kg_inr'] = round(per_gram * unit_g, 2)
            return b

        return {
            'gold': _block(approx['gold'], GOLD_UNIT, '10g'),
            'silver': _block(approx['silver'], SILVER_UNIT, 'kg'),
            'platinum': _block(approx['platinum'], PLATINUM_UNIT, 'g'),
            'currencies': currencies,
            'gold_silver_ratio': round(approx['gold'] / approx['silver'], 2),
            'timestamp': datetime.now().isoformat(),
            'source': 'fallback',
        }

    # ── history tracking ─────────────────────────────────────
    def _update_history(self, prices: Dict):
        try:
            history = self._load_history()
            today = datetime.now().strftime('%Y-%m-%d')
            week_num = datetime.now().strftime('%Y-W%V')

            entry = {
                'date': today,
                'week': week_num,
                'gold_10g': prices['gold'].get('price_per_10g_inr', 0),
                'silver_kg': prices['silver'].get('price_per_kg_inr', 0),
                'platinum_g': prices['platinum'].get('price_per_gram_inr', 0),
                'gold_usd_oz': prices['gold']['price_usd_oz'],
                'silver_usd_oz': prices['silver']['price_usd_oz'],
                'platinum_usd_oz': prices['platinum']['price_usd_oz'],
            }

            existing_weeks = {h['week'] for h in history}
            if week_num not in existing_weeks:
                history.append(entry)
            else:
                for i, h in enumerate(history):
                    if h['week'] == week_num:
                        history[i] = entry
                        break

            history = sorted(history, key=lambda x: x['date'])[-260:]
            with open(self.history_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to update price history: {e}")

    def _load_history(self) -> List[Dict]:
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def get_historical_prices(self, years: int = 1) -> List[Dict]:
        history = self._load_history()
        if not history:
            return self._generate_sample_history(years)
        weeks_needed = years * 52
        return history[-weeks_needed:]

    def _generate_sample_history(self, years: int) -> List[Dict]:
        history = []
        base_gold = 65000
        base_silver = 75000
        base_plat = 3100

        start = date.today() - timedelta(days=years * 365)
        current = start

        while current <= date.today():
            base_gold *= (1 + random.uniform(-0.02, 0.02))
            base_silver *= (1 + random.uniform(-0.03, 0.03))
            base_plat *= (1 + random.uniform(-0.025, 0.025))

            base_gold = max(50000, min(100000, base_gold))
            base_silver = max(50000, min(130000, base_silver))
            base_plat = max(2000, min(5000, base_plat))

            history.append({
                'date': current.isoformat(),
                'week': current.strftime('%Y-W%V'),
                'gold_10g': round(base_gold, 2),
                'silver_kg': round(base_silver, 2),
                'platinum_g': round(base_plat, 2),
                'gold_usd_oz': round(base_gold / 83 * TROY_OZ_TO_GRAM / 10, 2),
                'silver_usd_oz': round(base_silver / 83 * TROY_OZ_TO_GRAM / 1000, 2),
                'platinum_usd_oz': round(base_plat / 83 * TROY_OZ_TO_GRAM, 2),
            })
            current += timedelta(days=7)

        return history
