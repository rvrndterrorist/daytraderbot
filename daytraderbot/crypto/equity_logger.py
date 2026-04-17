"""
Equity Logger — writes a balance snapshot to CSV every candle.

This builds the equity curve: a complete record of wallet value over time.
Without this you only ever see "current balance" — you can never answer
"what was my worst losing streak?" or "did I recover after that crash?"

Output: logs/equity_YYYY-MM.csv  (one file per month, auto-rotates)
Columns: time, symbol, strategy, regime, price, balance_usd,
         position_size, total_value, pnl_usd, pnl_pct,
         stop_price, drawdown_pct
"""

import csv
import os
from datetime import datetime


LOGS_DIR = "logs"


def _get_path() -> str:
    os.makedirs(LOGS_DIR, exist_ok=True)
    month = datetime.now().strftime("%Y-%m")
    return os.path.join(LOGS_DIR, f"equity_{month}.csv")


_HEADER = [
    "time", "symbol", "strategy", "regime", "adx",
    "price", "balance_usd", "position_size",
    "total_value", "pnl_usd", "pnl_pct",
    "stop_price", "drawdown_pct",
]


def _ensure_header(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(_HEADER)


# Track per-symbol peak value so we can compute drawdown
_peaks: dict[str, float] = {}


def log_snapshot(
    symbol: str,
    strategy: str,
    regime: str,
    adx: float,
    price: float,
    balance_usd: float,
    position_size: float,
    total_value: float,
    starting_balance: float,
    stop_price: float | None,
):
    """Call once per candle after portfolio values are updated."""
    path = _get_path()
    _ensure_header(path)

    pnl_usd = total_value - starting_balance
    pnl_pct = (pnl_usd / starting_balance * 100) if starting_balance else 0

    # Drawdown: how far below the all-time peak are we right now?
    peak = _peaks.get(symbol, starting_balance)
    if total_value > peak:
        _peaks[symbol] = total_value
        peak = total_value
    drawdown_pct = ((peak - total_value) / peak * 100) if peak > 0 else 0

    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            strategy,
            regime,
            round(adx, 2),
            round(price, 4),
            round(balance_usd, 4),
            round(position_size, 8),
            round(total_value, 4),
            round(pnl_usd, 4),
            round(pnl_pct, 4),
            round(stop_price, 4) if stop_price else "",
            round(drawdown_pct, 4),
        ])
