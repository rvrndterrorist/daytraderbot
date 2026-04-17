import pandas as pd
import ta


class MARibbonStrategy:
    """
    Fibonacci Moving Average Ribbon Strategy
    Buy: Perfect bullish EMA alignment (5 > 21 > 55 > 144) AND close > SMA200.
    Sell: EMA5 crosses below EMA21 OR close < SMA100.
    """
    def __init__(self, ema1=5, ema2=21, ema3=55, ema4=144, sma1=100, sma2=200, trade_pct=0.95):
        self.ema1 = ema1
        self.ema2 = ema2
        self.ema3 = ema3
        self.ema4 = ema4
        self.sma1 = sma1
        self.sma2 = sma2
        self.trade_pct = trade_pct

    def _calc_indicators(self, close_series: pd.Series):
        e1 = ta.trend.ema_indicator(close=close_series, window=self.ema1)
        e2 = ta.trend.ema_indicator(close=close_series, window=self.ema2)
        e3 = ta.trend.ema_indicator(close=close_series, window=self.ema3)
        e4 = ta.trend.ema_indicator(close=close_series, window=self.ema4)
        s1 = ta.trend.sma_indicator(close=close_series, window=self.sma1)
        s2 = ta.trend.sma_indicator(close=close_series, window=self.sma2)
        return e1, e2, e3, e4, s1, s2

    def signal(self, df: pd.DataFrame) -> str:
        # Require enough data for the longest moving average
        longest = max(self.ema1, self.ema2, self.ema3, self.ema4, self.sma1, self.sma2)
        if len(df) < longest + 1:
            return "hold"

        e1, e2, e3, e4, s1, s2 = self._calc_indicators(df["close"])
        close = df["close"]

        # Current values
        e1_c, e2_c = e1.iloc[-1], e2.iloc[-1]
        e3_c, e4_c = e3.iloc[-1], e4.iloc[-1]
        s1_c, s2_c = s1.iloc[-1], s2.iloc[-1]
        price_c = close.iloc[-1]

        # Previous values
        e1_p, e2_p = e1.iloc[-2], e2.iloc[-2]
        
        if pd.isna(e4_c) or pd.isna(s2_c):
            return "hold"

        # BUY Logic: Perfect bullish alignment AND above 200 SMA
        bullish_alignment = (e1_c > e2_c) and (e2_c > e3_c) and (e3_c > e4_c)
        if bullish_alignment and (price_c > s2_c):
            # To avoid spamming buys if it's already aligned, we can optionally check if it wasn't aligned previously.
            # But the backtester state engine handles not double buying. We'll emit 'buy' whenever conditions are met.
            return "buy"

        # SELL Logic: Fast EMA (5) drops below Mid EMA (21) OR price breaks below 100 SMA
        e1_cross_down = (e1_p >= e2_p) and (e1_c < e2_c)
        price_breaks_s1 = price_c < s1_c

        if e1_cross_down or price_breaks_s1:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        longest = max(self.ema1, self.ema2, self.ema3, self.ema4, self.sma1, self.sma2)
        
        if len(df) < longest:
            return "Ribbon=Wait"
            
        e1, e2, e3, e4, s1, s2 = self._calc_indicators(df["close"])
        return f"Ribbon 5={e1.iloc[-1]:.0f} / 21={e2.iloc[-1]:.0f}"
