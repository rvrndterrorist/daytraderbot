# DayTrader Bot — Critical Review & Profitability Roadmap

This document is intentionally blunt. The question isn’t “can this place trades?”—it can. The question is whether it can **produce a repeatable edge after fees/slippage** and **survive live execution realities**.

## Summary verdict

- **Will it run?** Yes. Paper trading + dashboard + multi-symbol threads + logs should run end-to-end.
- **Will it trade live safely?** Not yet. `crypto/live_trader.py` can submit orders, but the system lacks the reconciliation and guardrails needed to prevent silent failure modes.
- **Will it be profitable as-is?** Unlikely. Most included strategies are standard TA templates; the current evaluation loop is not strict enough to distinguish noise from edge.

## What’s strong (keep these)

- **Clear modular design**: data fetcher, strategies, execution adapters, state, dashboard.
- **Operational quality features** many bots skip: single-instance lock, hot reload, per-symbol isolation, equity snapshots, nightly evaluation reports.
- **Risk building blocks exist**: ATR trailing stop (`crypto/stop_loss.py`) and position sizing (`crypto/position_sizer.py`) in the live loop.

## Critical gaps blocking “profitable tool”

### 1) Backtests do not match live behavior (major)

Live trading uses:
- ATR trailing stop (can exit before the strategy’s “sell”)
- ATR-based sizing (fraction varies by volatility)

But `crypto/backtester.py` currently simulates:
- signal-based buy/sell only
- fixed `trade_pct` sizing

**Consequence**: strategy comparison, evaluator scoring, and “robustness” conclusions can be wrong. You may select strategies that only work in the simplified simulator.

### 2) Evaluator likely selects the wrong “best” strategy (major)

`crypto/evaluator.py` scores strategies using defaults:
- `build_strategy({"strategy": name, name: {}})` ignores tuned params in `config.json`
- `Backtester(... fee_rate=0.0026)` hardcodes fee rate and uses default slippage (not config-driven)

**Consequence**: your “adaptive DNA” may rotate based on a different strategy configuration than what you actually run, making the adaptation unreliable.

### 3) Live execution is naive and not self-verifying (major)

`crypto/live_trader.py` submits market orders but does not:
- confirm fills / handle partial fills
- compute and store average fill price
- reconcile internal position vs exchange position
- implement retry/backoff policies per error class
- enforce per-symbol and global risk limits using exchange-truth balances

**Consequence**: in live trading, you can drift into unknown state (thinking you’re flat when you’re not, double-selling, holding dust, etc.). That’s how real accounts get damaged even when “the strategy is fine.”

### 4) Shared CCXT client + polling cadence can cause rate-limit issues (major)

The fleet shares one `exchange` instance across threads. Each thread:
- calls ticker frequently (every 15s) via `fetch_ticker`
- fetches candles each loop
- fetches balances in live mode on each buy/sell/status call

**Consequence**: intermittent API failures, bans, stale reads. These look like “random bot bugs” but are actually architecture problems.

### 5) You’re currently building a *strategy zoo*, not an edge factory

Thirteen strategies doesn’t help much if the evaluation process:
- is not realistic
- is not statistically disciplined
- can overfit via frequent selection among many candidates

**Consequence**: backtest optimism and live disappointment.

## What “profit-ready” actually means (acceptance criteria)

Treat these as gates. Do not go live until they are satisfied.

### Gate A — Simulator/production parity

- Backtester reproduces the live loop’s key mechanics:
  - fees + slippage
  - ATR sizing (or a provably equivalent sizing model)
  - trailing stop exits
  - (ideally) stop triggering logic that’s not “end-of-candle only”

### Gate B — Strategy selection rigor

- Evaluator uses real config parameters, real fee/slippage assumptions, and doesn’t silently fall back to defaults.
- Walk-forward evaluation includes:
  - multiple periods (not one 70/30 split)
  - stability checks (performance consistency, not just best return)
  - a baseline comparison (e.g., buy-and-hold, or simple trend-following baseline)

### Gate C — Live execution safety

- Order lifecycle handling:
  - place → confirm → filled/partial → final average fill
  - retries with backoff
  - reconciliation (positions and cash)
