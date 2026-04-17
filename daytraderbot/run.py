#!/usr/bin/env python3
"""
DayTrader Bot — Fleet Entry Point
==================================
Usage:
  python run.py              # Start multi-threaded fleet trading loop
  python run.py --ui         # Launch browser dashboard at http://localhost:8000
"""

import argparse
import os
import sys
import threading
import time
from datetime import datetime
import json
import webbrowser
import fcntl

import crypto.evaluator as evaluator
from crypto.data import get_exchange, get_candles, get_current_price, wait_for_next_candle
from crypto.backtester import Backtester
from crypto.paper_trader import PaperTrader
from crypto.live_trader import LiveTrader
from crypto.notifier import Notifier
from crypto.state import bot_state
from crypto.stop_loss import TrailingStop, _calc_atr
from crypto.position_sizer import calculate_position_usd
from crypto.regime import detect_regime
from crypto.equity_logger import log_snapshot as log_equity

from crypto.strategies.rsi import RSIStrategy
from crypto.strategies.grid import GridStrategy
from crypto.strategies.bb_rsi import BBRSIStrategy
from crypto.strategies.macd import MACDStrategy
from crypto.strategies.multi_rsi import MultiRSIStrategy
from crypto.strategies.trend_rsi import TrendRSIStrategy
from crypto.strategies.combined import CombinedStrategy
from crypto.strategies.stoch_rsi import StochRSIStrategy
from crypto.strategies.supertrend import SupertrendStrategy
from crypto.strategies.vwap import VWAPStrategy
from crypto.strategies.ma_ribbon import MARibbonStrategy
from crypto.strategies.demark import DeMarkStrategy
from crypto.strategies.fib_retrace import FibRetraceStrategy


