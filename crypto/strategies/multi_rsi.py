import pandas as pd
import ta


class MultiRSIStrategy:
    """
    Multi-timeframe RSI Strategy
    Buy: Base RSI < buy_below AND Higher Timeframe RSI < buy_below.
    Sell: Base RSI > sell_above AND Higher Timeframe RSI > sell_above.
    """
    def __init__(self, period: int = 14, buy_below: float = 30, sell_above: float = 70, 
                 higher_timeframe: str = "4h", trade_pct: float = 0.95):
        self.period = period
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.higher_timeframe = higher_timeframe
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.period + 1:
            return "hold"

        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.period).rsi()
        latest_rsi = rsi_series.iloc[-1]

        if pd.isna(latest_rsi):
            return "hold"

        # Ensure index is datetime for resampling
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            return "hold"

        # Convert higher timeframe to pandas resample string if needed
        # e.g. "4H" -> "4h"
        htf = self.higher_timeframe.lower()

        df_higher = df.resample(htf).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        if len(df_higher) < self.period + 1:
            return "hold"

        rsi_higher_series = ta.momentum.RSIIndicator(close=df_higher["close"], window=self.period).rsi()
        latest_higher_rsi = rsi_higher_series.iloc[-1]

        if pd.isna(latest_higher_rsi):
            return "hold"

        if latest_rsi < self.buy_below and latest_higher_rsi < self.buy_below:
            return "buy"
        elif latest_rsi > self.sell_above and latest_higher_rsi > self.sell_above:
            return "sell"

        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.period).rsi()
        val = rsi_series.iloc[-1]
        return f"RSI={val:.2f}" if not pd.isna(val) else "RSI=Wait"