- Risk kill-switches:
  - max daily loss
  - max drawdown
  - max trades/day
  - cooldown after stop-out(s)
- Observability:
  - errors and abnormal states are surfaced immediately (Telegram + logs)

## The roadmap to move from learning tool → profit attempt

This is ordered by highest leverage and lowest “illusion risk.”

### Step 1 — Fix evaluator to be honest and config-driven

**Change**:
- Build each candidate strategy using parameters from `config.json` (not empty dict defaults).
- Pass `fee_rate` and `backtest_slippage_pct` from config into `Backtester`.

**Acceptance**:
- A daily report explicitly prints: fee rate used, slippage used, strategy params used.
- Running live with overrides uses the exact same parameterization used in evaluation.

### Step 2 — Upgrade backtester to reflect live risk controls

**Change**:
- Implement trailing-stop exits (same ATR window and multiplier logic as `TrailingStop`).
- Implement ATR-based sizing (matching `calculate_position_usd`).
- Model stop triggers at least approximately:
  - simplest: stop triggers if candle low <= stop price (for long-only)
  - fill price: stop price minus slippage (conservative)

**Acceptance**:
- A paper trading run and a “replay backtest” over the same candles produce comparable trade counts and drawdowns (not identical, but directionally similar).

### Step 3 — Stop picking “best of many” without penalizing selection

Selecting the best of \(N\) strategies every day creates a **multiple-comparisons problem**. You will almost always “find a winner” in noise.

**Change**:
- Reduce candidate set per regime to a smaller, curated set *or*
- Require improvement thresholds:
  - new strategy must beat current by margin \( \Delta \) (e.g., Sharpe +0.3 or return +X%) over a reasonable window
  - include turnover penalty (switching cost)
  - include a minimum trade count

**Acceptance**:
- Strategy switches become rare and explainable; performance doesn’t depend on frequent mutation.

### Step 4 — Live trader must reconcile and persist state

**Change**:
- Maintain a per-symbol persistent state file:
  - last known position size, entry, stop, last order id, last sync time
- On every loop:
  - fetch current position/balances
  - if mismatch from expected → enter “safe mode” (no new trades) and alert
- After order placement:
  - fetch order status until terminal; record average fill; record fees if available

**Acceptance**:
- You can kill the process and restart and it resumes safely without doubling positions.

### Step 5 — Portfolio-level risk and constraints

Right now each symbol trades independently, but in reality the portfolio is coupled:
- correlations spike in crypto crashes
- simultaneous stop-outs can compound losses

**Change**:
- Add global risk caps:
  - max % of total equity deployed
  - max simultaneous open positions
  - correlation/“market risk” proxy (e.g., BTC trend filter gating alts)

**Acceptance**:
- Worst-case scenario under market crash is bounded by explicit caps, not by hope.

### Step 6 — Edge research: treat this as a research pipeline, not a bot

Most profitable systems win by:
- regime filters, better features, realistic execution assumptions
- avoiding trades when expected edge is low

Concrete directions (more promising than “more TA indicators”):
- **volatility targeting** (you already started this)
- **filters** (avoid chop): trend filters, volatility contraction/expansion, spread/liquidity checks
- **time-of-day / weekday effects** (crypto has structure)
- **label leakage prevention** (ensure signals never use future data; verify indicator implementations)
- **out-of-sample rolling** (walk-forward across many windows; report distribution, not single score)

## Known hygiene issues (easy wins)

- **Secrets**: don’t store live API keys in `config.json`. Use environment variables or an ignored secrets file.
- **`.venv/` in repo**: consider moving it outside the project directory to reduce accidental packaging/scanning noise.
- **`config.json` contains `trade_pct` per strategy**: if ATR sizing is the standard, consider deprecating `trade_pct` entirely for non-grid strategies to avoid confusion.

## If you do only three things

1) **Make evaluation config-driven and honest** (Step 1).
2) **Make the backtester match live stop/sizing** (Step 2).
3) **Make live trading reconcile positions and order fills** (Step 4).

Until those are done, any “profitability” you see is likely to be a simulator artifact or selection bias, not durable edge.

