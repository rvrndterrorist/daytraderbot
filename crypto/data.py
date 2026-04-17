"""
Fetches OHLCV (Open/High/Low/Close/Volume) candle data from any exchange via ccxt.
No API key required for public market data.
"""

import ccxt
import pandas as pd
import time


def get_exchange(exchange_id: str, api_key: str = "", api_secret: str = ""):
    """Create and return a ccxt exchange instance."""
    exchange_class = getattr(ccxt, exchange_id)
    params = {"enableRateLimit": True}
    if api_key and api_secret:
        params["apiKey"] = api_key
        params["secret"] = api_secret
    return exchange_class(params)


def get_candles(
    exchange,
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> pd.DataFrame:
    """
    Fetch historical OHLCV candles.

    Returns a DataFrame with columns:
        timestamp, open, high, low, close, volume
    Sorted oldest → newest.
    """
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def get_current_price(exchange, symbol: str) -> float:
    """Fetch the latest ticker price for a symbol."""
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])


def wait_for_next_candle(timeframe: str):
    """
    Sleep until the next candle opens.
    Adds a small buffer so the candle is fully formed before we act.
    """
    seconds_map = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    interval = seconds_map.get(timeframe, 3600)
    now = time.time()
    # Sleep until the next interval boundary + 5 second buffer
    sleep_seconds = interval - (now % interval) + 5
    print(f"  Waiting {sleep_seconds:.0f}s for next {timeframe} candle...")
    time.sleep(sleep_seconds)
