"""
RSI Mean-Reversion Strategy
----------------------------
Logic:
  - BUY  when RSI drops below `buy_below`  (oversold — price may bounce up)
  - SELL when RSI rises above `sell_above` (overbought — price may pull back)
  - HOLD otherwise

Tunable in config.json under the "rsi" key.
"""

import pandas as pd
import ta


class RSIStrategy:
    def __init__(self, period: int = 14, buy_below: float = 30, sell_above: float = 70, trade_pct: float = 0.95):
        self.period = period
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.trade_pct = trade_pct  # fraction of available balance to deploy per trade

    def signal(self, df: pd.DataFrame) -> str:
        """
        Analyze the latest candles and return 'buy', 'sell', or 'hold'.
        df must have at least (period + 1) rows with a 'close' column.
        """
        if len(df) < self.period + 1:
            return "hold"

        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.period).rsi()
        latest_rsi = rsi_series.iloc[-1]

        if pd.isna(latest_rsi):
            return "hold"

        if latest_rsi < self.buy_below:
            return "buy"
        elif latest_rsi > self.sell_above:
            return "sell"
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.period).rsi()
        val = rsi_series.iloc[-1]
        return f"RSI={val:.2f}" if not pd.isna(val) else "RSI=Wait"
