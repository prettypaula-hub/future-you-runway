# Forecast Explanation

This document explains exactly how the forecast is generated: the signals
used, the method, and — most importantly — the assumptions and their
limitations. Nothing here is a black box.

## 1. Signals used

The only input is transaction history pulled from the Investec API:
`transactionDate`, `description`, `type` (DEBIT/CREDIT), `amount`, and
`runningBalance`. No external data sources are used.

## 2. Step 1 — Recurring payment detection

Transactions are grouped by their `description` field (Investec's
descriptions are fairly stable per merchant/payee). A group is flagged as
**recurring** if it meets two criteria:

- **Amount consistency**: the coefficient of variation (std / mean) of the
  amounts is below a threshold (default 0.15) — i.e. the amount barely
  changes between occurrences.
- **Interval consistency**: the standard deviation of the gaps between
  occurrences is below a threshold (default 4 days) — i.e. it happens on a
  roughly fixed schedule.
- At least 3 occurrences are required before something is considered a
  pattern rather than a coincidence.

**Why this approach**: it's simple, transparent, and every flagged payment
can be explained in one sentence to a user ("this repeats every ~30 days at
a consistent amount"). It deliberately avoids more opaque approaches (e.g.
clustering on description embeddings) because explainability matters more
here than marginal recall improvements.

**Known limitation**: a payment whose amount varies more than ~15% (e.g. a
usage-based bill) or whose timing drifts by more than a few days won't be
detected as recurring, and will instead be absorbed into the "everyday
spending" model — which makes it a random variable instead of a known
scheduled cost. This understates its predictability but doesn't cause it to
be missed from the balance projection entirely.

## 3. Step 2 — Splitting recurring vs. irregular

Every transaction not flagged as recurring is treated as "irregular" and
split further by direction: irregular DEBITs (day-to-day spending) and
irregular CREDITs (income).

## 4. Step 3 — Fitting statistical models

**Everyday spending** is modeled with two components:
- The *probability* that any spending happens on a given day (observed
  fraction of days with at least one irregular debit)
- A **lognormal distribution** fit to the amounts, when a spend does happen

Lognormal was chosen because spending amounts can't be negative and tend to
have a long right tail (most purchases are small, occasionally a larger
one) — a normal distribution would allow (incorrectly) negative spend
amounts and wouldn't capture that skew.

**Irregular income** is modeled with two independent pieces:
- The gap (in days) between income events, using the mean and standard
  deviation of historical gaps
- The amount per income event, using the mean and standard deviation of
  historical amounts

**Known limitation — small samples**: with only a few months of sandbox
history, income events in particular can number in the single digits. A
distribution fit to 3–10 data points has real uncertainty that a point
estimate doesn't convey. The simulation still runs, but the confidence in
the income-timing forecast should be read as lower than the confidence in
the (much more data-rich) spending forecast. If fewer than 2 income events
are observed, the model falls back to a wide, explicitly-flagged assumption
rather than silently producing an unreliable fit.

## 5. Step 4 — Monte Carlo simulation

Starting from today's actual balance, the simulation steps forward
day-by-day for a chosen horizon (default 30 days). On each simulated day:

1. Any recurring payment scheduled for that day-of-month is subtracted
2. With the fitted probability, a random spend amount (drawn from the
   lognormal spending distribution) is subtracted
3. If the running countdown to the next income event reaches zero, a random
   income amount (drawn from the income distribution) is added, and the
   countdown resets using a fresh random gap

This entire process is repeated **5,000 times independently**, each with
fresh random draws, producing 5,000 different possible balance trajectories
over the horizon.

**Why Monte Carlo rather than a single projection**: a single "average
income minus average expenses" projection hides the fact that timing
matters enormously — two people with identical average income and spending
can have very different risk profiles depending on when the recurring rent
payment lands relative to when income arrives. Simulating many random
trajectories captures that timing risk directly, rather than assuming
everything lands smoothly.

## 6. Step 5 — Turning simulations into a forecast

Across the 5,000 simulated trajectories, we compute:
- The 10th, 50th (median), and 90th percentile balance on each day — shown
  as a shaded band in the chart
- The percentage of simulations that go below R0 within 7 / 14 / 30 days
- The median day of first shortfall, among simulations that do go negative

This is reported as a probability, not a certainty — e.g. "62% chance of
going below R0 within 14 days" — because that's what the model actually
produces and what's honest to show a user.

## 7. Assumptions, stated explicitly

- Recurring payments are assumed to always fall on the same day-of-month
  going forward (a payment seen on the 25th is assumed to recur on the 25th
  indefinitely). Real payments can drift by a day or two around
  weekends/holidays.
- Everyday spending and income events are simulated independently of each
  other and of the day of the month (no seasonality, e.g. no modeling of
  "people spend more in December").
- The starting point for the simulation is the most recent `runningBalance`
  in the pulled transaction history, which may lag slightly behind the
  true current balance if very recent transactions haven't posted yet.
- If no irregular income is observed in the pulled history at all, the
  model assumes no further income in the forecast horizon — this is a
  deliberately conservative fallback (better to warn about a risk that
  doesn't materialize than to miss one), but it does mean the forecast will
  look worse than reality for an account whose income simply falls outside
  the pulled date range.

## 8. What would make this more robust (not implemented here)

- Modeling recurring payments with a small amount of day-of-month jitter
  instead of a fixed day
- Detecting seasonality (day-of-week or month-of-year spending patterns)
- Weighting more recent transactions more heavily than older ones when
  fitting distributions
- A larger pulled history window to reduce small-sample uncertainty on the
  income side
