"""
Technical analysis for gold, silver and platinum price trends.
Provides price-based signals consumed by the AI analyser.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Analyses price trends and technical indicators for precious metals."""

    def analyze_trend(self, history: List[Dict], metal: str = 'gold') -> Dict:
        """
        Analyse price trend for a metal.

        Args:
            history: weekly price entries from PriceFetcher
            metal: 'gold', 'silver' or 'platinum'
        """
        key_map = {
            'gold': 'gold_10g',
            'silver': 'silver_kg',
            'platinum': 'platinum_g',
        }
        price_key = key_map.get(metal, 'gold_10g')

        if not history or len(history) < 4:
            return self._neutral()

        prices = [h[price_key] for h in history if price_key in h]
        if len(prices) < 4:
            return self._neutral()

        ma_short = self._ma(prices, min(4, len(prices)))
        ma_long = self._ma(prices, min(12, len(prices)))
        cur = prices[-1]

        signals = []
        score = 0.0

        # Price vs short MA
        if cur > ma_short:
            signals.append("Price above 4-week moving average (bullish)")
            score += 1
        else:
            signals.append("Price below 4-week moving average (bearish)")
            score -= 1

        # Price vs long MA
        if cur > ma_long:
            signals.append("Price above 12-week moving average (bullish)")
            score += 1
        else:
            signals.append("Price below 12-week moving average (bearish)")
            score -= 1

        # Golden / Death cross
        if ma_short > ma_long:
            signals.append("Short-term MA above long-term MA (uptrend)")
            score += 1
        else:
            signals.append("Short-term MA below long-term MA (downtrend)")
            score -= 1

        # 4-week momentum
        if len(prices) >= 4:
            chg = (prices[-1] - prices[-4]) / prices[-4] * 100
            if chg > 2:
                signals.append(f"Strong momentum: +{chg:.1f}% in 4 weeks")
                score += 1
            elif chg < -2:
                signals.append(f"Weak momentum: {chg:.1f}% in 4 weeks")
                score -= 1
            else:
                signals.append(f"Sideways: {chg:+.1f}% in 4 weeks")

        # Support / Resistance
        lookback = prices[-12:] if len(prices) >= 12 else prices
        support = min(lookback)
        resistance = max(lookback)
        rng = resistance - support
        if rng > 0:
            pos = (cur - support) / rng
            if pos < 0.2:
                signals.append("Near support — potential buy zone")
                score += 0.5
            elif pos > 0.8:
                signals.append("Near resistance — potential sell zone")
                score -= 0.5

        trend = 'bullish' if score >= 2 else ('bearish' if score <= -2 else 'neutral')
        strength = min(100, max(0, (score + 4) * 12.5))

        return {
            'trend': trend,
            'strength': round(strength),
            'signals': signals,
            'support': round(support, 2),
            'resistance': round(resistance, 2),
            'current_price': cur,
            'ma_short': round(ma_short, 2),
            'ma_long': round(ma_long, 2),
            'trend_score': score,
        }

    # ── helpers ──────────────────────────────────────────────
    @staticmethod
    def _ma(prices: List[float], period: int) -> float:
        if len(prices) < period:
            return sum(prices) / len(prices)
        return sum(prices[-period:]) / period

    @staticmethod
    def _neutral() -> Dict:
        return {
            'trend': 'neutral', 'strength': 50,
            'signals': ['Insufficient data for trend analysis'],
            'support': 0, 'resistance': 0, 'current_price': 0,
            'ma_short': 0, 'ma_long': 0, 'trend_score': 0,
        }

    def get_technical_summary(
        self,
        gold_analysis: Dict,
        silver_analysis: Dict,
        platinum_analysis: Dict,
    ) -> str:
        """Formatted technical summary for the AI prompt."""
        units = {'gold': '10g', 'silver': 'kg', 'platinum': 'g'}
        emojis = {'gold': '🥇', 'silver': '🥈', 'platinum': '⚪'}

        lines = ["📊 TECHNICAL ANALYSIS:", ""]
        for metal, analysis in [('gold', gold_analysis),
                                ('silver', silver_analysis),
                                ('platinum', platinum_analysis)]:
            e = emojis[metal]
            u = units[metal]
            lines.append(f"{e} {metal.upper()}:")
            lines.append(f"   Trend: {analysis['trend'].upper()} "
                         f"(strength: {analysis['strength']}%)")
            lines.append(f"   Current: ₹{analysis.get('current_price', 0):,.0f}/{u}")
            lines.append(f"   Support: ₹{analysis['support']:,.0f} | "
                         f"Resistance: ₹{analysis['resistance']:,.0f}")
            for sig in analysis['signals'][:3]:
                lines.append(f"   • {sig}")
            lines.append("")

        return '\n'.join(lines)
