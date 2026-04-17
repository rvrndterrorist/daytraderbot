# DayTrader Bot — Roadmap & Known Gaps

This document explains what the known gaps in the bot are, why they matter
in plain English, and exactly how they'll be implemented.

---

## What's Already Done

| Feature | Status | What it does |
|---|---|---|
| ATR Trailing Stop | ✅ Done | Automatically exits a losing trade before it becomes a disaster |
| Regime Detection | ✅ Done | Detects trending vs ranging markets, selects right strategy type |
| Adaptive Evaluator | ✅ Done | Nightly Sharpe-based strategy rotation instead of random switching |
| Walk-Forward Backtest | ✅ Done | Tests on data the strategy has never seen (real robustness test) |
| Per-symbol trade logs | ✅ Done | `trades_BTC_USDT.csv` etc. — full history with strategy column |
| Equity curve logging | ✅ Done | `logs/equity_YYYY-MM.csv` — hourly wallet snapshots |
| Weekly report | ✅ Done | `python weekly_report.py` — Sharpe, Sortino, drawdown, fee drag |
| Plain-English dashboard | ✅ Done | `python run.py --ui` — no jargon |
| Slippage modeling | ✅ Done | `crypto/backtester.py` — 0.05% penalty on every simulated fill |
| Dynamic position sizing | ✅ Done | `crypto/position_sizer.py` — ATR-based 1% fixed-risk sizing |
| Backtester parity | ✅ Done | `crypto/backtester.py` — trailing stop + ATR sizing in simulation |
| Evaluator config-driven | ✅ Done | `crypto/evaluator.py` — uses real params, not defaults |
| Evaluator thresholds | ✅ Done | Min Sharpe improvement, min trades, cooldown between switches |
| Live trader safety | ✅ Done | Fill confirmation, state file, reconciliation, kill-switches |

---

## Open Gaps — Priority Order

These must be fixed before the bot's backtest results and strategy rankings
can be trusted. Do not go live until Gate C (Gap 4) is satisfied.

| # | Gap | Status | Blocks |
|---|-----|--------|--------|
| 1 | Backtester trailing stop + ATR sizing | ✅ Done | Strategy rankings were unrealistic without this |
| 2 | Evaluator uses real config params | ✅ Done | Nightly adaptation now uses actual config params |
| 3 | Evaluator improvement threshold | ✅ Done | Cooldown + min trades + min Sharpe improvement gate |
| 4 | Live trader fill confirmation + reconciliation | ✅ Done | Safe to run with real money |

**All four gaps complete. See "What's Already Done" table above.**

---

## Gap 1 — Backtester Doesn't Match Live Behavior

### What the bot currently does
When `compare_strategies.py` tests a strategy, it only exits when the
strategy says "sell." But in real life, the trailing stop often fires
**first** — cutting the trade short before the strategy ever signals a sell.
The backtester also uses a fixed 95% of balance per trade, but live trading
now uses ATR-based sizing that varies with volatility.

### Why that's a problem
You're comparing strategies using a simulator that behaves differently from
the actual live loop. A strategy might look great in the backtester (it held
through a recovery) but terrible live (the trailing stop kicked it out at
the bottom). You can't trust the leaderboard in `compare_strategies.py`
until the simulator runs the same rules as the bot.

### How it will be implemented

**`crypto/backtester.py`**:
- Add a trailing stop simulation inside `run()`:
  - On buy: initialize `highest_price = fill_price`, `stop_price = fill_price − ATR × 2.5`
  - Each candle: ratchet `highest_price` up, recalculate stop
  - If candle low <= stop_price → exit at `stop_price × (1 − slippage_pct)` before checking sell signal
- Add ATR-based sizing matching `calculate_position_usd()`:
  - On buy: compute `fraction` using wallet value, current ATR, and `risk_per_trade_pct` from config
  - Fall back to `trade_pct` if ATR is unavailable

**Files that change:**
- `crypto/backtester.py` — add stop sim + ATR sizing; new params `stop_multiplier`, `risk_per_trade_pct`
- `compare_strategies.py` — pass new params from config

**Expected impact:**
Trade counts and drawdown numbers from `compare_strategies.py` will closely
mirror what the bot actually does on live candles. Strategy rankings become
meaningful.

---

## Gap 2 — Evaluator Uses Wrong Strategy Parameters

### What the bot currently does
Every night the evaluator runs backtests to rank strategies. But it builds
each strategy with an empty config: `{"strategy": name, name: {}}`. This
means all the tuned settings in `config.json` (RSI periods, ATR multiplier,
buy/sell thresholds, etc.) are silently ignored and replaced with hardcoded
defaults. It also hardcodes the fee rate rather than reading it from config.

