"""
Paper Trader — simulates trades with fake money.
Tracks balance, position, P&L, and writes every trade to a per-symbol CSV.

Each coin gets its own file: trades_BTC_USDT.csv, trades_ETH_USDT.csv, etc.
Columns include symbol and strategy so you can analyse performance per coin
and per strategy after the fact.
"""

import csv
import os
from datetime import datetime


class PaperTrader:
    def __init__(self, starting_balance: float, fee_rate: float = 0.001,
                 symbol: str = "BTC/USDT", strategy: str = "unknown"):
        self.balance_usd = starting_balance
        self.position_size = 0.0
        self.position_entry_price = 0.0
        self.fee_rate = fee_rate
        self.symbol = symbol
        self.strategy = strategy
        self.trade_count = 0
        self.starting_balance = starting_balance

        # Per-symbol file so BTC/ETH/SOL/ADA trades never get mixed together
        safe_symbol = symbol.replace("/", "_")
        self.csv_path = f"trades_{safe_symbol}.csv"
        self._ensure_csv_header()

    def _ensure_csv_header(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "time", "symbol", "strategy", "action",
                    "price", "amount_usd", "amount_crypto", "fee",
                    "balance_usd", "position_usd", "cumulative_pnl",
                ])

    def _log_trade(self, action, price, amount_usd, amount_crypto, fee):
        position_usd = self.position_size * price
        cumulative_pnl = (self.balance_usd + position_usd) - self.starting_balance

        with open(self.csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.symbol,
                self.strategy,
                action,
                round(price, 4),
                round(amount_usd, 4),
                round(amount_crypto, 8),
                round(fee, 6),
                round(self.balance_usd, 4),
                round(position_usd, 4),
                round(cumulative_pnl, 4),
            ])

    def buy(self, price: float, fraction: float = 0.95) -> dict | None:
        """Buy crypto using `fraction` of available USD balance."""
        if self.balance_usd < 1.0:
            return None
        if self.position_size > 0:
            return None  # already in a position

        spend_usd = self.balance_usd * fraction
        fee = spend_usd * self.fee_rate
        net_spend = spend_usd - fee
        amount_crypto = net_spend / price

        self.balance_usd -= spend_usd
        self.position_size = amount_crypto
        self.position_entry_price = price
        self.trade_count += 1

        self._log_trade("BUY", price, spend_usd, amount_crypto, fee)

        return {
            "action": "BUY",
            "price": price,
            "amount_usd": spend_usd,
            "amount_crypto": amount_crypto,
            "fee": fee,
        }

    def sell(self, price: float, reason: str = "SELL") -> dict | None:
        """Sell entire position. reason can be 'SELL' or 'STOP'."""
        if self.position_size <= 0:
            return None

        gross_usd = self.position_size * price
        fee = gross_usd * self.fee_rate
        net_usd = gross_usd - fee
        pnl = net_usd - (self.position_size * self.position_entry_price)

        amount_crypto = self.position_size
        self.balance_usd += net_usd
        self.position_size = 0.0
        self.position_entry_price = 0.0
        self.trade_count += 1

        self._log_trade(reason, price, net_usd, amount_crypto, fee)

        return {
            "action": reason,
            "price": price,
            "amount_usd": net_usd,
            "amount_crypto": amount_crypto,
            "fee": fee,
            "pnl": pnl,
        }

    def portfolio_value(self, current_price: float) -> float:
        return self.balance_usd + (self.position_size * current_price)

    def status(self, current_price: float) -> str:
        total = self.portfolio_value(current_price)
        pnl = total - self.starting_balance
        pnl_pct = (pnl / self.starting_balance) * 100
        sign = "+" if pnl >= 0 else ""
        return (
            f"Balance: ${self.balance_usd:.4f} USD  |  "
            f"Position: {self.position_size:.8f} ({self.symbol.split('/')[0]})  |  "
            f"Total: ${total:.4f}  |  "
            f"P&L: {sign}${pnl:.4f} ({sign}{pnl_pct:.2f}%)  |  "
            f"Trades: {self.trade_count}"
        )
