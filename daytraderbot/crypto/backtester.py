"""
Backtester — runs a strategy against historical candle data and reports performance.

This is the most important step before risking real money.
A strategy that loses on historical data will almost certainly lose on live data too.

The simulator matches the live trading loop as closely as possible:
- Fees applied on every fill
- Slippage applied on every fill (pay more on buy, receive less on sell)
- ATR-based position sizing (same formula as crypto/position_sizer.py)
- Trailing stop that ratchets upward (same logic as crypto/stop_loss.py)

If a candle's low price touches or breaks the trailing stop, the position exits
at the stop price (with slippage), before the strategy sell signal is checked.
This is the key difference from a naive backtester — it prevents the simulator
from optimistically assuming you always exit at the strategy's ideal sell price.
"""

import pandas as pd
import ta


ATR_WINDOW = 14


def _calc_atr_series(df: pd.DataFrame) -> pd.Series:
    """Return the full ATR series for the dataframe. NaN where insufficient data."""
    if len(df) < ATR_WINDOW + 1:
        return pd.Series([float("nan")] * len(df), index=df.index)
    try:
        return ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=ATR_WINDOW
        ).average_true_range()
    except Exception:
        return pd.Series([float("nan")] * len(df), index=df.index)


class Backtester:
    def __init__(
        self,
        strategy,
        fee_rate: float = 0.001,
        slippage_pct: float = 0.0005,
        stop_multiplier: float = 2.5,
        risk_per_trade_pct: float = 0.95,
    ):
        self.strategy = strategy
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.stop_multiplier = stop_multiplier
        # risk_per_trade_pct < 1.0 activates ATR-based sizing (e.g. 0.01 = 1% risk).
        # Values >= 1.0 are treated as a fixed fraction of balance (legacy behaviour).
        self.risk_per_trade_pct = risk_per_trade_pct

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _position_fraction(self, wallet: float, price: float, atr: float) -> float:
        """
        Return the fraction of available balance to spend on this trade.

        If risk_per_trade_pct < 1: use ATR-based sizing (1% risk model).
        Otherwise: fall back to risk_per_trade_pct as a literal fraction (0.95 = 95%).
        """
        if self.risk_per_trade_pct >= 1.0:
            # Legacy: treat as a fraction directly (shouldn't normally happen;
            # config stores 0.01 not 1.0, but guard just in case)
            return min(self.risk_per_trade_pct, 0.95)

        # ATR-based fixed-fractional sizing
        if atr <= 0 or price <= 0 or wallet <= 0:
            return 0.95  # fallback if ATR unavailable

        risk_usd = wallet * self.risk_per_trade_pct
        stop_distance = atr * self.stop_multiplier
        position_usd = (risk_usd / stop_distance) * price
        capped = min(position_usd, wallet * 0.95)
        return capped / wallet

    # ------------------------------------------------------------------
    # Main simulation
    # ------------------------------------------------------------------

    def run(self, df: pd.DataFrame, starting_balance: float = 20.0) -> dict:
        """
        Simulate the strategy on historical candle data.

        Returns a results dict with key performance metrics.
        """
        # Pre-compute ATR series once across the full df for speed
        atr_series = _calc_atr_series(df)

        balance = starting_balance
        position_size = 0.0
        entry_price = 0.0
        trades = []

        # Trailing stop state
        stop_price: float | None = None
        highest_price: float = 0.0

        for i in range(len(df)):
            window = df.iloc[: i + 1]
            price    = float(df["close"].iloc[i])
            low      = float(df["low"].iloc[i])
            atr_val  = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0.0

            # --- Update trailing stop (ratchet up if price rose) ---
            if position_size > 0 and stop_price is not None:
                if price > highest_price:
                    highest_price = price
                if atr_val > 0:
                    new_stop = highest_price - atr_val * self.stop_multiplier
                    if new_stop > stop_price:
                        stop_price = new_stop

            # --- Trailing stop exit (check candle low, not just close) ---
            if position_size > 0 and stop_price is not None and low <= stop_price:
                # Fill at stop price with slippage (we get slightly less)
                fill_price = stop_price * (1 - self.slippage_pct)
                gross = position_size * fill_price
                fee = gross * self.fee_rate
                net = gross - fee
                pnl = net - (position_size * entry_price)
                balance += net
                trades.append({
                    "type": "stop",
                    "price": fill_price,
                    "time": df.index[i],
                    "amount": net,
                    "pnl": pnl,
                })
                position_size = 0.0
                entry_price = 0.0
                stop_price = None
                highest_price = 0.0
                # Skip strategy signal this candle — we already exited
                continue

            # --- Strategy signal ---
            sig = self.strategy.signal(window)

            if sig == "buy" and position_size == 0 and balance >= 1.0:
                # Slippage: pay slightly more than the signal price
                fill_price = price * (1 + self.slippage_pct)
                wallet_value = balance  # no open position at this point
                fraction = self._position_fraction(wallet_value, fill_price, atr_val)
                spend = balance * fraction
                fee = spend * self.fee_rate
                net_spend = spend - fee
                position_size = net_spend / fill_price
                entry_price = fill_price
                balance -= spend

                # Initialise trailing stop
                highest_price = fill_price
                stop_distance = (atr_val * self.stop_multiplier) if atr_val > 0 else fill_price * 0.03
                stop_price = fill_price - stop_distance

                trades.append({
                    "type": "buy",
                    "price": fill_price,
                    "time": df.index[i],
                    "amount": net_spend,
                })

            elif sig == "sell" and position_size > 0:
                # Slippage: receive slightly less than the signal price
                fill_price = price * (1 - self.slippage_pct)
                gross = position_size * fill_price
                fee = gross * self.fee_rate
                net = gross - fee
                pnl = net - (position_size * entry_price)
                balance += net
                trades.append({
                    "type": "sell",
                    "price": fill_price,
                    "time": df.index[i],
                    "amount": net,
                    "pnl": pnl,
                })
                position_size = 0.0
                entry_price = 0.0
                stop_price = None
                highest_price = 0.0

        # Close any open position at the last price for final valuation
        final_price = float(df["close"].iloc[-1])
        final_value = balance + position_size * final_price

        total_return = final_value - starting_balance
        total_return_pct = (total_return / starting_balance) * 100

        exit_trades = [t for t in trades if t["type"] in ("sell", "stop")]
        stop_trades  = [t for t in trades if t["type"] == "stop"]
        wins   = [t for t in exit_trades if t.get("pnl", 0) > 0]
        losses = [t for t in exit_trades if t.get("pnl", 0) <= 0]
        win_rate = (len(wins) / len(exit_trades) * 100) if exit_trades else 0.0

        total_fees = sum(t["amount"] * self.fee_rate for t in trades)

        # Per-trade returns as a fraction of starting balance — used for Sharpe scoring
        trade_pnls = [t["pnl"] / starting_balance for t in exit_trades]

        return {
            "starting_balance": starting_balance,
            "final_value": round(final_value, 4),
            "total_return_usd": round(total_return, 4),
            "total_return_pct": round(total_return_pct, 2),
            "num_trades": len(trades),
            "num_buys": len([t for t in trades if t["type"] == "buy"]),
            "num_sells": len([t for t in trades if t["type"] == "sell"]),
            "num_stops": len(stop_trades),
            "win_rate_pct": round(win_rate, 1),
            "wins": len(wins),
            "losses": len(losses),
            "total_fees_usd": round(total_fees, 4),
            "open_position": position_size > 0,
            "candles_tested": len(df),
            "trade_pnls": trade_pnls,
        }

    @staticmethod
    def print_report(results: dict, symbol: str, timeframe: str, strategy_name: str):
        print("\n" + "=" * 55)
        print(f"  BACKTEST RESULTS — {strategy_name.upper()} on {symbol}")
        print("=" * 55)
        print(f"  Candles tested : {results['candles_tested']} ({timeframe} each)")
        print(f"  Starting balance: ${results['starting_balance']:.2f}")
        print(f"  Final value     : ${results['final_value']:.4f}")
        sign = "+" if results["total_return_usd"] >= 0 else ""
        print(f"  Return          : {sign}${results['total_return_usd']:.4f}  ({sign}{results['total_return_pct']:.2f}%)")
        print(f"  Trades          : {results['num_buys']} buys / {results['num_sells']} sells / {results.get('num_stops', 0)} stops")
        print(f"  Win rate        : {results['win_rate_pct']:.1f}%  ({results['wins']}W / {results['losses']}L)")
        print(f"  Fees paid       : ${results['total_fees_usd']:.4f}")
        if results["open_position"]:
            print(f"  Note            : Position still open at end of test period")
        print("=" * 55)

        if results["num_sells"] + results.get("num_stops", 0) == 0:
            print("  WARNING: No completed trades. Strategy may be too conservative")
            print("           for this time period, or parameters need adjustment.")
        elif results["total_return_pct"] < 0:
            print("  WARNING: Strategy lost money in this period. Consider adjusting")
            print("           parameters or testing a different time range.")
        else:
            print("  Strategy was profitable in this test period.")
            print("  Remember: past results do NOT guarantee future profits.")
        print()
