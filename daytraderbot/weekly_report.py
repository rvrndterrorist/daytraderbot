#!/usr/bin/env python3
"""
Weekly Performance Report
==========================
Run this any time to get a plain-English summary of how the bot performed.
It reads the trade CSVs and equity logs — no internet connection needed.

Usage:
    python weekly_report.py           # last 7 days
    python weekly_report.py --days 30 # last 30 days
    python weekly_report.py --all     # entire history
"""

import argparse
import csv
import glob
import math
import os
from datetime import datetime, timedelta


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mean(values):
    return sum(values) / len(values) if values else 0.0

def _std(values):
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))

def _sharpe(returns):
    """Mean / std of returns. Returns 0 if not enough data."""
    if len(returns) < 2:
        return 0.0
    m = _mean(returns)
    s = _std(returns)
    return round(m / s, 3) if s > 0 else 0.0

def _sortino(returns):
    """
    Like Sharpe but only penalises downside volatility.
    Better metric for crypto because big upside swings shouldn't count as risk.
    Target > 2.0 for a healthy system.
    """
    if len(returns) < 2:
        return 0.0
    m = _mean(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf")  # no losing trades at all
    downside_std = _std(downside)
    return round(m / downside_std, 3) if downside_std > 0 else 0.0

def _max_drawdown(equity_values):
    """
    Largest peak-to-trough drop in the equity curve, as a percentage.
    e.g. 15.2 means the wallet fell 15.2% from its highest point at some stage.
    Target: stay under 20% for a healthy system.
    """
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    max_dd = 0.0
    for v in equity_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)

def _calmar(total_return_pct, max_drawdown_pct):
    """
    Total return divided by max drawdown. Target > 2.0.
    Penalises big losses relative to gains — a strategy with 10% return
    but 30% drawdown is worse than one with 8% return and 5% drawdown.
    """
    if max_drawdown_pct <= 0:
        return float("inf")
    return round(total_return_pct / max_drawdown_pct, 2)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_trades(cutoff: datetime | None) -> dict:
    """Load all per-symbol trade CSVs. Returns {symbol: [row, ...]}."""
    all_trades = {}
    for path in glob.glob("trades_*.csv"):
        symbol = path.replace("trades_", "").replace(".csv", "").replace("_", "/", 1)
        rows = []
        try:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        t = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                    if cutoff and t < cutoff:
                        continue
                    rows.append(row)
        except Exception:
            continue
        if rows:
            all_trades[symbol] = rows
    return all_trades


def load_equity(cutoff: datetime | None) -> dict:
    """Load equity log CSVs. Returns {symbol: [total_value, ...]}."""
    equity = {}
    for path in glob.glob("logs/equity_*.csv"):
        try:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    try:
                        t = datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                    if cutoff and t < cutoff:
                        continue
                    sym = row.get("symbol", "?")
                    val = float(row.get("total_value", 0) or 0)
                    equity.setdefault(sym, []).append(val)
        except Exception:
            continue
    return equity


def load_daily_reports(cutoff: datetime | None) -> list:
    """Load text from daily eval reports written by the adaptive evaluator."""
    reports = []
    for path in sorted(glob.glob("reports/*_eval.txt")):
        try:
            date_part = os.path.basename(path)[:10]
            report_date = datetime.strptime(date_part, "%Y-%m-%d")
        except ValueError:
            continue
        if cutoff and report_date < cutoff:
            continue
        try:
            with open(path) as f:
                reports.append((report_date, path, f.read()))
        except Exception:
            continue
    return reports


# ── Per-symbol analysis ────────────────────────────────────────────────────────

