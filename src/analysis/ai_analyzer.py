"""
AI-powered analyser using Google Gemini API.
Generates BUY / SELL / HOLD recommendations with confidence scores
for gold, silver and platinum.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Optional

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from ..config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

METAL_LABELS = {
    'gold':     ('Gold',     '10 grams',  'price_per_10g_inr'),
    'silver':   ('Silver',   '1 kilogram', 'price_per_kg_inr'),
    'platinum': ('Platinum', '1 gram',     'price_per_gram_inr'),
}


class AIAnalyzer:
    """AI-powered market analyser using Google Gemini."""

    def __init__(self):
        self.model = None
        self._setup_gemini()

    def _setup_gemini(self):
        if not genai:
            logger.error("google-generativeai package not installed")
            return
        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
            logger.warning("Gemini API key not configured")
            return
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            logger.info("Gemini API initialised")
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")

    # ── single-metal analysis ────────────────────────────────
    def analyze(
        self,
        prices: Dict,
        news_summary: str,
        technical_summary: str,
        currency_summary: str,
        metal: str = 'gold',
    ) -> Dict:
        if not self.model:
            return self._rule_based(prices, technical_summary, metal)
        try:
            return self._ai_analysis(prices, news_summary, technical_summary, currency_summary, metal)
        except Exception as e:
            logger.error(f"AI analysis failed for {metal}: {e}")
            return self._rule_based(prices, technical_summary, metal)

    def _ai_analysis(self, prices, news_summary, technical_summary, currency_summary, metal):
        label, unit, key = METAL_LABELS[metal]
        md = prices.get(metal, {})
        unit_price = md.get(key, md.get('price_per_gram_inr', 0))
        currencies = prices.get('currencies', {})
        usd_inr = currencies.get('USD_INR', 83.5)
        gs_ratio = prices.get('gold_silver_ratio', 0)

        prompt = f"""You are a precious metals investment analyst. Analyse the data for **{label}** and provide a recommendation.

CURRENT PRICE DATA:
- {label} Price: ₹{unit_price:,.2f} per {unit}
- Price per gram: ₹{md.get('price_per_gram_inr', 0):,.2f}
- USD Price: ${md.get('price_usd_oz', 0):.2f} per troy ounce
- Daily Change: {md.get('change_percent', 0):.2f}%
- Gold/Silver Ratio: {gs_ratio}

CURRENCY CONTEXT:
{currency_summary}

{technical_summary}

RECENT NEWS & EVENTS:
{news_summary}

Based on this, provide your recommendation in **pure JSON** (no markdown):
{{
    "recommendation": "BUY" or "SELL" or "HOLD",
    "confidence": {{
        "buy": <0-100>,
        "sell": <0-100>,
        "hold": <0-100>
    }},
    "summary": "<3-4 sentences with reasoning, mentioning key factors>"
}}

Rules:
- Confidence must sum to 100
- Consider technical trend, news sentiment, currency movements, and global events
- Factor in whether Indian prices are over/under-performing international prices
- This is for bullion bars (no jewellery, no GST)
"""
        resp = self.model.generate_content(prompt)
        text = resp.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        text = text.strip()

        result = json.loads(text)
        rec = result.get('recommendation', 'HOLD').upper()
        if rec not in ('BUY', 'SELL', 'HOLD'):
            rec = 'HOLD'

        conf = result.get('confidence', {})
        b = max(0, min(100, int(conf.get('buy', 33))))
        s = max(0, min(100, int(conf.get('sell', 33))))
        h = max(0, min(100, int(conf.get('hold', 34))))
        total = b + s + h
        if total > 0:
            b = round(b * 100 / total)
            s = round(s * 100 / total)
            h = 100 - b - s

        return {
            'metal': metal,
            'recommendation': rec,
            'confidence': {'buy': b, 'sell': s, 'hold': h},
            'summary': result.get('summary', 'Analysis completed.'),
            'timestamp': datetime.now().isoformat(),
            'source': 'gemini-ai',
        }

    # ── rule-based fallback ──────────────────────────────────
    def _rule_based(self, prices, technical_summary, metal):
        md = prices.get(metal, {})
        chg = md.get('change_percent', 0)

        score = 0
        reasons = []

        if chg > 1:
            score += 2; reasons.append(f"Strong daily gain of {chg:.1f}%")
        elif chg > 0:
            score += 1; reasons.append(f"Positive daily movement of {chg:.1f}%")
        elif chg < -1:
            score -= 2; reasons.append(f"Significant daily drop of {chg:.1f}%")
        elif chg < 0:
            score -= 1; reasons.append(f"Slight decline of {chg:.1f}%")

        ts = technical_summary.lower()
        if 'bullish' in ts:
            score += 2; reasons.append("Technical indicators show bullish trend")
        elif 'bearish' in ts:
            score -= 2; reasons.append("Technical indicators show bearish trend")
        if 'above' in ts and 'moving average' in ts:
            score += 1; reasons.append("Price above key moving averages")
        elif 'below' in ts and 'moving average' in ts:
            score -= 1; reasons.append("Price below key moving averages")

        if score >= 2:
            rec = 'BUY'
            b = min(65, 40 + score * 8)
            s = max(10, 25 - score * 5)
            h = 100 - b - s
        elif score <= -2:
            rec = 'SELL'
            s = min(65, 40 + abs(score) * 8)
            b = max(10, 25 - abs(score) * 5)
            h = 100 - b - s
        else:
            rec = 'HOLD'
            h, b, s = 50, 25, 25

        label = METAL_LABELS[metal][0]
        direction = 'positive' if score > 0 else ('negative' if score < 0 else 'mixed')
        summary = (f"{label} is showing {direction} signals. "
                   + ". ".join(reasons[:2]) + ". "
                   + f"Recommendation: {rec} with moderate confidence based on current indicators.")

        return {
            'metal': metal,
            'recommendation': rec,
            'confidence': {'buy': b, 'sell': s, 'hold': h},
            'summary': summary,
            'timestamp': datetime.now().isoformat(),
            'source': 'rule-based',
        }

    # ── analyse all three metals ─────────────────────────────
    def analyze_all_metals(
        self,
        prices: Dict,
        news_summary: str,
        technical_summary: str,
        currency_summary: str,
    ) -> Dict:
        results = {}
        for metal in ('gold', 'silver', 'platinum'):
            results[metal] = self.analyze(
                prices, news_summary, technical_summary, currency_summary, metal
            )
        results['timestamp'] = datetime.now().isoformat()
        return results
