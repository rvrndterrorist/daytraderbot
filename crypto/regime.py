"""
Regime Detection — classifies the market as trending or ranging using ADX.

ADX > 25 = trending  → use trend-following strategies (MA Ribbon, Supertrend, MACD…)
ADX ≤ 25 = ranging   → use mean-reversion strategies (RSI, BB-RSI, Stoch-RSI…)

This is the foundation for intelligent strategy selection: matching the right
strategy type to the current market structure rather than running one style
blindly through all conditions.
"""

import pandas as pd
import ta

TRENDING_STRATEGIES = ["ma_ribbon", "supertrend", "macd", "demark", "fib_retrace"]
RANGING_STRATEGIES  = ["rsi", "bb_rsi", "stoch_rsi", "vwap", "trend_rsi"]

ADX_TREND_THRESHOLD = 25
ADX_WINDOW = 14
MIN_CANDLES = ADX_WINDOW * 2  # need enough bars for ADX to be meaningful


def detect_regime(df: pd.DataFrame) -> dict:
    """
    Analyse recent candles and classify the market regime.

    Returns:
        {"regime": "trending" | "ranging", "adx": float}

    Falls back to "trending" when there isn't enough data — trend-following
    is generally less dangerous as a blind default than mean-reversion.
    """
    if len(df) < MIN_CANDLES:
        return {"regime": "trending", "adx": 0.0}

    try:
        adx_indicator = ta.trend.ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=ADX_WINDOW,
        )
        val = float(adx_indicator.adx().iloc[-1])
    except Exception:
        return {"regime": "trending", "adx": 0.0}

    if pd.isna(val):
        return {"regime": "trending", "adx": 0.0}

    regime = "trending" if val >= ADX_TREND_THRESHOLD else "ranging"
    return {"regime": regime, "adx": round(val, 2)}


def strategies_for_regime(regime: str) -> list:
    """Return the approved strategy list for a given regime string."""
    if regime == "ranging":
        return list(RANGING_STRATEGIES)
    return list(TRENDING_STRATEGIES)