### Why that's a problem
The evaluator is deciding "ma_ribbon is better than supertrend right now"
— but it's testing a different version of each strategy than what's actually
running. It's like picking a race winner by testing the cars with the
wrong engines installed.

### How it will be implemented

**`crypto/evaluator.py`**:
- Load `config.json` inside `adapt_strategy()` and pass the full per-strategy
  config dict (e.g. `cfg.get("ma_ribbon", {})`) to `build_strategy()` rather
  than an empty dict
- Read `fee_rate` and `backtest_slippage_pct` from config instead of hardcoding
- Print the parameters used in the daily report so you can verify them

**Files that change:**
- `crypto/evaluator.py` — load and pass real config params

**Expected impact:**
The nightly adaptation will rank strategies on an honest playing field —
using the same parameters that are actually running — making the rotation
decision reliable.

---

## Gap 3 — Evaluator Switches Too Eagerly (Multiple Comparisons Problem)

### What the bot currently does
Every night the evaluator picks whichever of the 5–8 candidate strategies
scored highest in the last 30 days and switches to it — even if the margin
over the current strategy is tiny.

### Why that's a problem
If you test 8 strategies every night, you will almost always find *one* that
looks better just by chance — especially with only 30 days of data. The more
candidates you test, the more likely you are to pick noise. The bot ends up
switching constantly for no real edge, burning fees each time a new position
opens under a different strategy.

### How it will be implemented

**`crypto/evaluator.py`**:
- Only switch if the best candidate beats the current strategy by a minimum
  margin (e.g. Sharpe +0.3 over the evaluation window)
- Require a minimum number of completed trades (e.g. ≥ 5) before a strategy
  is eligible to win — strategies with 1 lucky trade shouldn't rank first
- Add a cooldown: don't switch again within N days of the last switch

**Config additions:**
```json
"eval_min_sharpe_improvement": 0.3,
"eval_min_trades": 5,
"eval_cooldown_days": 3
```

**Expected impact:**
Strategy rotations become rare and deliberate — only when there's a real
signal that something is working better. Performance stops depending on
luck of the nightly draw.

---

## Gap 4 — Live Trader Cannot Verify Its Own State

### What the bot currently does
`crypto/live_trader.py` submits a market order and moves on. It never
checks whether the order filled, never handles a partial fill, and if you
restart the bot mid-position it has no memory of what it was holding.

### Why that's a problem
In live trading, exchanges sometimes:
- Fill orders partially (you bought 0.003 BTC instead of 0.005)
- Reject orders silently due to balance edge cases
- Experience momentary outages mid-order

If the bot thinks it's flat (no position) but the exchange says it holds
$12 of SOL, the next buy will over-allocate. If the bot thinks it holds a
position but the exchange cancelled the order, the next stop-loss sell will
fail silently. These scenarios cause real account damage.

### How it will be implemented

**`crypto/live_trader.py`**:
- After placing an order, poll `fetch_order()` until status is `closed`
  or `canceled` (with timeout + backoff)
- Record actual average fill price from the order response
- Write a per-symbol state file (`live_state_BTC_USDT.json`) with:
  `position_size`, `entry_price`, `last_order_id`, `last_sync_time`
- On startup: load the state file and reconcile against exchange balance —
  if they disagree, log a warning and skip new trades for that symbol
- Add kill-switches: max daily loss %, max drawdown % — if breached,
  stop trading that symbol and send a Telegram alert

**Config additions:**
```json
"max_daily_loss_pct": 5.0,
"max_drawdown_pct": 20.0
```

**Files that change:**
- `crypto/live_trader.py` — fill confirmation, state persistence, reconciliation
- `run.py` — pass kill-switch thresholds; handle "safe mode" flag per symbol

**Expected impact:**
The bot can be restarted safely at any time. Partial fills are handled
correctly. You always know what it holds and why. This is the minimum bar
for risking real money.

---

## Hygiene Items (Small, Do Anytime)

These don't block paper trading but should be cleaned up before going live:

- **API keys in `config.json`**: move to environment variables or a
  gitignored `.env` file so secrets never end up in version control
- **`trade_pct` per strategy**: now that ATR sizing is the standard,
  `trade_pct` in each strategy block is misleading. Consider removing it
  from non-grid strategies or adding a comment that it's ignored when
  `risk_per_trade_pct` is set
- **Shared CCXT instance**: one `exchange` object is used across all threads.
  Under heavy load this can cause rate-limit errors. Consider one instance
  per thread or a shared rate-limiter wrapper
