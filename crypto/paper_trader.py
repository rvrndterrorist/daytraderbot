"""
Paper Trader — simulates trades with fake money.
Tracks balance, position, P&L, and writes every trade to a per-symbol CSV.

Each coin gets its own file: trades_BTC_USDT.csv, trades_ETH_USDT.csv, etc.

Supports an optional SharedWallet so that all fleet coins draw from and
return to a single pool of money rather than isolated per-coin buckets.
When a SharedWallet is provided, `balance_usd` reflects the shared pool's
remaining cash, and buys/sells move money in and out of that pool atomically.
"""

import csv
import os
from datetime import datetime


class PaperTrader:
    def __init__(
        self,
        starting_balance: float,
        fee_rate: float = 0.001,
        symbol: str = "BTC/USDT",
        strategy: str = "unknown",
        shared_wallet=None,
    ):
        self._shared_wallet  = shared_wallet
        self.starting_balance = starting_balance  # used for PnL display; total pool if shared
        self.fee_rate         = fee_rate
        self.symbol           = symbol
        self.strategy         = strategy
        self.trade_count      = 0
        self.position_size    = 0.0
        self.position_entry_price = 0.0

        # Local balance only used when no shared wallet
        self._local_balance = starting_balance if shared_wallet is None else 0.0
        self._position_cost_usd = 0.0   # how much USD was spent to enter the current position

        # Per-symbol CSV
        safe_symbol    = symbol.replace("/", "_")
        self.csv_path  = f"trades_{safe_symbol}.csv"
        self._ensure_csv_header()

    # ── Balance access ─────────────────────────────────────────────────────────

    @property
    def balance_usd(self) -> float:
        """Available cash. Reads from shared wallet if present."""
        if self._shared_wallet:
            return self._shared_wallet.balance
        return self._local_balance

    # ── Logging ───────────────────────────────────────────────────────────────

    def _ensure_csv_header(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                csv.writer(f).writerow([
                    "time", "symbol", "strategy", "action",
                    "price", "amount_usd", "amount_crypto", "fee",
                    "balance_usd", "position_usd", "cumulative_pnl",
                ])

    def _log_trade(self, action, price, amount_usd, amount_crypto, fee):
        position_usd    = self.position_size * price
        cumulative_pnl  = (self.balance_usd + position_usd) - self.starting_balance
        with open(self.csv_path, "a", newline="") as f:
            csv.writer(f).writerow([
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

    # ── Trading ───────────────────────────────────────────────────────────────

    def buy(self, price: float, fraction: float = 0.95) -> dict | None:
        """
        Buy crypto using `fraction` of available cash.
        With a shared wallet, deducts from the shared pool atomically.
        Returns None if already in a position or funds are too low.
        """
        if self.position_size > 0:
            return None  # already holding this coin

        available = self.balance_usd
        if available < 1.0:
            return None  # wallet is empty

        spend_usd = available * fraction

        if self._shared_wallet:
            # Atomic deduction — another thread may have spent funds since we checked
            spend_usd = self._shared_wallet.spend(spend_usd)
            if spend_usd < 1.0:
                return None  # another coin grabbed the last of the funds first
        else:
            self._local_balance -= spend_usd

        fee         = spend_usd * self.fee_rate
        net_spend   = spend_usd - fee
        amount_crypto = net_spend / price

        self.position_size        = amount_crypto
        self.position_entry_price = price
        self._position_cost_usd   = spend_usd
        self.trade_count         += 1

        self._log_trade("BUY", price, spend_usd, amount_crypto, fee)

        return {
            "action":        "BUY",
            "price":         price,
            "amount_usd":    spend_usd,
            "amount_crypto": amount_crypto,
            "fee":           fee,
        }

    def sell(self, price: float, reason: str = "SELL") -> dict | None:
        """
        Sell entire position. Returns funds to shared wallet if present.
        reason can be 'SELL' or 'STOP'.
        """
        if self.position_size <= 0:
            return None

        gross_usd     = self.position_size * price
        fee           = gross_usd * self.fee_rate
        net_usd       = gross_usd - fee
        pnl           = net_usd - (self.position_size * self.position_entry_price)
        amount_crypto = self.position_size

        if self._shared_wallet:
            self._shared_wallet.deposit(net_usd)
        else:
            self._local_balance += net_usd

        self.position_size        = 0.0
        self.position_entry_price = 0.0
        self._position_cost_usd   = 0.0
        self.trade_count         += 1

        self._log_trade(reason, price, net_usd, amount_crypto, fee)

        return {
            "action":        reason,
            "price":         price,
            "amount_usd":    net_usd,
            "amount_crypto": amount_crypto,
            "fee":           fee,
            "pnl":           pnl,
        }

    # ── Portfolio helpers ─────────────────────────────────────────────────────

    def portfolio_value(self, current_price: float) -> float:
        """Cash available + value of any open position on this coin."""
        return self.balance_usd + (self.position_size * current_price)

    def is_out_of_funds(self) -> bool:
        """True if the wallet has less than $1 — can't open any more positions."""
        if self._shared_wallet:
            return self._shared_wallet.is_empty()
        return self._local_balance < 1.0

    def status(self, current_price: float) -> str:
        total   = self.portfolio_value(current_price)
        pnl     = total - self.starting_balance
        pnl_pct = (pnl / self.starting_balance * 100) if self.starting_balance else 0
        sign    = "+" if pnl >= 0 else ""
        wallet_label = "Shared pool" if self._shared_wallet else "Balance"
        return (
            f"{wallet_label}: ${self.balance_usd:.4f} USD  |  "
            f"Position: {self.position_size:.8f} ({self.symbol.split('/')[0]})  |  "
            f"Total: ${total:.4f}  |  "
            f"P&L: {sign}${pnl:.4f} ({sign}{pnl_pct:.2f}%)  |  "
            f"Trades: {self.trade_count}"
        )
