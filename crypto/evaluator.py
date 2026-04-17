"""
Adaptive DNA Evaluator — nightly strategy selection engine.

At midnight, for each fleet coin:
  1. Detect current market regime (trending vs ranging) via ADX.
  2. Filter the approved strategy list to those suited for that regime.
  3. Backtest each candidate on the last 30 days of candle data,
     using the REAL parameters from config.json (not defaults).
  4. Score by Sharpe ratio (mean / std of per-trade returns).
  5. Only switch if the best candidate beats the current strategy
     by a meaningful margin AND has enough completed trades to be trusted.
  6. Enforce a cooldown so the bot can't thrash between strategies daily.
  7. If switching, overwrite config.json overrides → hot-reload picks it up.
"""

import json
import math
import os
from datetime import datetime, timedelta

import pandas as pd

from crypto.backtester import Backtester
from crypto.regime import detect_regime, strategies_for_regime

# Large notional so fee impact is realistic; rounding noise doesn't matter
_EVAL_BALANCE = 1000.0
# 30 days × 24 candles/day at 1h timeframe
_EVAL_CANDLES = 720

# Config defaults used when keys are absent
_DEFAULT_FEE          = 0.0026
_DEFAULT_SLIPPAGE     = 0.0005
_DEFAULT_STOP_MULT    = 2.5
_DEFAULT_RISK_PCT     = 0.01
_DEFAULT_MIN_IMPROVE  = 0.3   # Sharpe improvement required to trigger switch
_DEFAULT_MIN_TRADES   = 5     # minimum completed trades for a strategy to be eligible
_DEFAULT_COOLDOWN     = 3     # days between strategy switches


# ── Scoring helpers ────────────────────────────────────────────────────────────

def _sharpe(trade_pnls: list) -> float:
    """
    Sharpe proxy: mean / std of per-trade fractional returns.
    Returns -inf if fewer than 2 completed trades.
    """
    if len(trade_pnls) < 2:
        return float("-inf")
    mean = sum(trade_pnls) / len(trade_pnls)
    variance = sum((x - mean) ** 2 for x in trade_pnls) / len(trade_pnls)
    std = math.sqrt(variance)
    if std == 0:
        return mean * 10
    return mean / std


def _score_strategies(candidates: list, eval_df: pd.DataFrame, cfg: dict) -> dict:
    """
    Backtest each candidate strategy on eval_df using real config parameters.

    Returns {strategy_name: {"sharpe": float, "num_trades": int}}.
    Uses lazy import of build_strategy to avoid circular import with run.py.
    """
    from run import build_strategy  # noqa: PLC0415

    fee_rate          = cfg.get("fee_rate",               _DEFAULT_FEE)
    slippage_pct      = cfg.get("backtest_slippage_pct",  _DEFAULT_SLIPPAGE)
    stop_multiplier   = cfg.get("stop_multiplier",        _DEFAULT_STOP_MULT)
    risk_per_trade    = cfg.get("risk_per_trade_pct",     _DEFAULT_RISK_PCT)

    scores = {}
    for name in candidates:
        try:
            # Pass real per-strategy params from config, not an empty dict
            strat_cfg = {"strategy": name, name: cfg.get(name, {})}
            strat = build_strategy(strat_cfg)
            bt = Backtester(
                strat,
                fee_rate=fee_rate,
                slippage_pct=slippage_pct,
                stop_multiplier=stop_multiplier,
                risk_per_trade_pct=risk_per_trade,
            )
            res = bt.run(eval_df, starting_balance=_EVAL_BALANCE)
            scores[name] = {
                "sharpe":     _sharpe(res["trade_pnls"]),
                "num_trades": len(res["trade_pnls"]),
            }
        except Exception:
            scores[name] = {"sharpe": float("-inf"), "num_trades": 0}
    return scores


# ── Cooldown helpers ───────────────────────────────────────────────────────────

def _last_switch_date(cfg_data: dict, symbol: str) -> datetime | None:
    """Read the last switch date stored in config overrides for this symbol."""
    raw = cfg_data.get("overrides", {}).get(symbol, {}).get("_last_switch", "")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None


def _in_cooldown(cfg_data: dict, symbol: str, cooldown_days: int) -> bool:
    last = _last_switch_date(cfg_data, symbol)
    if last is None:
        return False
    return datetime.now() - last < timedelta(days=cooldown_days)


# ── Adaptation ────────────────────────────────────────────────────────────────

