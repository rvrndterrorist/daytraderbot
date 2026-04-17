import pandas as pd
import ta


class StochRSIStrategy:
    """
    Stochastic RSI Strategy
    Buy: %K crosses above 20 from below.
    Sell: %K crosses below 80 from above.
    """
    def __init__(self, period: int = 14, smooth1: int = 3, smooth2: int = 3, 
                 buy_level: float = 0.20, sell_level: float = 0.80, trade_pct: float = 0.95):
        self.period = period
        self.smooth1 = smooth1
        self.smooth2 = smooth2
        self.buy_level = buy_level
        self.sell_level = sell_level
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.period + max(self.smooth1, self.smooth2) + 2:
            return "hold"

        stoch_rsi = ta.momentum.StochRSIIndicator(
            close=df["close"], 
            window=self.period, 
            smooth1=self.smooth1, 
            smooth2=self.smooth2
        )
        k_line = stoch_rsi.stochrsi_k()

        if pd.isna(k_line.iloc[-1]) or pd.isna(k_line.iloc[-2]):
            return "hold"

        k_prev = k_line.iloc[-2]
        k_curr = k_line.iloc[-1]

        if k_prev < self.buy_level and k_curr >= self.buy_level:
            return "buy"
        elif k_prev > self.sell_level and k_curr <= self.sell_level:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < self.period:
            return "StochRSI=Wait"
        st = ta.momentum.StochRSIIndicator(close=df["close"], window=self.period, smooth1=self.smooth1, smooth2=self.smooth2).stochrsi_k()
        val = st.iloc[-1]
        return f"StochRSI={val:.2f}" if not pd.isna(val) else "StochRSI=Wait"
