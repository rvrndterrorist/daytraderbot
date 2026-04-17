import pandas as pd
import ta


class VWAPStrategy:
    """
    VWAP Reversion Strategy
    Buy: Price drops more than `dev_multiplier` standard deviations below VWAP.
    Sell: Price reverts back up to VWAP.
    Note: Standard VWAP resets daily.
    """
    def __init__(self, period: int = 14, dev_multiplier: float = 1.5, trade_pct: float = 0.95):
        self.period = period
        self.dev_multiplier = dev_multiplier
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.period + 1:
            return "hold"

        # VWAP indicator from ta
        vwap = ta.volume.VolumeWeightedAveragePrice(
            high=df["high"], 
            low=df["low"], 
            close=df["close"], 
            volume=df["volume"], 
            window=self.period
        ).volume_weighted_average_price()
        
        close = df["close"]
        
        # Calculate trailing std deviation for reversion bands
        std = close.rolling(window=self.period).std()
        
        vwap_curr = vwap.iloc[-1]
        close_curr = close.iloc[-1]
        std_curr = std.iloc[-1]

        if pd.isna(vwap_curr) or pd.isna(std_curr):
            return "hold"

        lower_band = vwap_curr - (std_curr * self.dev_multiplier)

        if close_curr < lower_band:  # Severely detached downwards
            return "buy"
        elif close_curr >= vwap_curr:  # Reverted to mean
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < self.period:
            return "VWAP=Wait"
        vwap = ta.volume.VolumeWeightedAveragePrice(
            high=df["high"], low=df["low"], close=df["close"], volume=df["volume"], window=self.period
        ).volume_weighted_average_price()
        val = vwap.iloc[-1]
        return f"VWAP= ${val:,.2f}" if not pd.isna(val) else "VWAP=Wait"