def adapt_strategy(symbol: str, current_strategy: str, df: pd.DataFrame) -> str | None:
    """
    Select the best regime-appropriate strategy for this symbol based on
    recent backtested Sharpe. Only switches if:
      - best candidate beats current strategy by eval_min_sharpe_improvement
      - best candidate has at least eval_min_trades completed trades
      - cooldown period since last switch has elapsed

    Writes override to config.json on switch. Returns new name or None.
    """
    cfg_path = "config.json"
    if not os.path.exists(cfg_path):
        return None

    try:
        with open(cfg_path) as f:
            cfg_data = json.load(f)
    except Exception:
        return None

    min_improvement = cfg_data.get("eval_min_sharpe_improvement", _DEFAULT_MIN_IMPROVE)
    min_trades      = cfg_data.get("eval_min_trades",              _DEFAULT_MIN_TRADES)
    cooldown_days   = cfg_data.get("eval_cooldown_days",           _DEFAULT_COOLDOWN)

    # Cooldown check — don't thrash
    if _in_cooldown(cfg_data, symbol, cooldown_days):
        return None

    regime_info = detect_regime(df)
    candidates  = strategies_for_regime(regime_info["regime"])
    eval_df     = df.tail(_EVAL_CANDLES)

    # Score all regime-appropriate candidates + the current strategy
    # (current may be from a different regime — score it anyway for comparison)
    to_score = list(set(candidates) | {current_strategy})
    scores   = _score_strategies(to_score, eval_df, cfg_data)

    # Filter: must have minimum trades to be considered
    eligible = {
        k: v for k, v in scores.items()
        if k in candidates                      # must be regime-appropriate
        and v["sharpe"] != float("-inf")
        and v["num_trades"] >= min_trades
    }

    if not eligible:
        return None

    best       = max(eligible, key=lambda k: eligible[k]["sharpe"])
    best_score = eligible[best]["sharpe"]

    if best == current_strategy:
        return None

    # Improvement threshold: only switch if materially better
    current_score = scores.get(current_strategy, {}).get("sharpe", float("-inf"))
    if best_score - current_score < min_improvement:
        return None

    # All gates passed — write the switch
    try:
        cfg_data.setdefault("overrides", {}).setdefault(symbol, {})["strategy"] = best
        cfg_data["overrides"][symbol]["_last_switch"] = datetime.now().strftime("%Y-%m-%d")
        with open(cfg_path, "w") as f:
            json.dump(cfg_data, f, indent=2)
        return best
    except Exception as e:
        print(f"  [Evaluator] Failed to write adaptation for {symbol}: {e}")
        return None


# ── Daily report ───────────────────────────────────────────────────────────────

