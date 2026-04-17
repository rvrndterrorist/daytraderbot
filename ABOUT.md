# What Is This?

This is an automated trading bot. You turn it on, point it at a few
cryptocurrencies, and it watches the market 24 hours a day and trades
on your behalf — buying when conditions look good, selling when they
don't, and protecting itself from big losses automatically.

You don't need to watch charts. You don't need to know when to buy or
sell. The bot handles all of that.

---

## The Core Idea

Most people lose money in crypto not because they picked bad coins, but
because of two things:

1. **They hold through losses hoping things recover** — sometimes they
   do, sometimes they wipe out the account.
2. **They trade on emotion** — panic selling at the bottom, FOMO buying
   at the top.

This bot removes both problems. It follows rules, not feelings. And it
cuts losses automatically before they get out of hand.

---

## What It Actually Does

**It watches prices every hour.**
Every 60 minutes it looks at the price history for each coin and asks:
"Does this look like a good time to buy?" If yes, it buys. If not, it
does nothing.

**It protects every position with a safety net.**
The moment it buys, it sets an automatic exit point below the purchase
price. If the coin drops to that point, it sells immediately — no
hesitation, no "maybe it'll recover." This is called a trailing stop,
and it's the most important protection the bot has.

The exit point isn't fixed. As the price goes up, the exit point rises
with it — locking in more and more profit. If the coin then turns and
falls, it gets out with whatever profit was locked in.

**It sizes each trade based on risk, not greed.**
Instead of always spending 95% of the wallet, the bot figures out exactly
how much to buy so that if the stop fires, it only loses 1% of the total
wallet. In a wild, volatile market it buys less. In a calm market it buys
more. The dollar amount at risk stays roughly the same no matter what.

**It reads market conditions and picks the right strategy.**
Not every strategy works in every market. Some work best when prices are
trending in a direction. Others work best when prices are bouncing up and
down in a range. Every night at midnight the bot detects which type of
market it's in and checks whether the strategy it's using is still the
right one for those conditions.

**It switches strategies when there's a real reason to.**
The nightly check doesn't just blindly switch — it runs a 30-day
simulation of several candidate strategies and only switches if a
different one would have performed meaningfully better. It also won't
switch again for 3 days after the last switch, so it doesn't thrash
back and forth on noise.

**It keeps a full paper trail.**
Every trade is logged: what was bought, at what price, when, using which
strategy, what the fee was, and what the profit or loss was. Every hour
it takes a snapshot of the total wallet value. You can run a report at
any time and see Sharpe ratio, win rate, max drawdown, and fee drag.

---

## The Strategies

The bot has 13 different trading strategies built in. Here's what each
one is actually doing in plain English:

| Strategy | What it's watching for |
|---|---|
| **RSI** | "Is this coin oversold? Has everyone already panic-sold and is it due for a bounce?" |
| **MACD** | "Have two different trend lines just crossed? That usually signals a direction change." |
| **Bollinger Bands + RSI** | "Has the price hit the outer edge of its normal range while also being oversold?" |
| **Stochastic RSI** | "A more sensitive version of RSI — catches turns earlier but with more false signals." |
| **Multi-RSI** | "RSI on the 1h chart AND the 4h chart both agree — higher confidence signal." |
| **Trend RSI** | "RSI signal only taken when the long-term trend (50-period average) agrees." |
| **Supertrend** | "A single indicator that flips between bullish and bearish based on volatility." |
| **VWAP** | "Is the price below the average price weighted by trading volume? Institutions watch this." |
| **MA Ribbon** | "A stack of moving averages — when they're all aligned and fanning out, trend is strong." |
| **DeMark** | "Counts 9 consecutive closes in one direction — exhaustion signal, often precedes reversal." |
| **Fibonacci Retracement** | "Price pulled back to a mathematically significant level and is bouncing." |
| **Combined** | "Requires two or more strategies to agree before taking a trade — fewer trades, higher quality." |
| **Grid** | "Divides a price range into levels and buys/sells at each one — works well in sideways markets." |

The bot can run any of these. The nightly evaluator picks which one is
working best for current conditions on each coin.

---

## Starting With Pretend Money

Out of the box the bot runs in **paper trading mode** — it trades with
fake money. Every buy and sell is recorded exactly as it would be in real
life (including fees and slippage), but nothing real happens.

This is how you find out whether a strategy would have actually worked
before putting real money behind it. Run it for a month or two, read the
weekly reports, and see if the numbers hold up.

---

## Going Live

When you're ready to use real money, you add your Kraken API key to the
config file and change one word from `"paper"` to `"live"`.

The bot then uses several additional safety features that only apply in
live mode:

- **Fill confirmation** — after every order is placed, it waits for the
  exchange to confirm the order actually went through before moving on.
  Most bots skip this step.

- **Position memory** — every trade is saved to a file so that if the
  bot restarts, it knows exactly what it was holding and at what price.
  On startup it compares that saved state against the exchange's actual
  records. If they don't match, it stops trading and sends you an alert
  rather than making assumptions.

- **Daily loss limit** — if the total loss on any single day exceeds 5%
  of the wallet, the bot stops opening new positions for that coin for
  the rest of the day.

- **Drawdown limit** — if the wallet falls more than 20% below its peak
  value at any point, the bot stops opening new positions until you
  manually review and reset it.

Both limits are adjustable in the config file.

---

## The Dashboard

Run `python run.py --ui` and open a browser to see everything in real
time: live price charts, which strategy is running, what the current
signal is, where the stop loss is set, what the market regime is
(trending or ranging), and the current profit/loss.

Everything on the dashboard is written in plain English — no trading
jargon, no unexplained acronyms.

---

## What to Realistically Expect

This bot is not magic. No bot is. Here's an honest picture:

**It will lose trades.** Any strategy that wins 50–60% of the time is
considered solid. The goal isn't to win every trade — it's to make sure
wins are larger than losses on average.

**Fees matter.** Kraken charges 0.26% per trade. A round-trip (buy +
sell) costs 0.52%. Every trade needs to move the price by more than that
just to break even. The bot accounts for this and avoids overtrading.

**It won't predict crashes.** A sudden market-wide drop will trigger the
trailing stop, which limits the damage — but it can't avoid the loss
entirely. The stop is protection, not insurance.

**Paper trading results won't perfectly match live results.** Live
markets have tiny differences (exact fill prices, split-second timing)
that simulations can't perfectly replicate. The bot does account for
slippage and fees in its simulations, which makes them more realistic
than most, but there will always be a small gap.

**With a $20 starting balance per coin**, expect:
- 2–6 completed trades per coin per month
- Each trade risks ~$0.20 (1% of wallet)
- The trailing stop keeps any single loss well under $1
- Realistic expectation: flat to slightly positive after fees in the
  first few months, with gradual improvement as the evaluator learns
  which strategies work

The bot is designed for patient, long-term operation — not get-rich-quick.
