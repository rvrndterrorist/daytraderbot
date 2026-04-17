#!/usr/bin/env python3
"""
Walk-Forward Strategy Comparison
=================================
Runs every strategy against every symbol using a 70/30 train/test split.

- In-sample (70%): strategy is fitted on this window — this is the "pitch"
- Out-of-sample (30%): this is what matters — how the strategy performs on data
  it has never seen. Sorted by this column.

A strategy with a positive OOS return is genuinely robust.
A large gap between in-sample and OOS (the Overfit Gap) means the strategy
is curve-fitted to the past and likely to disappoint on live data.
"""

import sys
import pandas as pd
from crypto.data import get_exchange, get_candles
from crypto.backtester import Backtester
from run import build_strategy

TRAIN_SPLIT = 0.70   # 70% in-sample, 30% out-of-sample

def main():
    symbols    = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]
    timeframes = ["1h"]
    strategies = [
        "rsi", "bb_rsi", "macd", "trend_rsi", "multi_rsi",
        "stoch_rsi", "supertrend", "vwap", "ma_ribbon", "demark", "fib_retrace",
    ]

    cfg = {
        "starting_balance": 20.0,
        "fee_rate": 0.0026,
        "backtest_slippage_pct": 0.0005,
        "risk_per_trade_pct": 0.01,
        "stop_multiplier": 2.5,
    }

    exchange = get_exchange("kraken", "", "")
    results_list = []

    print("\n" + "=" * 80)
    print("  WALK-FORWARD STRATEGY COMPARISON")
    print("=" * 80)
    print(f"Symbols   : {', '.join(symbols)}")
    print(f"Strategies: {', '.join(strategies)}")
    print(f"Split     : {int(TRAIN_SPLIT*100)}% in-sample / {int((1-TRAIN_SPLIT)*100)}% out-of-sample")
    print("Fetching data and running backtests...\n")

    for symbol in symbols:
        for tf in timeframes:
            try:
                df = get_candles(exchange, symbol, tf, limit=1000)
            except Exception as e:
                print(f"  Error fetching {symbol} {tf}: {e}")
                continue

            split_idx = int(len(df) * TRAIN_SPLIT)
            df_train = df.iloc[:split_idx]
            df_oos   = df.iloc[split_idx:]

            if len(df_train) < 50 or len(df_oos) < 20:
                print(f"  Not enough candles for {symbol} {tf} — skipping.")
                continue

            for strat_name in strategies:
                cfg_copy = dict(cfg)
                cfg_copy["strategy"] = strat_name
                cfg_copy["symbol"] = symbol

                try:
                    strat = build_strategy(cfg_copy)
                    bt = Backtester(
                        strat,
                        fee_rate=cfg["fee_rate"],
                        slippage_pct=cfg["backtest_slippage_pct"],
                        stop_multiplier=cfg["stop_multiplier"],
                        risk_per_trade_pct=cfg["risk_per_trade_pct"],
                    )

                    res_train = bt.run(df_train, starting_balance=cfg["starting_balance"])
                    res_oos   = bt.run(df_oos,   starting_balance=cfg["starting_balance"])

                    overfit_gap = res_train["total_return_pct"] - res_oos["total_return_pct"]

                    results_list.append({
                        "symbol":         symbol,
                        "timeframe":      tf,
                        "strategy":       strat_name,
                        "train_pct":      res_train["total_return_pct"],
                        "oos_pct":        res_oos["total_return_pct"],
                        "overfit_gap":    round(overfit_gap, 2),
                        "oos_win_rate":   res_oos["win_rate_pct"],
                        "oos_trades":     res_oos["num_trades"],
                        "oos_stops":      res_oos.get("num_stops", 0),
                        "robust":         res_oos["total_return_pct"] > 0,
                    })
                except Exception as e:
                    print(f"  Error on {strat_name}/{symbol}: {e}")

    # Sort by out-of-sample return — that's the real metric
    results_list.sort(key=lambda x: x["oos_pct"], reverse=True)

    print("=" * 80)
    print(f"{'SYMBOL':<10} | {'TF':<3} | {'STRATEGY':<12} | {'TRAIN%':<8} | {'OOS%':<8} | {'GAP':<7} | {'OOS WIN%':<9} | {'ROBUST'}")
    print("-" * 80)
    for r in results_list:
        train_str  = f"{'+' if r['train_pct'] >= 0 else ''}{r['train_pct']:.2f}%"
        oos_str    = f"{'+' if r['oos_pct'] >= 0 else ''}{r['oos_pct']:.2f}%"
        robust_str = "YES ✓" if r["robust"] else "no"
        print(
            f"{r['symbol']:<10} | {r['timeframe']:<3} | {r['strategy']:<12} | "
            f"{train_str:<8} | {oos_str:<8} | {r['overfit_gap']:<7.2f} | "
            f"{r['oos_win_rate']:<9.1f}% | {robust_str}"
        )

    print("=" * 80)

    robust = [r for r in results_list if r["robust"]]
    print(f"\n{len(robust)} / {len(results_list)} strategy-symbol combinations were profitable on out-of-sample data.")
    print("Only 'ROBUST: YES' rows should be considered for live deployment.")
    print("Low overfit gap = strategy generalises well. High gap = curve-fitted to history.")

if __name__ == "__main__":
    main()
