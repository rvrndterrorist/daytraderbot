"""
ATR-Based Position Sizer — Fixed Fractional Risk.

Instead of always spending 95% of the wallet, this calculates how much
to buy so that if the stop loss fires, we lose exactly `risk_pct` of
the total wallet — no matter how volatile the coin is.

Formula (from ROADMAP):
    risk_per_trade    = wallet_value × risk_pct          (e.g. 1% of $20 = $0.20)
    stop_distance     = atr × stop_multiplier            (price units — same as trailing stop)
    position_size_usd = risk_per_trade / stop_distance × price

In plain English: "I'm willing to lose $0.20. My stop is $X below entry.
How much can I buy so that losing $X per coin costs me exactly $0.20?"

The result is capped at 95% of wallet to avoid over-leveraging.
"""


def calculate_position_usd(
    wallet_value: float,
    price: float,
    atr: float,
    risk_pct: float = 0.01,
    stop_multiplier: float = 2.5,
) -> float:
    """
    Return the USD amount to invest in this trade.

    Args:
        wallet_value:    Total portfolio value in USD (cash + any open position)
        price:           Current coin price in USD
        atr:             Latest ATR value (from stop_loss._calc_atr)
        risk_pct:        Fraction of wallet to risk per trade (default 1%)
        stop_multiplier: Same multiplier used by TrailingStop (default 2.5)

    Returns:
        Position size in USD, capped at 95% of wallet_value.
        Falls back to 95% of wallet if ATR is zero or price is zero.
    """
    max_position = wallet_value * 0.95

    if atr <= 0 or price <= 0 or wallet_value <= 0:
        return max_position

    risk_per_trade = wallet_value * risk_pct
    stop_distance = atr * stop_multiplier      # price units (e.g. $250 for BTC)

    # Number of coins we can hold: risk_per_trade / stop_distance
    # Position in USD: coins × price
    position_usd = (risk_per_trade / stop_distance) * price

    return min(position_usd, max_position)
