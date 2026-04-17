import pandas as pd


class FibRetraceStrategy:
    """
    Fibonacci Retracement Strategy
    Tracks High/Low over a window and calculates standard Fib levels (0.382, 0.618, 1.272, etc).
    Buys near Golden Ratio support (0.618 from top, or 0.382 level).
    Sells near extensions (1.272, 1.414).
    """
    def __init__(self, window=100, buy_level=0.382, sell_level=1.272, threshold_pct=0.005, trade_pct=0.95):
        self.window = window
        self.buy_level = buy_level
        self.sell_level = sell_level
        # Threshold: price must be within X percent of the Fib line to trigger
        self.threshold = threshold_pct 
        self.trade_pct = trade_pct

    def _calc_fibs(self, df: pd.DataFrame):
        recent_df = df.tail(self.window)
        high = recent_df["high"].max()
        low = recent_df["low"].min()
        diff = high - low
        
        buy_target = low + (diff * self.buy_level)
        sell_target = low + (diff * self.sell_level)
        
        return high, low, buy_target, sell_target

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.window:
            return "hold"

        high, low, buy_target, sell_target = self._calc_fibs(df)
        if high == low: return "hold"
        
        current_price = df["close"].iloc[-1]
        
        # Check if price is within the percentage threshold of the target line
        if abs(current_price - buy_target) / buy_target <= self.threshold:
            return "buy"
            
        if abs(current_price - sell_target) / sell_target <= self.threshold:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < 5:
            return "Fibs=Wait"
        
        high, low, buy_t, sell_t = self._calc_fibs(df)
        return f"Fib B=${buy_t:,.0f} | S=${sell_t:,.0f}"
