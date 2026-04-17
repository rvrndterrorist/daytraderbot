"""
Shared bot state — thread-safe object that the trading loop writes to
and the WebSocket server reads from to push updates to the browser.
"""

import threading
from datetime import datetime
from collections import deque


class CoinState:
    def __init__(self, symbol):
        self._lock = threading.Lock()
        self.symbol = symbol
        self.strategy = ""
        self.mode = "paper"
        self.timeframe = "1h"
        self.is_running = False
        self.started_at = None

        self.current_price = 0.0
        self.signal = "—"
        self.rsi = None
        self.grid_info = None

        self.balance_usd = 0.0
        self.position_size = 0.0
        self.position_entry_price = 0.0
        self.total_value = 0.0
        self.pnl_usd = 0.0
        self.pnl_pct = 0.0
        self.starting_balance = 0.0
        self.trade_count = 0

        self.candles = []
        self.trades = deque(maxlen=50)
        self.logs = deque(maxlen=150)
        self.last_eval_date = None

        self.stop_price = None   # float | None — active trailing stop level
        self.regime = "unknown"  # "trending" | "ranging" | "unknown"
        self.adx = 0.0           # raw ADX value powering regime decision

    def snapshot(self):
        with self._lock:
            return {
                "symbol": self.symbol,
                "strategy": self.strategy,
                "mode": self.mode,
                "timeframe": self.timeframe,
                "is_running": self.is_running,
                "started_at": self.started_at,
                "current_price": self.current_price,
                "signal": self.signal,
                "rsi": self.rsi,
                "grid_info": self.grid_info,
                "balance_usd": round(self.balance_usd, 4),
                "position_size": round(self.position_size, 8),
                "position_entry_price": round(self.position_entry_price, 2),
                "total_value": round(self.total_value, 4),
                "pnl_usd": self.pnl_usd,
                "pnl_pct": self.pnl_pct,
                "starting_balance": self.starting_balance,
                "trade_count": self.trade_count,
                "candles": list(self.candles),
                "trades": list(self.trades),
                "logs": list(self.logs),
                "stop_price": self.stop_price,
                "regime": self.regime,
                "adx": self.adx,
            }

class BotState:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = []
        self._subscribers_lock = threading.Lock()
        
        self.coins = {}

    def get_coin(self, symbol: str) -> CoinState:
        with self._lock:
            if symbol not in self.coins:
                self.coins[symbol] = CoinState(symbol)
            return self.coins[symbol]

    def set_config(self, symbol, strategy, mode, timeframe, starting_balance):
        c = self.get_coin(symbol)
        with c._lock:
            c.strategy = strategy
            c.mode = mode
            c.timeframe = timeframe
            c.starting_balance = starting_balance
            c.balance_usd = starting_balance
            c.total_value = starting_balance
            c.is_running = True
            c.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def update_candles(self, symbol, df):
        records = []
        for ts, row in df.tail(150).iterrows():
            records.append({
                "time": int(ts.timestamp()),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low":  round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": round(float(row["volume"]), 4),
            })
        c = self.get_coin(symbol)
        with c._lock:
            c.candles = records

    def update_tick(self, symbol, price: float, signal: str, rsi=None, grid_info=None):
        c = self.get_coin(symbol)
        with c._lock:
            c.current_price = price
            c.signal = signal
            c.rsi = rsi
            c.grid_info = grid_info

    def update_portfolio(self, symbol, balance_usd, position_size, position_entry_price, total_value, trade_count):
        c = self.get_coin(symbol)
        with c._lock:
            c.balance_usd = balance_usd
            c.position_size = position_size
            c.position_entry_price = position_entry_price
            c.total_value = total_value
            c.pnl_usd = round(total_value - c.starting_balance, 4)
            c.pnl_pct = round((c.pnl_usd / c.starting_balance) * 100, 2) if c.starting_balance else 0
            c.trade_count = trade_count

    def update_stop(self, symbol, stop_price):
        c = self.get_coin(symbol)
        with c._lock:
            c.stop_price = round(stop_price, 4) if stop_price is not None else None

    def update_regime(self, symbol, regime: str, adx: float):
        c = self.get_coin(symbol)
        with c._lock:
            c.regime = regime
            c.adx = adx

    def add_trade(self, symbol, trade: dict):
        c = self.get_coin(symbol)
        with c._lock:
            trade["time"] = datetime.now().strftime("%H:%M:%S")
            c.trades.appendleft(dict(trade))

    def log(self, symbol, message: str):
        c = self.get_coin(symbol)
        with c._lock:
            c.logs.appendleft(f"{datetime.now().strftime('%H:%M:%S')}  {message}")
        self._notify()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "fleet": [c.snapshot() for sym, c in self.coins.items()]
            }

    def subscribe(self, queue):
        with self._subscribers_lock:
            self._subscribers.append(queue)

    def unsubscribe(self, queue):
        with self._subscribers_lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass

    def _notify(self):
        snap = self.snapshot()
        with self._subscribers_lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(snap)
                except Exception:
                    pass

    def push(self):
        self._notify()

# Singleton
bot_state = BotState()
