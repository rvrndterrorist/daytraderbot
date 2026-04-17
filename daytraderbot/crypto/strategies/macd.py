import pandas as pd
import ta


class MACDStrategy:
    """
    MACD Crossover Strategy
    Buy: MACD crosses ABOVE Signal.
    Sell: MACD crosses BELOW Signal.
    """
    def __init__(self, window_slow: int = 26, window_fast: int = 12, window_sign: int = 9, trade_pct: float = 0.95):
        self.window_slow = window_slow
        self.window_fast = window_fast
        self.window_sign = window_sign
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.window_slow + self.window_sign:
            return "hold"

        macd = ta.trend.MACD(
            close=df["close"], 
            window_slow=self.window_slow, 
            window_fast=self.window_fast, 
            window_sign=self.window_sign
        )
        macd_line = macd.macd()
        signal_line = macd.macd_signal()

        if pd.isna(macd_line.iloc[-1]) or pd.isna(signal_line.iloc[-1]) or pd.isna(macd_line.iloc[-2]) or pd.isna(signal_line.iloc[-2]):
            return "hold"

        macd_prev = macd_line.iloc[-2]
        signal_prev = signal_line.iloc[-2]
        macd_curr = macd_line.iloc[-1]
        signal_curr = signal_line.iloc[-1]

        if macd_prev <= signal_prev and macd_curr > signal_curr:
            return "buy"
        if macd_prev >= signal_prev and macd_curr < signal_curr:
            return "sell"
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < self.window_slow + self.window_sign:
            return "MACD=Wait"
        macd = ta.trend.MACD(close=df["close"], window_slow=self.window_slow, window_fast=self.window_fast, window_sign=self.window_sign)
        macd_line = macd.macd().iloc[-1]
        sig_line = macd.macd_signal().iloc[-1]
        if pd.isna(macd_line) or pd.isna(sig_line): return "MACD=Wait"
        return f"MACD={macd_line:.2f} / Sig={sig_line:.2f}"