def acquire_lock():
    lock_file = open("daytraderbot.lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except BlockingIOError:
        print("\n  [CRITICAL ERROR] DayTrader Bot is already running in another terminal window!")
        print("  Please close the other instance first to prevent API rate limit bans and conflicting duplicate trades.\n")
        sys.exit(1)


def load_config(path: str = "config.json") -> dict:
    with open(path) as f:
        lines = []
        for line in f:
            stripped = line.strip()
            if "//" in stripped and not stripped.startswith('"'):
                line = line[: line.index("//")] + "\n"
            lines.append(line)
        return json.loads("".join(lines))


def build_strategy(cfg: dict):
    name = cfg["strategy"]
    if name == "rsi":
        c = cfg.get("rsi", {})
        return RSIStrategy(period=c.get("period", 14), buy_below=c.get("buy_below", 30), sell_above=c.get("sell_above", 70), trade_pct=c.get("trade_pct", 0.95))
    elif name == "grid":
        c = cfg.get("grid", {})
        return GridStrategy(lower_price=c["lower_price"], upper_price=c["upper_price"], levels=c.get("levels", 10), amount_per_grid=c.get("amount_per_grid", 2.0))
    elif name == "bb_rsi":
        c = cfg.get("bb_rsi", {})
        return BBRSIStrategy(rsi_period=c.get("rsi_period", 14), buy_below=c.get("buy_below", 30), sell_above=c.get("sell_above", 70), bb_period=c.get("bb_period", 20), bb_std=c.get("bb_std", 2.0), trade_pct=c.get("trade_pct", 0.95))
    elif name == "macd":
        c = cfg.get("macd", {})
        return MACDStrategy(window_slow=c.get("window_slow", 26), window_fast=c.get("window_fast", 12), window_sign=c.get("window_sign", 9), trade_pct=c.get("trade_pct", 0.95))
    elif name == "multi_rsi":
        c = cfg.get("multi_rsi", {})
        return MultiRSIStrategy(period=c.get("period", 14), buy_below=c.get("buy_below", 30), sell_above=c.get("sell_above", 70), higher_timeframe=c.get("higher_timeframe", "4h"), trade_pct=c.get("trade_pct", 0.95))
    elif name == "trend_rsi":
        c = cfg.get("trend_rsi", {})
        return TrendRSIStrategy(period=c.get("period", 14), buy_below=c.get("buy_below", 30), sell_above=c.get("sell_above", 70), ema_period=c.get("ema_period", 50), trade_pct=c.get("trade_pct", 0.95))
    elif name == "stoch_rsi":
        c = cfg.get("stoch_rsi", {})
        return StochRSIStrategy(period=c.get("period", 14), smooth1=c.get("smooth1", 3), smooth2=c.get("smooth2", 3), buy_level=c.get("buy_level", 0.20), sell_level=c.get("sell_level", 0.80), trade_pct=c.get("trade_pct", 0.95))
    elif name == "supertrend":
        c = cfg.get("supertrend", {})
        return SupertrendStrategy(period=c.get("period", 10), multiplier=c.get("multiplier", 3.0), trade_pct=c.get("trade_pct", 0.95))
    elif name == "vwap":
        c = cfg.get("vwap", {})
        return VWAPStrategy(period=c.get("period", 14), dev_multiplier=c.get("dev_multiplier", 1.5), trade_pct=c.get("trade_pct", 0.95))
    elif name == "ma_ribbon":
        c = cfg.get("ma_ribbon", {})
        return MARibbonStrategy(ema1=c.get("ema1", 5), ema2=c.get("ema2", 21), ema3=c.get("ema3", 55), ema4=c.get("ema4", 144), sma1=c.get("sma1", 100), sma2=c.get("sma2", 200), trade_pct=c.get("trade_pct", 0.95))
    elif name == "demark":
        c = cfg.get("demark", {})
        return DeMarkStrategy(setup_length=c.get("setup_length", 9), offset=c.get("offset", 4), trade_pct=c.get("trade_pct", 0.95))
    elif name == "fib_retrace":
        c = cfg.get("fib_retrace", {})
        return FibRetraceStrategy(window=c.get("window", 100), buy_level=c.get("buy_level", 0.382), sell_level=c.get("sell_level", 1.272), threshold_pct=c.get("threshold_pct", 0.005), trade_pct=c.get("trade_pct", 0.95))
    elif name == "combined":
        sub_strats = []
        for s in cfg.get("combined", {}).get("strategies", []):
            temp_cfg = dict(cfg)
            temp_cfg["strategy"] = s
            sub_strats.append(build_strategy(temp_cfg))
        return CombinedStrategy(strategies=sub_strats, threshold=cfg.get("combined", {}).get("threshold", 2), trade_pct=cfg.get("combined", {}).get("trade_pct", 0.95))
    else:
        raise ValueError(f"Unknown strategy '{name}'.")


def get_symbol_strategy(cfg: dict, symbol: str):
    my_cfg = dict(cfg)
    if "overrides" in cfg and symbol in cfg["overrides"]:
        for k, v in cfg["overrides"][symbol].items():
            my_cfg[k] = v
    return build_strategy(my_cfg), my_cfg


def trading_loop(cfg: dict, exchange, symbol: str, notifier: Notifier):
    """Isolated threaded loop for a specific Fleet coin."""
    cfg_path = "config.json"

    strategy, my_cfg = get_symbol_strategy(cfg, symbol)
    timeframe = my_cfg.get("timeframe", "1h")
    trade_pct = my_cfg.get(my_cfg["strategy"], {}).get("trade_pct", 0.95)
    starting_balance = my_cfg.get("starting_balance", 20.0)

    if my_cfg.get("mode") == "live":
        trader = LiveTrader(exchange, symbol, fee_rate=my_cfg.get("fee_rate", 0.001),
                            notifier=notifier, config=my_cfg)
    else:
        trader = PaperTrader(starting_balance=starting_balance, fee_rate=my_cfg.get("fee_rate", 0.001),
                             symbol=symbol, strategy=my_cfg["strategy"])

    bot_state.set_config(symbol, my_cfg["strategy"], my_cfg.get("mode", "paper"), timeframe, starting_balance)
    bot_state.log(symbol, f"Fleet Thread Active — {my_cfg['strategy'].upper()}")

    ticker = threading.Thread(target=price_ticker, args=(exchange, symbol, 15), daemon=True)
    ticker.start()

    try: last_mtime = os.path.getmtime(cfg_path)
    except: last_mtime = 0

    # Trailing stop — lives outside the candle loop so it persists across iterations
    active_stop: TrailingStop | None = None

    while True:
        # --- Hot reload ---
        try:
            current_mtime = os.path.getmtime(cfg_path)
            if current_mtime != last_mtime:
                last_mtime = current_mtime
                try:
                    new_cfg = load_config(cfg_path)
                    strategy, my_cfg = get_symbol_strategy(new_cfg, symbol)
                    timeframe = my_cfg.get("timeframe", "1h")
                    trade_pct = my_cfg.get(my_cfg["strategy"], {}).get("trade_pct", 0.95)
                    bot_state.set_config(symbol, my_cfg["strategy"], my_cfg.get("mode", "paper"), timeframe, my_cfg.get("starting_balance", 20.0))
                    if isinstance(trader, PaperTrader):
                        trader.strategy = my_cfg["strategy"]
                    bot_state.log(symbol, f"Hot-reload: now running {my_cfg['strategy'].upper()}")
                except Exception as e:
                    bot_state.log(symbol, f"WARNING: Bad config ignored ({e})")
        except: pass

        try:
            # Fetch enough candles for the evaluator's 30-day rolling window
            df = get_candles(exchange, symbol, timeframe, limit=800)
            coin_state = bot_state.get_coin(symbol)

            # --- Daily Adaptive Evaluator ---
            current_date = datetime.now().date()
            if not getattr(coin_state, "last_eval_date", None):
                coin_state.last_eval_date = current_date
            if current_date > coin_state.last_eval_date:
                try:
                    evaluator.evaluate_daily(coin_state, df)
                    bot_state.log(symbol, "Midnight audit complete. Regime-aware Sharpe ranking applied.")
                except Exception as e:
                    bot_state.log(symbol, f"Evaluator error: {e}")
                coin_state.last_eval_date = current_date

            # --- Regime detection ---
            try:
                regime_info = detect_regime(df)
                bot_state.update_regime(symbol, regime_info["regime"], regime_info["adx"])
            except Exception:
                pass

            price = get_current_price(exchange, symbol)

            # --- Live kill-switch check (daily loss / drawdown limits) ---
            if isinstance(trader, LiveTrader):
                trader.check_kill_switches(price)

            # --- Update trailing stop (ratchet up if price rose) ---
            if active_stop is not None:
                active_stop.update(price, df)
                bot_state.update_stop(symbol, active_stop.stop_price)

            # --- Stop loss check — runs BEFORE strategy signal ---
            if active_stop is not None and active_stop.is_triggered(price):
                res = trader.sell(price, reason="STOP")
                if res:
                    notifier.trade(res, trader.status(price))
                    bot_state.add_trade(symbol, res)
                    bot_state.log(symbol, f"STOP LOSS HIT @ ${price:,.2f} | stop was ${active_stop.stop_price:,.2f} | P&L=${res.get('pnl', 0):.4f}")
                active_stop = None
                bot_state.update_stop(symbol, None)

            # --- Strategy signal ---
            sig = strategy.signal(df)
            indicator_info = strategy.get_indicator_info(df, price=price)

            rsi_val = None
            if "RSI=" in indicator_info and "StochRSI=" not in indicator_info:
                try: rsi_val = float(indicator_info.split("RSI=")[1].split()[0])
                except: pass

            bot_state.update_candles(symbol, df)
            bot_state.update_tick(symbol, price, sig, rsi=rsi_val, grid_info=indicator_info)

            if sig == "buy":
                # Dynamic position sizing: risk exactly risk_per_trade_pct of wallet per trade
                wallet_value = trader.portfolio_value(price)
                atr = _calc_atr(df)
                risk_pct = my_cfg.get("risk_per_trade_pct", 0.01)
                position_usd = calculate_position_usd(wallet_value, price, atr, risk_pct)
                fraction = min(position_usd / wallet_value, 0.95) if wallet_value > 0 else trade_pct
                res = trader.buy(price, fraction=fraction)
                if res:
                    active_stop = TrailingStop(price, df)
                    bot_state.update_stop(symbol, active_stop.stop_price)
                    notifier.trade(res, trader.status(price))
                    bot_state.add_trade(symbol, res)
                    bot_state.log(symbol, f"BUY @ ${price:,.2f} | stop set @ ${active_stop.stop_price:,.2f} | {indicator_info}")
                else:
                    bot_state.log(symbol, f"HOLD (No Funds)")
            elif sig == "sell":
                res = trader.sell(price)
                if res:
                    active_stop = None
                    bot_state.update_stop(symbol, None)
                    notifier.trade(res, trader.status(price))
                    bot_state.add_trade(symbol, res)
                    bot_state.log(symbol, f"SELL @ ${price:,.2f} P&L=${res.get('pnl', 0):.4f}")
                else:
                    bot_state.log(symbol, f"HOLD (No Position)")
            else:
                stop_info = f" | stop=${active_stop.stop_price:,.2f}" if active_stop else ""
                bot_state.log(symbol, f"HOLD ${price:,.2f} — {indicator_info}{stop_info}")

            # --- Sync portfolio to state ---
            if isinstance(trader, PaperTrader):
                bot_state.update_portfolio(symbol, trader.balance_usd, trader.position_size, trader.position_entry_price, trader.portfolio_value(price), trader.trade_count)
            else:
                bot_state.update_portfolio(symbol, 0, 0, 0, trader.portfolio_value(price), trader.trade_count)
            bot_state.push()

            # --- Equity curve snapshot (every candle) ---
            try:
                coin_snap = bot_state.get_coin(symbol)
                log_equity(
                    symbol=symbol,
                    strategy=my_cfg["strategy"],
                    regime=coin_snap.regime,
                    adx=coin_snap.adx,
                    price=price,
                    balance_usd=coin_snap.balance_usd,
                    position_size=coin_snap.position_size,
                    total_value=coin_snap.total_value,
                    starting_balance=coin_snap.starting_balance,
                    stop_price=coin_snap.stop_price,
                )
            except Exception:
                pass

        except Exception as e:
            bot_state.log(symbol, f"ERROR: {e}")
            time.sleep(30)

        wait_for_next_candle(timeframe)


def price_ticker(exchange, symbol: str, interval: int = 15):
    while True:
        try:
            bot_state.get_coin(symbol).current_price = get_current_price(exchange, symbol)
            bot_state.push()
        except: pass
        time.sleep(interval)


def main():
    _lock = acquire_lock()
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", action="store_true", help="Launch dashboard")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    cfg = load_config()
    notifier = Notifier(telegram_token=cfg.get("telegram_token", ""), telegram_chat_id=cfg.get("telegram_chat_id", ""))
    
    print("\n" + "=" * 55)
    print("  DayTrader Bot — Multithreaded Fleet Engine")
    print("=" * 55)
    
    if args.ui:
        from dashboard.app import start_server
        start_server(host="127.0.0.1", port=args.port)
        print(f"  Dashboard: http://localhost:{args.port}")
        time.sleep(1)
        webbrowser.open(f"http://localhost:{args.port}")

    fleet = cfg.get("fleet", [cfg.get("symbol", "BTC/USDT")])
    if not fleet: fleet = ["BTC/USDT"]

    needs_auth = cfg.get("mode") == "live"
    exchange = get_exchange(cfg.get("exchange", "kraken"), api_key=cfg.get("api_key", "") if needs_auth else "", api_secret=cfg.get("api_secret", "") if needs_auth else "")

    print(f"  Launching {len(fleet)} Isolated Threads: {', '.join(fleet)}\n")
    
    for sym in fleet:
        threading.Thread(target=trading_loop, args=(cfg, exchange, sym, notifier), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down master engine...")
        sys.exit(0)


if __name__ == "__main__":
    main()
