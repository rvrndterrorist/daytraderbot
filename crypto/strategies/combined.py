import pandas as pd


class CombinedStrategy:
    """
    Strategy Combiner
    Takes a list of instantiated strategies and returns buy/sell if 
    at least `threshold` strategies agree.
    """
    def __init__(self, strategies: list, threshold: int = 2, trade_pct: float = 0.95):
        self.strategies = strategies
        self.threshold = threshold
        self.trade_pct = trade_pct

    def signal(self, df: pd.DataFrame) -> str:
        buys = 0
        sells = 0

        for strat in self.strategies:
            sig = strat.signal(df)
            if sig == "buy":
                buys += 1
            elif sig == "sell":
                sells += 1

        if buys >= self.threshold:
            return "buy"
        if sells >= self.threshold:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        for strat in self.strategies:
            if hasattr(strat, 'get_indicator_info'):
                return "Comb: " + strat.get_indicator_info(df, price)
        return "Combined=Wait"
