import pandas as pd
import numpy as np


class SupertrendStrategy:
    """
    Supertrend Strategy
    Buy: Price closes above Supertrend.
    Sell: Price closes below Supertrend.
    Custom implementation matching pandas-ta math using standard pandas rules.
    """
    def __init__(self, period: int = 10, multiplier: float = 3.0, trade_pct: float = 0.95):
        self.period = period
        self.multiplier = multiplier
        self.trade_pct = trade_pct

    def _calc_supertrend(self, df: pd.DataFrame) -> pd.DataFrame:
        high = df['high']
        low = df['low']
        close = df['close']

        # Average True Range (ATR)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/self.period, adjust=False).mean()

        hl2 = (high + low) / 2
        upper = (hl2 + self.multiplier * atr).to_numpy(dtype=float, copy=True)
        lower = (hl2 - self.multiplier * atr).to_numpy(dtype=float, copy=True)
        close_arr = close.to_numpy(dtype=float)

        # Supertrend logic
        supertrend = np.zeros(len(df))
        direction = np.ones(len(df), dtype=int)  # 1 = up, -1 = down

        for i in range(1, len(df)):
            if close_arr[i] > upper[i - 1]:
                direction[i] = 1
            elif close_arr[i] < lower[i - 1]:
                direction[i] = -1
            else:
                direction[i] = direction[i - 1]

                # Lowerband can only ratchet up in an uptrend
                if direction[i] == 1 and lower[i] < lower[i - 1]:
                    lower[i] = lower[i - 1]

                # Upperband can only ratchet down in a downtrend
                if direction[i] == -1 and upper[i] > upper[i - 1]:
                    upper[i] = upper[i - 1]

            supertrend[i] = lower[i] if direction[i] == 1 else upper[i]

        return pd.DataFrame({'Supertrend': supertrend, 'Direction': direction}, index=df.index)

    def signal(self, df: pd.DataFrame) -> str:
        if len(df) < self.period + 2:
            return "hold"

        st_df = self._calc_supertrend(df)
        dir_prev = st_df['Direction'].iloc[-2]
        dir_curr = st_df['Direction'].iloc[-1]

        if dir_prev == -1 and dir_curr == 1:
            return "buy"
        elif dir_prev == 1 and dir_curr == -1:
            return "sell"
            
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if len(df) < self.period:
            return "ST=Wait"
        st = self._calc_supertrend(df)
        val = st['Supertrend'].iloc[-1]
        dr = "U" if st['Direction'].iloc[-1] == 1 else "D"
        return f"ST= ${val:,.2f} ({dr})"