def analyse_symbol(symbol: str, trades: list, equity_values: list) -> dict:
    sells = [t for t in trades if t["action"] in ("SELL", "STOP")]
    buys  = [t for t in trades if t["action"] == "BUY"]
    stops = [t for t in trades if t["action"] == "STOP"]

    pnls = []
    for t in sells:
        # cumulative_pnl column tracks running total — we want per-trade PnL
        # Approximate: (sell amount_usd - fee) vs the buy cost is already in pnl
        # The CSV doesn't store per-trade pnl directly, so derive from cumulative
        pass

    # Build per-trade pnl from cumulative_pnl snapshots at each sell
    # Since we track cumulative_pnl after each row, the per-trade pnl is
    # the difference in cumulative_pnl between consecutive sells
    cum_pnls = []
    prev_cum = None
    for t in trades:
        try:
            cum = float(t.get("cumulative_pnl", 0) or 0)
        except ValueError:
            continue
        if t["action"] in ("SELL", "STOP"):
            if prev_cum is not None:
                pnls.append(cum - prev_cum)
            prev_cum = cum

    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    starting = float(trades[0].get("balance_usd", 20) or 20) if trades else 20
    # Find starting balance from first BUY's balance_usd + amount_usd
    if buys:
        try:
            b = float(buys[0]["balance_usd"] or 0)
            a = float(buys[0]["amount_usd"] or 0)
            starting = b + a
        except Exception:
            pass

    final_cum_pnl = 0.0
    if trades:
        try:
            final_cum_pnl = float(trades[-1].get("cumulative_pnl", 0) or 0)
        except Exception:
            pass

    total_fees = sum(float(t.get("fee", 0) or 0) for t in trades)
    win_rate   = (len(wins) / len(pnls) * 100) if pnls else 0.0
    avg_win    = _mean(wins)  if wins   else 0.0
    avg_loss   = _mean(losses) if losses else 0.0

    # Normalise pnls as fractions of starting balance for Sharpe/Sortino
    norm_pnls = [p / starting for p in pnls] if starting else []

    max_dd = _max_drawdown(equity_values) if equity_values else 0.0
    total_return_pct = (final_cum_pnl / starting * 100) if starting else 0.0
    calmar = _calmar(total_return_pct, max_dd)

    # Fee drag: total fees as % of starting balance
    fee_drag_pct = (total_fees / starting * 100) if starting else 0.0

    current_strategy = trades[-1].get("strategy", "?") if trades else "?"

    return {
        "symbol":            symbol,
        "current_strategy":  current_strategy,
        "total_trades":      len(trades),
        "buys":              len(buys),
        "sells":             len(sells),
        "stop_losses":       len(stops),
        "completed_trades":  len(pnls),
        "wins":              len(wins),
        "losses":            len(losses),
        "win_rate":          round(win_rate, 1),
        "avg_win_usd":       round(avg_win, 4),
        "avg_loss_usd":      round(avg_loss, 4),
        "total_pnl_usd":     round(final_cum_pnl, 4),
        "total_return_pct":  round(total_return_pct, 2),
        "total_fees_usd":    round(total_fees, 4),
        "fee_drag_pct":      round(fee_drag_pct, 2),
        "max_drawdown_pct":  max_dd,
        "sharpe":            _sharpe(norm_pnls),
        "sortino":           _sortino(norm_pnls),
        "calmar":            calmar,
    }


# ── Report printing ────────────────────────────────────────────────────────────

def _grade(sharpe, sortino, max_dd, win_rate, total_return_pct):
    """Simple health grade based on multiple metrics."""
    score = 0
    if sharpe    >= 1.5: score += 2
    elif sharpe  >= 0.5: score += 1
    if sortino   >= 2.0: score += 2
    elif sortino >= 1.0: score += 1
    if max_dd    <= 10:  score += 2
    elif max_dd  <= 20:  score += 1
    if win_rate  >= 55:  score += 1
    if total_return_pct > 0: score += 1
    if   score >= 7: return "A — Excellent"
    elif score >= 5: return "B — Good"
    elif score >= 3: return "C — Marginal"
    else:            return "D — Needs work"

def _fmt_sign(val, suffix=""):
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}{suffix}"