def evaluate_daily(coin_state, df: pd.DataFrame, report_dir: str = "reports"):
    """
    Called once per day per fleet coin. Writes a report and conditionally
    triggers strategy adaptation.
    """
    os.makedirs(report_dir, exist_ok=True)
    date_str    = datetime.now().strftime("%Y-%m-%d")
    symbol_safe = coin_state.symbol.replace("/", "_")
    report_path = os.path.join(report_dir, f"{date_str}_{symbol_safe}_eval.txt")

    # Load config so report reflects actual params used
    cfg_data = {}
    try:
        with open("config.json") as f:
            cfg_data = json.load(f)
    except Exception:
        pass

    fee_rate       = cfg_data.get("fee_rate",               _DEFAULT_FEE)
    slippage_pct   = cfg_data.get("backtest_slippage_pct",  _DEFAULT_SLIPPAGE)
    stop_mult      = cfg_data.get("stop_multiplier",        _DEFAULT_STOP_MULT)
    risk_pct       = cfg_data.get("risk_per_trade_pct",     _DEFAULT_RISK_PCT)
    min_improve    = cfg_data.get("eval_min_sharpe_improvement", _DEFAULT_MIN_IMPROVE)
    min_trades     = cfg_data.get("eval_min_trades",        _DEFAULT_MIN_TRADES)
    cooldown_days  = cfg_data.get("eval_cooldown_days",     _DEFAULT_COOLDOWN)

    tf = coin_state.timeframe
    candles_in_day = {"1h": 24, "15m": 96, "4h": 6, "1d": 1}.get(tf, 24)
    recent_df = df.tail(candles_in_day)

    start_price = recent_df["close"].iloc[0] if len(recent_df) > 0 else 0
    end_price   = recent_df["close"].iloc[-1] if len(recent_df) > 0 else 0
    market_change_pct = ((end_price - start_price) / start_price * 100) if start_price > 0 else 0

    total_trades = len(coin_state.trades)
    wins         = [t for t in coin_state.trades if t.get("pnl", 0) > 0]
    win_rate     = (len(wins) / total_trades * 100) if total_trades > 0 else 0

    regime_info = detect_regime(df)
    candidates  = strategies_for_regime(regime_info["regime"])
    eval_df     = df.tail(_EVAL_CANDLES)

    to_score    = list(set(candidates) | {coin_state.strategy})
    scores      = _score_strategies(to_score, eval_df, cfg_data)

    eligible = {
        k: v for k, v in scores.items()
        if k in candidates
        and v["sharpe"] != float("-inf")
        and v["num_trades"] >= min_trades
    }

    best_candidate = max(eligible, key=lambda k: eligible[k]["sharpe"]) if eligible else "none"
    best_score     = eligible[best_candidate]["sharpe"] if eligible else float("-inf")
    current_score  = scores.get(coin_state.strategy, {}).get("sharpe", float("-inf"))

    in_cooldown    = _in_cooldown(cfg_data, coin_state.symbol, cooldown_days)
    trigger_adaptation = False

    with open(report_path, "w") as f:
        f.write(f"=== DAYTRADER DAILY EVALUATION ({date_str}) ===\n")
        f.write(f"Symbol  : {coin_state.symbol}\n")
        f.write(f"Strategy: {coin_state.strategy.upper()}\n\n")

        f.write("--- EVALUATION PARAMETERS ---\n")
        f.write(f"Fee rate        : {fee_rate*100:.3f}%\n")
        f.write(f"Slippage        : {slippage_pct*100:.3f}% per fill\n")
        f.write(f"Stop multiplier : {stop_mult}× ATR\n")
        f.write(f"Risk per trade  : {risk_pct*100:.2f}% of wallet\n")
        f.write(f"Min improvement : Sharpe +{min_improve}\n")
        f.write(f"Min trades req  : {min_trades}\n")
        f.write(f"Cooldown        : {cooldown_days} days\n\n")

        f.write("--- MARKET CONTEXT ---\n")
        f.write(f"Daily Asset Price Change : {market_change_pct:+.2f}%\n")
        if len(recent_df) > 0:
            high_day = recent_df["high"].max()
            low_day  = recent_df["low"].min()
            volatility_pct = (high_day - low_day) / low_day * 100
            f.write(f"Daily Volatility Spread  : {volatility_pct:.2f}%\n")
        f.write("\n")

        f.write("--- BOT PERFORMANCE ---\n")
        f.write(f"Current P&L  : ${coin_state.pnl_usd:.4f} ({coin_state.pnl_pct:+.2f}%)\n")
        f.write(f"Total Trades : {total_trades}\n")
        f.write(f"Win Rate     : {win_rate:.1f}%\n\n")

        f.write("--- REGIME ANALYSIS ---\n")
        f.write(f"Market Regime  : {regime_info['regime'].upper()} (ADX={regime_info['adx']})\n")
        f.write(f"Strategy Pool  : {', '.join(candidates)}\n")
        f.write(f"Best Candidate : {best_candidate} (Sharpe={best_score:.3f}, trades={eligible.get(best_candidate, {}).get('num_trades', 0)})\n")
        f.write(f"Current Strat  : {coin_state.strategy} (Sharpe={current_score:.3f})\n")
        score_lines = ", ".join(
            f"{k}={v['sharpe']:.3f}(n={v['num_trades']})"
            for k, v in sorted(scores.items(), key=lambda x: -x[1]["sharpe"])
            if v["sharpe"] != float("-inf")
        )
        f.write(f"All Scores     : {score_lines}\n\n")

        f.write("--- ALGORITHMIC ANALYSIS ---\n")
        if coin_state.pnl_pct < 0:
            f.write("Evaluation: Bot lost capital during this period.\n")
            if market_change_pct < -2.0 and coin_state.pnl_pct > market_change_pct:
                f.write("Why: Market crashed harder than the bot lost. Capital protected. (No Adaptation)\n")
            elif market_change_pct > 2.0:
                f.write("Why: Market surged but bot lost. False breakouts. (TRIGGERING ADAPTATION)\n")
                trigger_adaptation = True
            else:
                f.write("Why: Sideways/choppy market bled the strategy. (TRIGGERING ADAPTATION)\n")
                trigger_adaptation = True
        else:
            f.write("Evaluation: Bot grew capital or stayed flat.\n")
            if market_change_pct < 0 and coin_state.pnl_pct > 0:
                f.write("Why: Positive yield in a crashing market. Excellent. (No Adaptation)\n")
            elif coin_state.pnl_pct > market_change_pct:
                f.write("Why: Bot beat raw market ROI. (No Adaptation)\n")
            else:
                f.write("Why: Profitable but underperformed buy-and-hold. (No Adaptation)\n")
                trigger_adaptation = (
                    best_candidate != coin_state.strategy
                    and best_score - current_score >= min_improve
                )

        f.write("\n")

        if in_cooldown:
            last = _last_switch_date(cfg_data, coin_state.symbol)
            f.write(f"[SYSTEM] Cooldown active (last switch: {last.strftime('%Y-%m-%d') if last else '?'}). No adaptation.\n")
        elif trigger_adaptation:
            f.write("[SYSTEM] Adaptation triggered. Running regime-aware Sharpe ranking...\n")
            new_strat = adapt_strategy(coin_state.symbol, coin_state.strategy, df)
            if new_strat:
                f.write(f"[SYSTEM] Strategy mutated: {coin_state.strategy} → {new_strat}. Thread will hot-reload.\n")
            else:
                f.write("[SYSTEM] No eligible candidate met the improvement threshold. No change.\n")
        else:
            f.write("[SYSTEM] No adaptation needed.\n")

        f.write("\nEnd of Report.\n")
