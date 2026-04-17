# DayTrader Bot — Agent Handoff Document

## What This Project Is

An institutional-grade algorithmic cryptocurrency trading suite built in Python for a non-technical user.
- Operates totally headlessly and securely toggles between live and paper modes.
- Track parallel cryptocurrency pairs simultaneously via a massively **Multithreaded Fleet Engine**.
- Automatically diagnoses its own mathematical parameters and mutates its own configurations nightly using the **Adaptive Evaluator DNA**.
- Shifts its logic dynamically mid-flight utilizing a robust Config Hot-Reloader.

---

## Current State (Working & Finalized)

### File Structure
```
daytraderbot/
├── config.json              ← HOT-RELOADABLE — fleet, strategy, risk_per_trade_pct, backtest_slippage_pct
├── run.py                   ← Threaded Engine (loops over cfg["fleet"], one thread per symbol)
├── compare_strategies.py    ← Walk-forward strategy comparison (70/30 train/OOS split + slippage)
├── weekly_report.py         ← Sharpe/Sortino/Calmar/drawdown report from trade CSVs + equity logs
├── AGENT.md                 ← This document
├── ROADMAP.md               ← Feature gaps, implementation status
├── README.md                ← Setup & usage
├── crypto/
│   ├── evaluator.py         ← Nightly audit: regime-aware Sharpe ranking, writes to reports/, mutates config.json
│   ├── data.py              ← CCXT data fetcher
│   ├── state.py             ← Thread-safe BotState/CoinState singletons wired to WebSocket
│   ├── paper_trader.py      ← Simulated execution; writes trades_SYMBOL.csv per coin
│   ├── live_trader.py       ← Real exchange execution (Kraken)
│   ├── backtester.py        ← Historical simulation with fee + slippage modeling
│   ├── stop_loss.py         ← ATR chandelier trailing stop (ratchets up, never down)
│   ├── regime.py            ← ADX-based market regime detection (trending vs ranging)
│   ├── position_sizer.py    ← ATR fixed-fractional position sizing (1% wallet risk per trade)
│   ├── equity_logger.py     ← Hourly balance snapshots → logs/equity_YYYY-MM.csv
│   └── strategies/          ← 13 strategies
│       ├── rsi.py, grid.py, bb_rsi.py, macd.py, multi_rsi.py, trend_rsi.py, stoch_rsi.py
│       ├── supertrend.py, vwap.py, ma_ribbon.py, demark.py, fib_retrace.py, combined.py
└── dashboard/
    └── static/index.html    ← Plain-English live dashboard (LightweightCharts, WebSocket)
```

### Key Technical Features:
1. **Multithreaded Fleet Engine** — One isolated thread per symbol. Thread-safe `BotState`/`CoinState` singletons in `state.py`. Single-instance lock (`daytraderbot.lock`) prevents duplicate processes.
2. **ATR Trailing Stop** — `crypto/stop_loss.py`. Chandelier-style: placed at entry − 2.5×ATR, ratchets upward as price rises, never lowers. Fires before strategy signal check each candle.
3. **Regime Detection** — `crypto/regime.py`. ADX > 25 = trending (uses ma_ribbon/supertrend/macd/demark/fib_retrace). ADX ≤ 25 = ranging (uses rsi/bb_rsi/stoch_rsi/vwap/trend_rsi).
4. **Adaptive Evaluator** — `crypto/evaluator.py`. Nightly Sharpe-ranked rolling backtest over 30 days of candles. Picks best regime-appropriate strategy and writes override to `config.json`. Hot-reload picks it up automatically.
5. **Walk-Forward Backtester** — `compare_strategies.py`. 70/30 train/OOS split + slippage modeling. Sort by OOS return — the only metric that matters.
6. **ATR Position Sizing** — `crypto/position_sizer.py`. Sizes each trade so that if the stop fires, the loss is exactly `risk_per_trade_pct` (default 1%) of total wallet. Smaller position in volatile markets, larger in calm ones.
7. **Slippage Modeling** — `crypto/backtester.py`. Buy fills at `price × (1 + slippage_pct)`, sell fills at `price × (1 − slippage_pct)`. Default 0.05% per side, configurable via `backtest_slippage_pct`.
8. **Equity Curve Logging** — `crypto/equity_logger.py`. Hourly snapshots to `logs/equity_YYYY-MM.csv`. Tracks drawdown from rolling peak.
9. **Weekly Report** — `weekly_report.py`. CLI tool: `python weekly_report.py [--days N] [--all]`. Outputs Sharpe, Sortino, Calmar, drawdown, fee drag, win rate per symbol.
10. **Plain-English Dashboard** — `dashboard/static/index.html`. LightweightCharts candlesticks, regime badge, stop price, plain-language strategy explanations. Run via `python run.py --ui`.

### Current Config
- `fleet`: `["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]`
- Timeframe: `1h`
- Global Strategy: `ma_ribbon`
- Mode: `paper`
- Risk per trade: `1%` of wallet (`risk_per_trade_pct: 0.01`)
- Backtest slippage: `0.05%` per fill (`backtest_slippage_pct: 0.0005`)

---

## Current Status

Core features complete. Four reliability gaps identified in `CRITIQUE.md` and tracked in `ROADMAP.md`.

**Gap 1 — Backtester parity: DONE**
`crypto/backtester.py` now simulates the trailing stop (exits if candle low <= stop price) and ATR-based position sizing, matching the live loop. `compare_strategies.py` passes `stop_multiplier` and `risk_per_trade_pct` from config.

**Gap 2 — Evaluator config params: DONE**
`crypto/evaluator.py` fully rewritten. Uses real per-strategy params from config, real fee/slippage/stop/risk values in Backtester. Daily report prints all params used.

**Gap 3 — Evaluator improvement threshold: DONE**
`adapt_strategy()` enforces min Sharpe improvement (0.3), min completed trades (5), cooldown (3 days). New config keys: `eval_min_sharpe_improvement`, `eval_min_trades`, `eval_cooldown_days`.

**Gap 4 — Live trader safety: DONE**
`crypto/live_trader.py` fully rewritten. Fill confirmation, accurate fill price, `live_state_SYMBOL.json` persistence, startup reconciliation (safe mode on mismatch), kill-switches (`max_daily_loss_pct`, `max_drawdown_pct`). New config keys: `max_daily_loss_pct`, `max_drawdown_pct`.

**All four CRITIQUE.md gaps resolved. Bot is live-trading ready.**

**Do not start Gap 4 until Gaps 2 and 3 are done.**