def print_report(period_label: str, all_trades: dict, all_equity: dict, reports: list):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print()
    print("=" * 65)
    print(f"  WEEKLY PERFORMANCE REPORT  |  {now}")
    print(f"  Period: {period_label}")
    print("=" * 65)

    if not all_trades:
        print("\n  No trades recorded in this period.")
        print("  The bot may still be in its first few days.")
        print("  At 1h candles, expect 2-8 trades per coin per month.\n")
        return

    totals = {"pnl": 0, "fees": 0, "trades": 0, "wins": 0, "losses": 0, "stops": 0}

    for symbol, trades in sorted(all_trades.items()):
        equity_vals = all_equity.get(symbol, [])
        r = analyse_symbol(symbol, trades, equity_vals)
        totals["pnl"]    += r["total_pnl_usd"]
        totals["fees"]   += r["total_fees_usd"]
        totals["trades"] += r["total_trades"]
        totals["wins"]   += r["wins"]
        totals["losses"] += r["losses"]
        totals["stops"]  += r["stop_losses"]

        grade = _grade(r["sharpe"], r["sortino"], r["max_drawdown_pct"],
                       r["win_rate"], r["total_return_pct"])

        pnl_color = "UP" if r["total_pnl_usd"] >= 0 else "DOWN"
        print(f"\n  ── {symbol}  [{r['current_strategy'].upper()}]")
        print(f"     Result    : {_fmt_sign(r['total_pnl_usd'], ' USD')}  ({_fmt_sign(r['total_return_pct'], '%')})  ← {pnl_color}")
        print(f"     Trades    : {r['completed_trades']} completed  ({r['wins']}W / {r['losses']}L / {r['stop_losses']} stops)  Win rate: {r['win_rate']:.1f}%")
        if r["completed_trades"] > 0:
            print(f"     Avg win   : +${r['avg_win_usd']:.4f}   Avg loss: ${r['avg_loss_usd']:.4f}")
        print(f"     Fees paid : ${r['total_fees_usd']:.4f}  ({r['fee_drag_pct']:.2f}% fee drag on starting balance)")
        if equity_vals:
            print(f"     Max Drawdown : {r['max_drawdown_pct']:.2f}%")
        if r["completed_trades"] >= 3:
            print(f"     Sharpe    : {r['sharpe']}   Sortino: {r['sortino']}   Calmar: {r['calmar']}")
            print(f"     Health    : {grade}")
        else:
            print(f"     Health    : Not enough trades yet for meaningful stats (need ≥3 completed trades)")

    print()
    print("  ── COMBINED FLEET TOTALS")
    print(f"     Net P&L   : {_fmt_sign(totals['pnl'], ' USD')}")
    print(f"     Total fees: ${totals['fees']:.4f}")
    print(f"     Trades    : {totals['trades']}  ({totals['wins']}W / {totals['losses']}L / {totals['stops']} stops)")

    # Fee drag warning
    if totals["fees"] > 0:
        warn_threshold = 5.0  # warn if fees > 5% of any coin's starting balance
        if totals["fees"] > warn_threshold:
            print(f"\n  ⚠  FEE DRAG WARNING: ${totals['fees']:.2f} in fees this period.")
            print(f"     At 0.52% per round-trip on Kraken, high trade frequency")
            print(f"     bleeds capital. Each trade needs >0.52% price movement in")
            print(f"     your favour just to break even.")

    # Daily eval report highlights
    if reports:
        print()
        print("  ── NIGHTLY AUDIT HIGHLIGHTS (last 7 days)")
        for date, path, text in reports[-7:]:
            adaptations = [l for l in text.split("\n") if "mutated" in l.lower() or "mutation" in l.lower()]
            regime_lines = [l for l in text.split("\n") if "Market Regime" in l]
            symbol_line  = next((l for l in text.split("\n") if l.startswith("Symbol")), "")
            sym_name     = symbol_line.split(":")[-1].strip() if symbol_line else "?"
            date_str     = date.strftime("%b %d")
            regime_str   = regime_lines[0].split(":")[-1].strip() if regime_lines else "?"
            adapt_str    = adaptations[0].strip() if adaptations else "No changes made"
            print(f"     {date_str} [{sym_name}]  Regime: {regime_str}  |  {adapt_str}")

    print()
    print("  ── WHAT TO LOOK FOR WEEK OVER WEEK")
    print("     Sharpe > 1.5     = strategy is generating real edge")
    print("     Sortino > 2.0    = losses are small, wins are big")
    print("     Max Drawdown     = highest % the wallet ever fell from its peak")
    print("     Fee drag < 3%    = fees aren't eating you alive")
    print("     Stop losses      = HEALTHY — bot protected capital")
    print()
    print("=" * 65)
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DayTrader Weekly Performance Report")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--all",  action="store_true",  help="Include entire history")
    args = parser.parse_args()

    if args.all:
        cutoff = None
        period_label = "All time"
    else:
        cutoff = datetime.now() - timedelta(days=args.days)
        period_label = f"Last {args.days} days ({cutoff.strftime('%Y-%m-%d')} → now)"

    all_trades  = load_trades(cutoff)
    all_equity  = load_equity(cutoff)
    daily_rpts  = load_daily_reports(cutoff)

    print_report(period_label, all_trades, all_equity, daily_rpts)


if __name__ == "__main__":
    main()
