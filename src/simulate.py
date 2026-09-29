"""
Runs a Monte Carlo simulation of future account balance, using:

- Recurring payments (fixed, scheduled outflows — rent, subscriptions)
- A fitted spending model (random daily spend, lognormal amounts)
- A fitted income model (random irregular income, gamma-ish gap
  between events, normal-ish amount per event)

The simulation runs forward day-by-day for a given horizon, repeated
many times with fresh random draws each time, to build up a picture
of the *range* of possible futures rather than a single point
estimate. This is the core of the "Future You" forecast: instead of
saying "you'll have R X on day 30", it says "here's the probability
you're in trouble by day 30".
"""

from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd

from detect_recurring import load_transactions, detect_recurring_payments
from split_transactions import split_recurring_vs_irregular
from fit_models import fit_spending_model, fit_income_model

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def recurring_payments_by_day_of_month(recurring_payments_df):
    """
    Converts the recurring payments table into a simple lookup:
    {day_of_month: total_amount_due}. Assumes each recurring payment
    lands on the same day-of-month each cycle (true for our detector,
    since we grouped by ~30-day intervals). This is a simplification —
    real payments can drift by a day or two — documented as a
    limitation rather than hidden.
    """
    # We don't have day-of-month directly in the table, so derive it
    # from last_seen_date as a stand-in for "which day it recurs on".
    schedule = {}
    for _, row in recurring_payments_df.iterrows():
        day_of_month = pd.Timestamp(row["last_seen_date"]).day
        schedule[day_of_month] = schedule.get(day_of_month, 0.0) + row["typical_amount"]
    return schedule


def simulate_one_path(
    starting_balance,
    horizon_days,
    recurring_schedule,      # {day_of_month: amount}
    spending_model,
    income_model,
    start_day_of_month,
    rng,
):
    balance = starting_balance
    balances = np.empty(horizon_days)

    days_to_next_income = max(1, round(rng.normal(income_model.mean_gap_days, income_model.std_gap_days)))

    current_day_of_month = start_day_of_month

    for day in range(horizon_days):
        current_day_of_month = (current_day_of_month % 28) + 1  # simple month-day cycling, avoids month-length edge cases

        # Recurring payments due today
        if current_day_of_month in recurring_schedule:
            balance -= recurring_schedule[current_day_of_month]

        # Everyday spending: random chance, random amount
        if rng.random() < spending_model.daily_spend_probability:
            spend = rng.lognormal(spending_model.lognorm_mean_log, spending_model.lognorm_std_log)
            balance -= spend

        # Irregular income
        days_to_next_income -= 1
        if days_to_next_income <= 0:
            income = max(0.0, rng.normal(income_model.mean_amount, income_model.std_amount))
            balance += income
            days_to_next_income = max(1, round(rng.normal(income_model.mean_gap_days, income_model.std_gap_days)))

        balances[day] = balance

    return balances


def run_monte_carlo(
    starting_balance,
    horizon_days,
    recurring_schedule,
    spending_model,
    income_model,
    start_day_of_month,
    num_simulations=5000,
    seed=7,
):
    rng = np.random.default_rng(seed)
    all_paths = np.empty((num_simulations, horizon_days))

    for i in range(num_simulations):
        all_paths[i] = simulate_one_path(
            starting_balance, horizon_days, recurring_schedule,
            spending_model, income_model, start_day_of_month, rng,
        )

    return all_paths


def summarize_paths(all_paths, shortfall_threshold=0.0):
    num_simulations, horizon_days = all_paths.shape

    # Day of first shortfall per simulation (None if it never happens)
    goes_negative = all_paths < shortfall_threshold
    first_shortfall_day = np.where(
        goes_negative.any(axis=1),
        goes_negative.argmax(axis=1),
        -1,  # -1 means "never went negative in the horizon"
    )

    never_negative = (first_shortfall_day == -1)
    pct_never_negative = never_negative.mean()

    def pct_negative_within(n_days):
        within = (first_shortfall_day != -1) & (first_shortfall_day < n_days)
        return within.mean()

    median_shortfall_day = (
        np.median(first_shortfall_day[first_shortfall_day != -1])
        if (~never_negative).any() else None
    )

    percentile_bands = {
        "p10": np.percentile(all_paths, 10, axis=0),
        "p50": np.percentile(all_paths, 50, axis=0),
        "p90": np.percentile(all_paths, 90, axis=0),
    }

    return {
        "pct_never_negative": pct_never_negative,
        "pct_negative_within_7": pct_negative_within(7),
        "pct_negative_within_14": pct_negative_within(14),
        "pct_negative_within_30": pct_negative_within(30),
        "median_shortfall_day": median_shortfall_day,
        "percentile_bands": percentile_bands,
    }


if __name__ == "__main__":
    df = load_transactions(DATA_DIR / "synthetic_transactions.csv")
    recurring_payments = detect_recurring_payments(df)
    recurring_df, irregular_df = split_recurring_vs_irregular(df, recurring_payments)

    history_num_days = (df["transactionDate"].max() - df["transactionDate"].min()).days + 1
    spending_model = fit_spending_model(irregular_df, history_num_days)
    income_model = fit_income_model(irregular_df)
    recurring_schedule = recurring_payments_by_day_of_month(recurring_payments)

    starting_balance = float(df.iloc[-1]["runningBalance"])
    last_date = df["transactionDate"].max()
    start_day_of_month = last_date.day

    print(f"Starting balance: R{starting_balance:.2f}")
    print(f"Recurring payments schedule (day of month -> amount): {recurring_schedule}")

    HORIZON_DAYS = 30
    all_paths = run_monte_carlo(
        starting_balance, HORIZON_DAYS, recurring_schedule,
        spending_model, income_model, start_day_of_month,
        num_simulations=5000,
    )

    summary = summarize_paths(all_paths)

    print(f"\n--- {HORIZON_DAYS}-day forecast ({5000} simulated futures) ---")
    print(f"Chance you STAY above R0 for the full {HORIZON_DAYS} days: {summary['pct_never_negative']:.1%}")
    print(f"Chance of going below R0 within 7 days:  {summary['pct_negative_within_7']:.1%}")
    print(f"Chance of going below R0 within 14 days: {summary['pct_negative_within_14']:.1%}")
    print(f"Chance of going below R0 within 30 days: {summary['pct_negative_within_30']:.1%}")
    if summary["median_shortfall_day"] is not None:
        print(f"Median day of first shortfall (among those who go negative): day {summary['median_shortfall_day']:.0f}")

    print("\nProjected balance percentile bands (selected days):")
    for day in [0, 6, 13, 20, 29]:
        p10 = summary["percentile_bands"]["p10"][day]
        p50 = summary["percentile_bands"]["p50"][day]
        p90 = summary["percentile_bands"]["p90"][day]
        print(f"  Day {day+1:2d}: 10th pct R{p10:8.2f}   median R{p50:8.2f}   90th pct R{p90:8.2f}")
