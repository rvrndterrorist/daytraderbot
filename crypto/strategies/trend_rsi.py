import pandas as pd
import ta


class TrendRSIStrategy:
    """
    Trend-filtered RSI Strategy
    Buy: Price > EMA AND RSI < buy_below.
    Sell: Price < EMA AND RSI > sell_above.
    """
    def __init__(self, period: int = 14, buy_below: float = 30, sell_above: float = 70, 
                 ema_period: int = 50, trade_pct: float = 0.95):
        self.period = period
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.ema_period = ema_period
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < max(self.period, self.ema_period) + 1:
            return "hold"

        close = df["close"]
        rsi_series = ta.momentum.RSIIndicator(close=close, window=self.period).rsi()
        ema_series = ta.trend.EMAIndicator(close=close, window=self.ema_period).ema_indicator()
        
        latest_rsi = rsi_series.iloc[-1]
        latest_close = close.iloc[-1]
        latest_ema = ema_series.iloc[-1]

        if pd.isna(latest_rsi) or pd.isna(latest_ema):
            return "hold"

        if latest_rsi < self.buy_below and latest_close > latest_ema:
            return "buy"
        elif latest_rsi > self.sell_above and latest_close < latest_ema:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.period).rsi()
        val = rsi_series.iloc[-1]
        return f"RSI={val:.2f}" if not pd.isna(val) else "RSI=Wait"
