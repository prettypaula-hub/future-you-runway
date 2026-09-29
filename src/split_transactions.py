"""
Splits a transaction history into two buckets, using the recurring
payments already identified by detect_recurring.py:

- recurring_df:  transactions that belong to a detected recurring
                  payment (rent, subscriptions, etc). These get
                  treated as fixed, scheduled outflows in the
                  simulation, not random draws.
- irregular_df:  everything else (day-to-day spending, and irregular
                  income like freelance/side-hustle payments). These
                  get modeled as random distributions in the
                  simulation.

Keeping this as its own step (rather than burying it inside the
simulation) makes it easy to sanity-check: you can print either
bucket and confirm nothing recurring leaked into "irregular" and
vice versa.
"""

from pathlib import Path

import pandas as pd
from detect_recurring import load_transactions, detect_recurring_payments

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def split_recurring_vs_irregular(df, recurring_payments_df):
    """
    df: full transaction history (from load_transactions)
    recurring_payments_df: output of detect_recurring_payments(df)

    Returns (recurring_df, irregular_df) - both subsets of df's rows.
    """
    recurring_descriptions = set(recurring_payments_df["description"])

    is_recurring = df["description"].isin(recurring_descriptions)

    recurring_df = df[is_recurring].copy()
    irregular_df = df[~is_recurring].copy()

    return recurring_df, irregular_df


def summarize_split(df, recurring_df, irregular_df):
    irregular_debits = irregular_df[irregular_df["type"] == "DEBIT"]
    irregular_credits = irregular_df[irregular_df["type"] == "CREDIT"]

    print(f"Total transactions:        {len(df)}")
    print(f"Recurring (fixed):         {len(recurring_df)}")
    print(f"Irregular spending (DEBIT): {len(irregular_debits)}  "
          f"(total R{irregular_debits['amount'].sum():.2f})")
    print(f"Irregular income (CREDIT): {len(irregular_credits)}  "
          f"(total R{irregular_credits['amount'].sum():.2f})")


if __name__ == "__main__":
    df = load_transactions(DATA_DIR / "synthetic_transactions.csv")
    recurring_payments = detect_recurring_payments(df)

    recurring_df, irregular_df = split_recurring_vs_irregular(df, recurring_payments)

    summarize_split(df, recurring_df, irregular_df)

    print("\nSample of irregular (non-recurring) transactions:")
    print(irregular_df.head(8).to_string(index=False))
