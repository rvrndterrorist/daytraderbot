"""
Grid Trading Strategy
----------------------
Logic:
  - Divides a price range into N equally-spaced levels
  - BUY  when price crosses DOWN through a grid level (price is cheaper)
  - SELL when price crosses UP   through a grid level (price is higher)

Best in sideways/ranging markets. Dangerous in strong trending markets.

Tunable in config.json under the "grid" key.
"""

import pandas as pd


class GridStrategy:
    def __init__(self, lower_price: float, upper_price: float, levels: int, amount_per_grid: float):
        self.lower = lower_price
        self.upper = upper_price
        self.levels = levels
        self.amount_per_grid = amount_per_grid  # USD to spend per grid level

        step = (upper_price - lower_price) / levels
        self.grid_levels = [lower_price + i * step for i in range(levels + 1)]

        self._last_price = None
        self._last_grid_index = None

    def _price_to_grid_index(self, price: float) -> int:
        """Return which grid band the price currently sits in."""
        for i in range(len(self.grid_levels) - 1):
            if self.grid_levels[i] <= price < self.grid_levels[i + 1]:
                return i
        # Price is above the top of the grid
        return len(self.grid_levels) - 1

    def signal(self, df: pd.DataFrame) -> str:
        """
        Compare current price to the previous candle's grid position.
        Returns 'buy', 'sell', or 'hold'.
        """
        if len(df) < 2:
            return "hold"

        current_price = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2])

        if current_price < self.lower or current_price > self.upper:
            # Price has exited the grid — hold, don't chase
            return "hold"

        current_idx = self._price_to_grid_index(current_price)
        prev_idx = self._price_to_grid_index(prev_price)

        if current_idx < prev_idx:
            return "buy"   # Moved down through at least one grid level
        elif current_idx > prev_idx:
            return "sell"  # Moved up through at least one grid level
        return "hold"

    def get_indicator_info(self, df: pd.DataFrame, price: float = None) -> str:
        if price is None:
            if len(df) > 0: price = float(df["close"].iloc[-1])
            else: return "Grid=Wait"
        idx = self._price_to_grid_index(price)
        low = self.grid_levels[idx]
        high = self.grid_levels[min(idx + 1, len(self.grid_levels) - 1)]
        return f"Grid band {idx}/{self.levels}: ${low:,.0f} – ${high:,.0f}"
