"""
Multi-currency converter with focus on INR cross-rates.
Fetches rates for major currencies against INR to analyse
whether metals are under/over-performing in Indian markets.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path

from ..config import (
    EXCHANGERATE_API_KEY, EXCHANGERATE_URL,
    FREE_EXCHANGE_URL, DATA_DIR, TRACKED_CURRENCIES
)

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """Fetches multi-currency rates with caching."""

    def __init__(self):
        self.cache_file = DATA_DIR / "exchange_rate_cache.json"
        self.cache_duration = timedelta(hours=6)
        self._cached_rates: Optional[Dict[str, float]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._load_cache()

    # ── cache helpers ────────────────────────────────────────
    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self._cached_rates = data.get('rates')
                    ts = data.get('timestamp')
                    if ts:
                        self._cache_timestamp = datetime.fromisoformat(ts)
            except Exception as e:
                logger.warning(f"Failed to load rate cache: {e}")

    def _save_cache(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'rates': self._cached_rates,
                    'timestamp': self._cache_timestamp.isoformat() if self._cache_timestamp else None
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save rate cache: {e}")

    def _is_cache_valid(self) -> bool:
        if self._cached_rates is None or self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self.cache_duration

    # ── public API ───────────────────────────────────────────
    def get_all_rates(self) -> Dict[str, float]:
        """Return {CUR_INR: rate, …} for every tracked currency."""
        if self._is_cache_valid():
            return self._cached_rates

        rates = self._fetch_rates()
        if rates:
            self._cached_rates = rates
            self._cache_timestamp = datetime.now()
            self._save_cache()
            return rates

        if self._cached_rates:
            logger.warning("Using expired cached rates")
            return self._cached_rates

        return self._get_fallback_rates()

    def get_usd_to_inr_rate(self) -> float:
        """Backward-compatible shortcut."""
        return self.get_all_rates().get('USD_INR', 83.50)

    def convert_usd_to_inr(self, usd_amount: float) -> float:
        return usd_amount * self.get_usd_to_inr_rate()

    # ── fetching ─────────────────────────────────────────────
    def _fetch_rates(self) -> Optional[Dict[str, float]]:
        rates = self._fetch_from_paid_api()
        if rates:
            return rates
        return self._fetch_from_free_api()

    def _fetch_from_paid_api(self) -> Optional[Dict[str, float]]:
        if not EXCHANGERATE_API_KEY or EXCHANGERATE_API_KEY == "your_exchangerate_key_here":
            return None
        try:
            url = f"{EXCHANGERATE_URL}/{EXCHANGERATE_API_KEY}/latest/USD"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get('result') == 'success':
                return self._extract_inr_rates(data.get('conversion_rates', {}))
        except Exception as e:
            logger.error(f"Paid exchange-rate API failed: {e}")
        return None

    def _fetch_from_free_api(self) -> Optional[Dict[str, float]]:
        try:
            resp = requests.get(FREE_EXCHANGE_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_inr_rates(data.get('rates', {}))
        except Exception as e:
            logger.error(f"Free exchange-rate API failed: {e}")
        return None

    def _extract_inr_rates(self, usd_rates: Dict) -> Optional[Dict[str, float]]:
        """Convert USD-based rates to 'X_INR' cross-rates."""
        inr_rate = usd_rates.get('INR')
        if not inr_rate:
            return None

        result: Dict[str, float] = {}
        for cur in TRACKED_CURRENCIES:
            foreign = usd_rates.get(cur)
            if foreign and foreign > 0:
                result[f'{cur}_INR'] = round(inr_rate / foreign, 4)

        # Always include USD_INR explicitly
        result['USD_INR'] = round(inr_rate, 4)
        return result

    def _get_fallback_rates(self) -> Dict[str, float]:
        return {
            'USD_INR': 83.50,
            'EUR_INR': 91.00,
            'GBP_INR': 106.00,
            'JPY_INR': 0.56,
            'CHF_INR': 94.00,
            'AUD_INR': 55.00,
            'CAD_INR': 62.00,
            'SGD_INR': 63.00,
        }
