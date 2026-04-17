import pandas as pd


class DeMarkStrategy:
    """
    DeMark TD Sequential (Setup Phase)
    Counts consecutive closes compared to the close N bars prior.
    Default parameters look for a perfect 9-bar setup (exhaustion point) to trade reversals.
    """
    def __init__(self, setup_length=9, offset=4, trade_pct=0.95):
        self.setup_length = setup_length
        self.offset = offset
        self.trade_pct = trade_pct

    def _get_setup_count(self, close_series: pd.Series) -> tuple:
        """Returns (bull_setup_count, bear_setup_count) up to self.setup_length"""
        bull_count = 0  # Predicts bearish reversal (price rising)
        bear_count = 0  # Predicts bullish reversal (price falling)
        
        # Loop backwards from current bar
        for i in range(self.setup_length):
            idx = len(close_series) - 1 - i
            prev_idx = idx - self.offset
            
            if close_series.iloc[idx] > close_series.iloc[prev_idx]:
                bull_count += 1
            else:
                break
                
        for i in range(self.setup_length):
            idx = len(close_series) - 1 - i
            prev_idx = idx - self.offset
            
            if close_series.iloc[idx] < close_series.iloc[prev_idx]:
                bear_count += 1
            else:
                break
                
        return bull_count, bear_count

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.setup_length + self.offset + 1:
            return "hold"

        bull_c, bear_c = self._get_setup_count(df["close"])
        
        # Also check that the bar exactly BEFORE the sequence broke the rule, 
        # so we only trigger EXACTLY on the targeted setup_length bar, not spamming after.
        idx_before = len(df) - 1 - self.setup_length
        prev_idx_before = idx_before - self.offset
        
        close = df["close"]
        
        if bull_c == self.setup_length and close.iloc[idx_before] <= close.iloc[prev_idx_before]:
            # Exhausted upside -> SELL
            return "sell"
            
        if bear_c == self.setup_length and close.iloc[idx_before] >= close.iloc[prev_idx_before]:
            # Exhausted downside -> BUY
            return "buy"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < self.setup_length + self.offset:
            return "TD=Wait"
        
        bull_c, bear_c = self._get_setup_count(df["close"])
        if bull_c > 0:
            return f"TD Setup= {bull_c} (Uptrend)"
        elif bear_c > 0:
            return f"TD Setup= {bear_c} (Downtrend)"
        else:
            return "TD Setup= 0"
