"""
Shared Wallet — one pool of cash used by all fleet coins simultaneously.

Without this, each coin has its own $20 bucket and they never interact.
With this, all coins draw from and return to the same pot of money.

Thread-safe: each spend/deposit uses a lock so two coins can't
accidentally both think they have $20 available at the same moment.
"""

import threading


class SharedWallet:
    def __init__(self, starting_balance: float):
        self.starting_balance = starting_balance
        self._balance = starting_balance
        self._lock = threading.Lock()

    @property
    def balance(self) -> float:
        with self._lock:
            return self._balance

    def spend(self, amount: float) -> float:
        """
        Atomically deduct `amount` from the wallet.
        Returns how much was actually deducted — may be less if funds ran low.
        Returns 0 if balance is under $1.
        """
        with self._lock:
            if self._balance < 1.0:
                return 0.0
            actual = min(amount, self._balance)
            self._balance -= actual
            return actual

    def deposit(self, amount: float):
        """Return funds to the wallet after a sell."""
        with self._lock:
            self._balance += amount

    def is_empty(self) -> bool:
        """True if less than $1 remains — not enough to open a position."""
        return self.balance < 1.0
