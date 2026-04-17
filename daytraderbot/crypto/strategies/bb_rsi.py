import pandas as pd
import ta


class BBRSIStrategy:
    """
    Bollinger Bands + RSI Strategy
    Buy: Price <= Lower BB AND RSI < buy_below.
    Sell: Price >= Upper BB AND RSI > sell_above.
    """
    def __init__(self, rsi_period: int = 14, buy_below: float = 30, sell_above: float = 70, 
                 bb_period: int = 20, bb_std: float = 2.0, trade_pct: float = 0.95):
        self.rsi_period = rsi_period
        self.buy_below = buy_below
        self.sell_above = sell_above
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < max(self.rsi_period, self.bb_period) + 1:
            return "hold"

        close = df["close"]
        rsi_series = ta.momentum.RSIIndicator(close=close, window=self.rsi_period).rsi()
        bb = ta.volatility.BollingerBands(close=close, window=self.bb_period, window_dev=self.bb_std)
        
        latest_rsi = rsi_series.iloc[-1]
        latest_close = close.iloc[-1]
        lower_band = bb.bollinger_lband().iloc[-1]
        upper_band = bb.bollinger_hband().iloc[-1]

        if pd.isna(latest_rsi) or pd.isna(lower_band) or pd.isna(upper_band):
            return "hold"

        if latest_rsi < self.buy_below and latest_close <= lower_band:
            return "buy"
        elif latest_rsi > self.sell_above and latest_close >= upper_band:
            return "sell"
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=self.rsi_period).rsi()
        val = rsi_series.iloc[-1]
        return f"RSI={val:.2f}" if not pd.isna(val) else "RSI=Wait"
