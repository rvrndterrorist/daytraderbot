# DayTrader Bot

An automated cryptocurrency trading bot that runs 24/7 on Kraken, trading multiple coins simultaneously. Starts with paper (pretend) money so you can watch it run for weeks before risking anything real.

---

## What It Does

The bot watches the price of several coins every hour. When its algorithms spot a good buying opportunity, it buys. When conditions flip or the price drops too far, it sells. It does this automatically, around the clock, without you needing to do anything.

**The full feature set:**

| Feature | What it means in plain English |
|---|---|
| **Multithreaded Fleet** | Trades BTC, ETH, SOL, and ADA at the same time, completely independently |
| **13 Strategy Modules** | RSI, MACD, Bollinger Bands, Supertrend, MA Ribbon, VWAP, DeMark, Fibonacci, StochRSI, MultiRSI, TrendRSI, Combined, Grid |
| **ATR Trailing Stop** | Automatically cuts losses — if a coin drops too far from its peak, the bot exits. The exit level rises as the price rises, locking in profit |
| **Regime Detection** | Detects whether the market is trending (going somewhere) or ranging (going sideways) and picks the right type of strategy automatically |
| **Adaptive Evaluator** | Every night at midnight, ranks all strategies by recent performance and switches to whichever is working best right now |
| **ATR Position Sizing** | Instead of always spending 95% of the wallet, it figures out the right size based on how volatile the coin is. Calmer market = bigger position. Wild market = smaller position. Either way, you risk the same dollar amount per trade (default: 1% of wallet) |
| **Walk-Forward Backtesting** | Tests strategies on data they've never seen (the last 30%). If a strategy only looks good on old data, this catches it |
| **Slippage Modeling** | Backtests now account for the small price penalty you always pay on real market orders (~0.05% per trade). Prevents the backtester from being overly optimistic |
| **Equity Curve Logging** | Every hour, saves a snapshot of the wallet value to `logs/equity_YYYY-MM.csv`. You can see the full history of ups and downs |
| **Weekly Report** | Run `python weekly_report.py` any time for a full breakdown: win rate, Sharpe ratio, max drawdown, fee cost |
| **Plain-English Dashboard** | Open the browser UI and see exactly what the bot is doing, in language that doesn't require a finance degree |
| **Config Hot-Reload** | Change any setting in `config.json` and save — the bot picks it up within seconds, no restart needed |
| **Live Trading Ready** | Add your Kraken API key and flip `"mode": "live"` when you're ready to use real money |
| **Fill Confirmation** | Every live order is polled until confirmed closed — no more "did it fill?" uncertainty |
| **Position Reconciliation** | On startup, compares saved state vs exchange balance; enters safe mode if they don't match |
| **Kill-Switches** | Stops new buys if daily loss exceeds `max_daily_loss_pct` or drawdown exceeds `max_drawdown_pct` |

---

## What to Expect

**Running it 24/7 on paper money:**
- Starting wallet: $20 per coin (configurable)
- Trade frequency: roughly 2–6 trades per coin per month on 1h candles
- Each trade risks ~1% of the wallet (= ~$0.20 on a $20 wallet)
- The trailing stop keeps any single loss from exceeding ~2.5× the initial risk
- After 1–3 months of paper trading you'll have real data to evaluate

**Realistic performance targets (what a healthy system looks like):**
- Sharpe ratio > 1.5 = strategy has real edge
- Sortino ratio > 2.0 = losses are controlled, wins are bigger
- Max drawdown < 20% = wallet never fell more than 20% from its peak
- Fee drag < 3% of starting balance per quarter
- Win rate 45–60% is normal (winning amount per trade matters more than win rate)

**What it cannot do:**
- Guarantee profit. No algorithm can.
- React faster than 1 hour (runs on 1h candles by default)
- Escape a market-wide crash (a stop loss limits the damage but won't prevent it)

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Paper trade with live UI (recommended starting point)
python run.py --ui

# Run strategy comparison (takes ~2 min, shows which strategies work best)
python compare_strategies.py

# Check performance at any time
python weekly_report.py          # last 7 days
python weekly_report.py --days 30
python weekly_report.py --all
```

---

## Configuration (`config.json`)

The most important settings — all hot-reloadable:

```json
{
  "mode": "paper",                     // "paper" = pretend money, "live" = real money
  "fleet": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"],
  "strategy": "ma_ribbon",             // default strategy (overridden nightly by evaluator)
  "timeframe": "1h",
  "starting_balance": 20.0,           // USD per coin for paper trading
  "fee_rate": 0.0026,                  // Kraken taker fee (0.26%)
  "risk_per_trade_pct": 0.01,          // Risk 1% of wallet per trade
  "backtest_slippage_pct": 0.0005      // 0.05% slippage per fill in backtests
}
```

To go live, add your Kraken API key/secret and change `"mode"` to `"live"`.

**Recommended: use environment variables for API keys instead of putting them directly in `config.json`:**
```bash
export KRAKEN_API_KEY="your_key_here"
export KRAKEN_API_SECRET="your_secret_here"
```
Then leave `api_key` and `api_secret` blank in `config.json`. Add `config.json` to `.gitignore` if it contains secrets.

---

## File Overview

```
run.py                   ← Start the bot (+ --ui for dashboard)
compare_strategies.py    ← Backtest all strategies, find the best ones
weekly_report.py         ← Performance report from saved trade data
config.json              ← All settings (hot-reloadable)
ROADMAP.md               ← Feature status and what was built
CRITIQUE.md              ← External reliability review and gap analysis
crypto/
  backtester.py          ← Simulation: fees + slippage + trailing stop + ATR sizing
  stop_loss.py           ← ATR trailing stop (ratchets up, never down)
  regime.py              ← Trending vs ranging market detection (ADX)
  position_sizer.py      ← ATR-based 1%-risk position sizing
  evaluator.py           ← Nightly strategy ranking; config-driven, threshold-gated
  equity_logger.py       ← Hourly wallet snapshots → logs/
  paper_trader.py        ← Fake-money execution + trade logging
  live_trader.py         ← Real execution: fill confirmation, state file, kill-switches
  strategies/            ← 13 strategy modules
logs/                    ← equity_YYYY-MM.csv (created at runtime)
reports/                 ← Daily evaluator reports (created at runtime)
trades_BTC_USDT.csv      ← Per-coin trade history (created at runtime)
live_state_BTC_USDT.json ← Live position state file (created at runtime, live mode only)
dashboard/
  static/index.html      ← Browser dashboard
```
