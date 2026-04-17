"""
Live Trader — places real orders on an exchange with full safety controls.

WARNING: This uses real money. Only enable by setting "mode": "live" in config.json.
Only run this after backtesting and paper trading show consistent positive results.

Safety features added vs. the naive version:
  - Fill confirmation: polls fetch_order() until the order is actually closed
  - Accurate fill price: uses the exchange's reported average fill price
  - State persistence: writes position to live_state_SYMBOL.json after every trade
  - Startup reconciliation: compares saved state vs exchange balance on boot;
    enters safe mode and alerts if they don't match
  - Kill-switches: halts new buys if daily loss or drawdown exceeds config limits
  - Safe mode: all of the above can trigger safe mode — buy() returns None,
    sell() still works so you can always exit an existing position
"""

import json
import os
import time
from datetime import datetime


# How long to wait for an order to confirm before giving up (seconds)
_ORDER_CONFIRM_TIMEOUT = 60
_ORDER_POLL_INTERVAL   = 5

# Minimum crypto quantity considered a "real" position (below this = dust)
_DUST_THRESHOLD = 1e-5


class LiveTrader:
    def __init__(
        self,
        exchange,
        symbol: str,
        fee_rate: float = 0.001,
        notifier=None,
        config: dict = None,
    ):
        self.exchange   = exchange
        self.symbol     = symbol
        self.fee_rate   = fee_rate
        self.notifier   = notifier
        self.config     = config or {}
        self.trade_count = 0

        # Safe mode: blocks new buys but still allows sells
        self.safe_mode        = False
        self.safe_mode_reason = ""

        # Kill-switch tracking
        self._daily_start_value: float | None = None
        self._daily_start_date: str           = ""
        self._peak_value: float               = 0.0

        # Per-symbol state file
        safe_sym         = symbol.replace("/", "_")
        self.state_path  = f"live_state_{safe_sym}.json"

        # Reconcile saved state vs exchange on startup
        self._load_and_reconcile()

    # ── Alerting ──────────────────────────────────────────────────────────────

    def _alert(self, msg: str):
        """Log to console and send Telegram alert if notifier is available."""
        full = f"[LIVE {self.symbol}] {msg}"
        print(f"  {full}")
        if self.notifier:
            try:
                self.notifier.send(full)
            except Exception:
                pass

    # ── State persistence ─────────────────────────────────────────────────────

    def _save_state(self, position_size: float, entry_price: float, order_id: str = ""):
        """Write current position state to disk so restarts are safe."""
        state = {
            "symbol":        self.symbol,
            "position_size": position_size,
            "entry_price":   entry_price,
            "last_order_id": order_id,
            "last_sync_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self._alert(f"WARNING: Could not save state file: {e}")

    def _load_state(self) -> dict:
        """Load state from disk. Returns empty dict if file doesn't exist."""
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_state(self) -> dict:
        """Load position state from disk. Returns empty dict if file doesn't exist."""
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_and_reconcile(self):
        """
        On startup, compare the saved state file against the live exchange balance.
        Any mismatch triggers safe mode — better to pause and investigate than to
        trade on stale assumptions.
        """
        state = self._load_state()
        saved_qty = float(state.get("position_size", 0.0))

        try:
            balance_info   = self.exchange.fetch_balance()
            base           = self.symbol.split("/")[0]
            exchange_qty   = float(balance_info["free"].get(base, 0.0))
        except Exception as e:
            self._alert(f"Could not fetch balance on startup: {e}. Entering safe mode.")
            self._enter_safe_mode(f"Balance fetch failed on startup: {e}")
            return

        saved_flat    = saved_qty   < _DUST_THRESHOLD
        exchange_flat = exchange_qty < _DUST_THRESHOLD

        if saved_flat and exchange_flat:
            return  # Both flat — consistent, nothing to do

        if not saved_flat and not exchange_flat:
            # Both show a position — check quantities are within 5%
            if abs(saved_qty - exchange_qty) / max(saved_qty, exchange_qty) > 0.05:
                self._enter_safe_mode(
                    f"Position size mismatch: state={saved_qty:.8f}, "
                    f"exchange={exchange_qty:.8f}. Investigate before trading."
                )
            return  # Quantities match — consistent

        # One side flat, the other isn't — definite mismatch
        if saved_flat and not exchange_flat:
            self._enter_safe_mode(
                f"State says flat but exchange shows {exchange_qty:.8f} {base}. "
                f"Unexpected position. Investigate before trading."
            )
        else:
            self._enter_safe_mode(
                f"State says position {saved_qty:.8f} {base} but exchange shows flat. "
                f"Position may have been closed externally. Investigate before trading."
            )

    def _enter_safe_mode(self, reason: str):
        self.safe_mode        = True
        self.safe_mode_reason = reason
        self._alert(f"SAFE MODE ACTIVATED — {reason}")

    # ── Order fill confirmation ────────────────────────────────────────────────

    def _confirm_order(self, order_id: str) -> dict | None:
        """
        Poll fetch_order() until the order is closed/filled or the timeout expires.
        Returns the final order dict (with real fill price) or None on timeout/cancel.
        """
        deadline = time.time() + _ORDER_CONFIRM_TIMEOUT
        while time.time() < deadline:
            try:
                order = self.exchange.fetch_order(order_id, self.symbol)
                status = order.get("status", "")
                if status in ("closed", "filled"):
                    return order
                if status == "canceled":
                    self._alert(f"Order {order_id} was CANCELED by the exchange.")
                    return None
            except Exception as e:
                self._alert(f"Error polling order {order_id}: {e}")
            time.sleep(_ORDER_POLL_INTERVAL)

        self._alert(
            f"Order {order_id} not confirmed after {_ORDER_CONFIRM_TIMEOUT}s. "
            f"Entering safe mode — check the exchange manually."
        )
        self._enter_safe_mode(f"Order {order_id} confirmation timed out")
        return None

    @staticmethod
    def _fill_price(order: dict, fallback: float) -> float:
        """Extract actual average fill price from a closed order."""
        avg = order.get("average") or order.get("price")
        try:
            val = float(avg)
            return val if val > 0 else fallback
        except (TypeError, ValueError):
            return fallback

    # ── Kill-switches ─────────────────────────────────────────────────────────

    def check_kill_switches(self, current_price: float):
        """
        Call this once per candle from the trading loop.
        Checks daily loss and drawdown limits. Triggers safe mode if breached.
        """
        if self.safe_mode:
            return  # Already in safe mode

        total = self.portfolio_value(current_price)
        if total <= 0:
            return

        today = datetime.now().strftime("%Y-%m-%d")

        # Reset daily baseline at midnight
        if today != self._daily_start_date:
            self._daily_start_date  = today
            self._daily_start_value = total
            if total > self._peak_value:
                self._peak_value = total

        # Update peak
        if total > self._peak_value:
            self._peak_value = total

        max_daily_loss = self.config.get("max_daily_loss_pct", 5.0)
        max_drawdown   = self.config.get("max_drawdown_pct",   20.0)

        # Daily loss kill-switch
        if self._daily_start_value and self._daily_start_value > 0:
            daily_loss_pct = (self._daily_start_value - total) / self._daily_start_value * 100
            if daily_loss_pct >= max_daily_loss:
                self._enter_safe_mode(
                    f"Daily loss limit hit: -{daily_loss_pct:.2f}% "
                    f"(limit={max_daily_loss}%). No new buys today."
                )
                return

        # Max drawdown kill-switch
        if self._peak_value > 0:
            drawdown_pct = (self._peak_value - total) / self._peak_value * 100
            if drawdown_pct >= max_drawdown:
                self._enter_safe_mode(
                    f"Max drawdown limit hit: -{drawdown_pct:.2f}% from peak "
                    f"(limit={max_drawdown}%). No new buys until manual review."
                )

    # ── Trade execution ───────────────────────────────────────────────────────

    def buy(self, price: float, fraction: float = 0.95) -> dict | None:
        """
        Place a market buy order using `fraction` of available quote balance.
        Confirms the fill and persists state before returning.
        Returns trade info dict or None on failure / safe mode.
        """
        if self.safe_mode:
            print(f"  [LIVE] Buy blocked — safe mode: {self.safe_mode_reason}")
            return None

        try:
            balance_info   = self.exchange.fetch_balance()
            quote          = self.symbol.split("/")[1]
            available      = float(balance_info["free"].get(quote, 0))

            if available < 1.0:
                print(f"  Insufficient {quote} balance: ${available:.4f}")
                return None

            spend        = available * fraction
            amount_crypto = self.exchange.amount_to_precision(
                self.symbol, spend / price
            )

            order = self.exchange.create_market_buy_order(self.symbol, float(amount_crypto))
            order_id = order.get("id", "")

            # Wait for confirmed fill
            confirmed = self._confirm_order(order_id) if order_id else None
            fill_price = self._fill_price(confirmed, price) if confirmed else price
            filled_qty = float((confirmed or order).get("filled") or amount_crypto)

            self._save_state(filled_qty, fill_price, order_id)
            self.trade_count += 1

            fee = spend * self.fee_rate
            return {
                "action":        "BUY",
                "price":         fill_price,
                "amount_usd":    spend,
                "amount_crypto": filled_qty,
                "fee":           fee,
                "order_id":      order_id,
            }

        except Exception as e:
            self._alert(f"BUY ERROR: {e}")
            return None

    def sell(self, price: float, reason: str = "SELL") -> dict | None:
        """
        Sell entire base currency position.
        Confirms the fill and clears state before returning.
        Note: sell is NOT blocked by safe mode — you can always exit a position.
        """
        try:
            balance_info = self.exchange.fetch_balance()
            base         = self.symbol.split("/")[0]
            amount       = float(balance_info["free"].get(base, 0))

            if amount < _DUST_THRESHOLD:
                print(f"  No {base} position to sell.")
                return None

            amount   = self.exchange.amount_to_precision(self.symbol, amount)
            order    = self.exchange.create_market_sell_order(self.symbol, float(amount))
            order_id = order.get("id", "")

            confirmed  = self._confirm_order(order_id) if order_id else None
            fill_price = self._fill_price(confirmed, price) if confirmed else price
            filled_qty = float((confirmed or order).get("filled") or amount)

            gross = filled_qty * fill_price
            fee   = gross * self.fee_rate
            net   = gross - fee

            # Clear state — we're now flat
            self._save_state(0.0, 0.0, order_id)

            # If we were in safe mode due to a position mismatch, clear it now
            # that we've successfully exited — allow fresh start next buy signal
            if self.safe_mode and "position" in self.safe_mode_reason.lower():
                self.safe_mode        = False
                self.safe_mode_reason = ""
                self._alert("Safe mode cleared after successful sell. Position now flat.")

            self.trade_count += 1

            return {
                "action":        reason,
                "price":         fill_price,
                "amount_usd":    net,
                "amount_crypto": filled_qty,
                "fee":           fee,
                "order_id":      order_id,
            }

        except Exception as e:
            self._alert(f"SELL ERROR ({reason}): {e}")
            return None

    # ── Portfolio helpers ─────────────────────────────────────────────────────

    def portfolio_value(self, current_price: float) -> float:
        """Fetch live balance and compute total USD value."""
        try:
            balance_info = self.exchange.fetch_balance()
            base         = self.symbol.split("/")[0]
            quote        = self.symbol.split("/")[1]
            usd          = float(balance_info["free"].get(quote, 0))
            crypto       = float(balance_info["free"].get(base, 0))
            return usd + crypto * current_price
        except Exception as e:
            print(f"  Error fetching live balance: {e}")
            return 0.0

    def status(self, current_price: float) -> str:
        try:
            balance_info = self.exchange.fetch_balance()
            base         = self.symbol.split("/")[0]
            quote        = self.symbol.split("/")[1]
            usd          = float(balance_info["free"].get(quote, 0))
            crypto       = float(balance_info["free"].get(base, 0))
            total        = usd + crypto * current_price
            safe_str     = f"  ⚠ SAFE MODE: {self.safe_mode_reason}" if self.safe_mode else ""
            return (
                f"[LIVE] Balance: ${usd:.4f} {quote}  |  "
                f"Position: {crypto:.8f} {base}  |  "
                f"Total: ${total:.4f}  |  "
                f"Trades: {self.trade_count}{safe_str}"
            )
        except Exception as e:
            return f"[LIVE] Error fetching status: {e}"


