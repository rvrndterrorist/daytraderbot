"""
ATR Trailing Stop Loss — Chandelier-style.

On entry, the stop is placed at: entry_price - multiplier × ATR
As price moves up, the stop ratchets upward tracking the new high.
The stop NEVER moves down — it only ever tightens.

This caps the maximum loss on any position and locks in profits
as the trade moves in your favour.

Default multiplier of 2.5 gives the trade room to breathe through
normal volatility while cutting runaway losses.
"""

import pandas as pd
import ta


ATR_WINDOW = 14


def _calc_atr(df: pd.DataFrame) -> float:
    """Return the latest ATR value, or 0 if not enough data."""
    if len(df) < ATR_WINDOW + 1:
        return 0.0
    try:
        atr_series = ta.volatility.AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=ATR_WINDOW,
        ).average_true_range()
        val = float(atr_series.iloc[-1])
        return val if not pd.isna(val) else 0.0
    except Exception:
        return 0.0


class TrailingStop:
    """
    ATR-based chandelier trailing stop.

    Usage:
        stop = TrailingStop(entry_price, df)           # create on buy
        stop.update(current_price, df)                 # call each candle
        if stop.is_triggered(current_price): ...       # check before strategy signal
    """

    def __init__(self, entry_price: float, df: pd.DataFrame, multiplier: float = 2.5):
        self.multiplier = multiplier
        self.highest_price = entry_price

        atr = _calc_atr(df)
        # If ATR is zero (insufficient data), fall back to 3% of entry price
        self._atr_fallback = entry_price * 0.03
        distance = (atr * multiplier) if atr > 0 else self._atr_fallback
        self.stop_price = entry_price - distance

    def update(self, current_price: float, df: pd.DataFrame):
        """
        Call once per candle after fetching new data.
        Ratchets the stop upward as price rises — never lowers it.
        """
        if current_price > self.highest_price:
            self.highest_price = current_price

        atr = _calc_atr(df)
        distance = (atr * self.multiplier) if atr > 0 else self._atr_fallback
        new_stop = self.highest_price - distance

        # Only move stop up, never down
        if new_stop > self.stop_price:
            self.stop_price = new_stop

    def is_triggered(self, current_price: float) -> bool:
        """Returns True if current price has fallen to or below the stop."""
        return current_price <= self.stop_price
