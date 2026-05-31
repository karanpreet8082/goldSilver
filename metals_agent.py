#!/usr/bin/env python3
"""
Autonomous precious-metals trading and advisory agent.

Outputs BUY/SELL/HOLD signals for Gold, Silver, and Platinum using:
1) Gold/Silver ratio mean-reversion
2) EMA(20/50) + MACD momentum/trend
3) RSI(14) reversal layer
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

# Ensure project root is importable when running script directly
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_fetcher.price_fetcher import PriceFetcher

logger = logging.getLogger("metals_agent")


class AgentDataError(Exception):
    """Raised when market data is missing or malformed."""


@dataclass
class SignalResult:
    action: str
    score: float
    reason: str
    indicators: Dict[str, float]


class DataIngestion:
    """Fetches and validates current/historical metal prices."""

    def __init__(self, price_fetcher: PriceFetcher | None = None):
        self.price_fetcher = price_fetcher or PriceFetcher()

    def load_market_data(self, years: int = 2) -> Tuple[Dict[str, Any], pd.DataFrame]:
        current = self.price_fetcher.get_current_prices()
        history = self.price_fetcher.get_historical_prices(years=years)

        validated_current = self._validate_current(current)
        history_df = self._build_history_frame(history, validated_current)

        if not self._is_positive(validated_current.get("platinum")):
            logger.warning("Platinum missing in main feed; trying yfinance fallback")
            platinum_price, platinum_series = self._fetch_platinum_from_yfinance()
            validated_current["platinum"] = platinum_price
            history_df["platinum"] = history_df["platinum"].fillna(platinum_series)

        if history_df[["gold", "silver", "platinum"]].isna().any().any():
            history_df = history_df.ffill().bfill()

        if history_df.empty:
            raise AgentDataError("Historical data frame is empty after preprocessing.")

        return validated_current, history_df

    @staticmethod
    def _is_positive(value: Any) -> bool:
        return isinstance(value, (int, float)) and value > 0

    def _validate_current(self, current: Dict[str, Any]) -> Dict[str, float]:
        if not isinstance(current, dict):
            raise AgentDataError("Current price payload must be a dictionary.")

        mapped = {
            "gold": current.get("gold", {}).get("price_usd_oz"),
            "silver": current.get("silver", {}).get("price_usd_oz"),
            "platinum": current.get("platinum", {}).get("price_usd_oz"),
        }

        for metal in ("gold", "silver"):
            if not self._is_positive(mapped.get(metal)):
                raise AgentDataError(f"Missing or invalid live {metal} price.")

        if not self._is_positive(mapped.get("platinum")):
            logger.warning("Live platinum price unavailable or invalid")

        return mapped

    def _build_history_frame(
        self,
        history: List[Dict[str, Any]],
        current: Dict[str, float],
    ) -> pd.DataFrame:
        if not isinstance(history, list):
            raise AgentDataError("Historical price payload must be a list.")

        rows: List[Dict[str, Any]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            row = {
                "date": item.get("date"),
                "gold": item.get("gold_usd_oz"),
                "silver": item.get("silver_usd_oz"),
                "platinum": item.get("platinum_usd_oz"),
            }
            rows.append(row)

        if not rows:
            raise AgentDataError("Historical prices are missing.")

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date")

        for metal in ("gold", "silver", "platinum"):
            df[metal] = pd.to_numeric(df[metal], errors="coerce")

        latest_row = {
            "date": pd.Timestamp.now(tz="UTC").tz_localize(None),
            "gold": current["gold"],
            "silver": current["silver"],
            "platinum": current.get("platinum"),
        }
        df = pd.concat([df, pd.DataFrame([latest_row])], ignore_index=True)
        return df.tail(520).reset_index(drop=True)

    def _fetch_platinum_from_yfinance(self) -> Tuple[float, pd.Series]:
        try:
            import yfinance as yf
        except Exception as exc:
            raise AgentDataError(
                "Platinum missing and yfinance fallback is unavailable. "
                "Install yfinance or restore platinum feed."
            ) from exc

        ticker = yf.Ticker("PL=F")
        hist = ticker.history(period="2y", interval="1d", timeout=10)
        if hist.empty or "Close" not in hist:
            raise AgentDataError("yfinance returned no platinum history (PL=F).")

        close = hist["Close"].dropna()
        if close.empty:
            raise AgentDataError("Platinum close series from yfinance is empty.")

        current_price = float(close.iloc[-1])
        series = close.copy()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        series.name = "platinum"
        return current_price, series


class StrategyEngine:
    """Computes weighted BUY/SELL/HOLD decisions for each metal."""

    TREND_WEIGHT = 0.45
    RSI_WEIGHT = 0.30
    RATIO_WEIGHT = 0.25

    def evaluate(self, history_df: pd.DataFrame) -> Dict[str, SignalResult]:
        if history_df.empty:
            raise AgentDataError("No history available for strategy evaluation.")

        ratio_series = history_df["gold"] / history_df["silver"]
        ratio_now = float(ratio_series.iloc[-1])
        ratio_low = float(ratio_series.quantile(0.20))
        ratio_high = float(ratio_series.quantile(0.80))

        ratio_bias = self._ratio_bias(ratio_now, ratio_low, ratio_high)
        results: Dict[str, SignalResult] = {}

        for metal in ("gold", "silver", "platinum"):
            indicators = self._indicators(history_df[metal])
            trend_component, trend_reason = self._trend_component(indicators)
            rsi_component, rsi_reason = self._rsi_component(indicators["rsi"])
            ratio_component, ratio_reason = self._ratio_component(metal, ratio_bias, ratio_now)

            total_score = (
                self.TREND_WEIGHT * trend_component
                + self.RSI_WEIGHT * rsi_component
                + self.RATIO_WEIGHT * ratio_component
            )
            action = self._action_from_score(total_score)

            reason = f"{trend_reason}. {rsi_reason}. {ratio_reason}."
            results[metal] = SignalResult(
                action=action,
                score=round(total_score, 3),
                reason=reason,
                indicators=indicators,
            )

        return results

    def _indicators(self, prices: pd.Series) -> Dict[str, float]:
        series = pd.to_numeric(prices, errors="coerce").dropna()
        if len(series) < 60:
            raise AgentDataError("At least 60 data points are required for robust indicators.")

        ema20 = series.ewm(span=20, adjust=False).mean()
        ema50 = series.ewm(span=50, adjust=False).mean()

        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        macd_signal = macd.ewm(span=9, adjust=False).mean()

        delta = series.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        if pd.isna(rsi.iloc[-1]):
            rsi_value = 50.0
        else:
            rsi_value = float(rsi.iloc[-1])

        return {
            "price": float(series.iloc[-1]),
            "ema20": float(ema20.iloc[-1]),
            "ema50": float(ema50.iloc[-1]),
            "macd": float(macd.iloc[-1]),
            "macd_signal": float(macd_signal.iloc[-1]),
            "rsi": round(rsi_value, 2),
        }

    @staticmethod
    def _ratio_bias(ratio_now: float, ratio_low: float, ratio_high: float) -> str:
        upper = max(80.0, ratio_high)
        lower = min(60.0, ratio_low)
        if ratio_now >= upper:
            return "favor_silver"
        if ratio_now <= lower:
            return "favor_gold"
        return "neutral"

    @staticmethod
    def _trend_component(indicators: Dict[str, float]) -> Tuple[float, str]:
        ema_signal = 1.0 if indicators["ema20"] > indicators["ema50"] else -1.0
        macd_signal = 1.0 if indicators["macd"] > indicators["macd_signal"] else -1.0
        component = (ema_signal + macd_signal) / 2
        reason = (
            f"Trend {'bullish' if component > 0 else 'bearish'} "
            f"(EMA20 {indicators['ema20']:.2f} vs EMA50 {indicators['ema50']:.2f}, "
            f"MACD {indicators['macd']:.4f} vs signal {indicators['macd_signal']:.4f})"
        )
        return component, reason

    @staticmethod
    def _rsi_component(rsi: float) -> Tuple[float, str]:
        if rsi < 30:
            return 1.0, f"RSI oversold at {rsi:.2f}"
        if rsi < 40:
            return 0.4, f"RSI mildly oversold at {rsi:.2f}"
        if rsi > 70:
            return -1.0, f"RSI overbought at {rsi:.2f}"
        if rsi > 60:
            return -0.4, f"RSI mildly overbought at {rsi:.2f}"
        return 0.0, f"RSI neutral at {rsi:.2f}"

    @staticmethod
    def _ratio_component(metal: str, ratio_bias: str, ratio_now: float) -> Tuple[float, str]:
        if metal == "platinum":
            return 0.0, "Ratio strategy not applicable to platinum"

        if ratio_bias == "favor_silver":
            if metal == "silver":
                return 1.0, f"Gold/Silver ratio high at {ratio_now:.2f}; favors silver mean reversion"
            return -1.0, f"Gold/Silver ratio high at {ratio_now:.2f}; less favorable for gold"

        if ratio_bias == "favor_gold":
            if metal == "gold":
                return 1.0, f"Gold/Silver ratio low at {ratio_now:.2f}; favors gold mean reversion"
            return -1.0, f"Gold/Silver ratio low at {ratio_now:.2f}; less favorable for silver"

        return 0.0, f"Gold/Silver ratio neutral at {ratio_now:.2f}"

    @staticmethod
    def _action_from_score(score: float) -> str:
        if score >= 0.35:
            return "BUY"
        if score <= -0.35:
            return "SELL"
        return "HOLD"


class MetalsLedger:
    """Simple JSON-backed portfolio with holdings, cash and trade logs."""

    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.ledger = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        if self.ledger_path.exists():
            with open(self.ledger_path, "r", encoding="utf-8") as fh:
                return json.load(fh)

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "cash_balance_usd": 100_000.0,
            "holdings": {
                "gold": {"quantity_oz": 10.0, "avg_price_usd_oz": 2200.0},
                "silver": {"quantity_oz": 300.0, "avg_price_usd_oz": 27.0},
                "platinum": {"quantity_oz": 30.0, "avg_price_usd_oz": 1000.0},
            },
            "trades": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def apply_signals(
        self,
        prices: Dict[str, float],
        signals: Dict[str, SignalResult],
        trade_size_oz: Dict[str, float] | None = None,
    ) -> Dict[str, Any]:
        trade_size_oz = trade_size_oz or {"gold": 1.0, "silver": 20.0, "platinum": 2.0}
        cash = float(self.ledger["cash_balance_usd"])
        holdings = self.ledger["holdings"]
        trades: List[Dict[str, Any]] = self.ledger["trades"]

        for metal in ("gold", "silver", "platinum"):
            action = signals[metal].action
            qty = float(trade_size_oz[metal])
            px = float(prices[metal])
            current_qty = float(holdings[metal]["quantity_oz"])
            avg_px = float(holdings[metal]["avg_price_usd_oz"])

            if action == "BUY" and cash >= qty * px:
                new_qty = current_qty + qty
                new_avg = ((current_qty * avg_px) + (qty * px)) / max(new_qty, 1e-9)
                holdings[metal]["quantity_oz"] = round(new_qty, 6)
                holdings[metal]["avg_price_usd_oz"] = round(new_avg, 6)
                cash -= qty * px
                trades.append(self._trade_row("BUY", metal, qty, px))
            elif action == "SELL" and current_qty > 0:
                sell_qty = min(qty, current_qty)
                holdings[metal]["quantity_oz"] = round(current_qty - sell_qty, 6)
                cash += sell_qty * px
                trades.append(self._trade_row("SELL", metal, sell_qty, px))

        self.ledger["cash_balance_usd"] = round(cash, 2)
        self.ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.ledger["valuation"] = self._valuation(prices)
        self._save()
        return self.ledger

    def _valuation(self, prices: Dict[str, float]) -> Dict[str, float]:
        holdings = self.ledger["holdings"]
        market_value = 0.0
        unrealized_pnl = 0.0
        for metal in ("gold", "silver", "platinum"):
            qty = float(holdings[metal]["quantity_oz"])
            avg_px = float(holdings[metal]["avg_price_usd_oz"])
            cur_px = float(prices[metal])
            market_value += qty * cur_px
            unrealized_pnl += qty * (cur_px - avg_px)

        total_equity = market_value + float(self.ledger["cash_balance_usd"])
        return {
            "market_value_usd": round(market_value, 2),
            "unrealized_pnl_usd": round(unrealized_pnl, 2),
            "total_equity_usd": round(total_equity, 2),
        }

    @staticmethod
    def _trade_row(side: str, metal: str, qty: float, px: float) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "side": side,
            "metal": metal,
            "quantity_oz": round(qty, 6),
            "price_usd_oz": round(px, 4),
            "notional_usd": round(qty * px, 2),
        }

    def _save(self) -> None:
        with open(self.ledger_path, "w", encoding="utf-8") as fh:
            json.dump(self.ledger, fh, indent=2)


def build_execution_summary(
    signals: Dict[str, SignalResult],
    ledger: Dict[str, Any],
) -> Dict[str, Any]:
    signal_block = {
        metal.upper(): {
            "action": res.action,
            "score": res.score,
            "reason": res.reason,
            "indicators": res.indicators,
        }
        for metal, res in signals.items()
    }
    return {
        "signals": signal_block,
        "portfolio": {
            "cash_balance_usd": ledger["cash_balance_usd"],
            "holdings": ledger["holdings"],
            "valuation": ledger["valuation"],
            "recent_trades": ledger["trades"][-6:],
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_agent() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    try:
        ingestion = DataIngestion()
        current_prices, history_df = ingestion.load_market_data(years=2)

        strategy = StrategyEngine()
        signals = strategy.evaluate(history_df)

        ledger = MetalsLedger(PROJECT_ROOT / "data" / "metals_ledger.json")
        updated_ledger = ledger.apply_signals(current_prices, signals)

        execution = build_execution_summary(signals, updated_ledger)
        print(json.dumps(execution, indent=2))
        return 0

    except AgentDataError as exc:
        logger.error("Data error: %s", exc)
        return 2
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_agent())
