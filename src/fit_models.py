"""
Fits simple, explainable statistical distributions to the irregular
(non-recurring) parts of the transaction history:

- Everyday spending: modeled as a lognormal distribution (amounts
  can't be negative, and spending has a long right tail — most days
  are small purchases, occasionally a bigger one). We also track the
  probability that *any* spend happens on a given day, since students
  don't spend money every single day.

- Income events: modeled as two independent pieces —
    1. the gap in days between income events (how often money arrives)
    2. the amount of each income event
  This captures irregular freelance/side-hustle income rather than
  assuming a fixed monthly payday.

Everything here is deliberately simple (means, standard deviations,
lognormal fits) rather than more sophisticated time-series modeling.
That's a conscious choice: with ~9 months of data and only 10 income
events, a complex model would be overfitting noise. The assumptions
are documented explicitly so they can be judged on their own terms.
"""

from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd

from detect_recurring import load_transactions, detect_recurring_payments
from split_transactions import split_recurring_vs_irregular

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class SpendingModel:
    daily_spend_probability: float   # chance any spend happens on a given day
    lognorm_mean_log: float          # mean of ln(amount), for days a spend occurs
    lognorm_std_log: float           # std of ln(amount)


@dataclass
class IncomeModel:
    mean_gap_days: float
    std_gap_days: float
    mean_amount: float
    std_amount: float


def fit_spending_model(irregular_df, history_num_days):
    """
    irregular_df: the non-recurring transactions (output of split_transactions)
    history_num_days: total number of days the history spans, used to
                       compute how often a spend day occurs at all.
    """
    spend_txns = irregular_df[irregular_df["type"] == "DEBIT"]
    amounts = spend_txns["amount"].values

    if len(amounts) == 0:
        # No irregular spending in the history at all - model as
        # "no everyday spending happens" rather than crashing on an
        # empty-array mean/std (which would produce NaN).
        return SpendingModel(
            daily_spend_probability=0.0,
            lognorm_mean_log=0.0,
            lognorm_std_log=0.0,
        )

    num_spend_days = spend_txns["transactionDate"].dt.date.nunique()
    daily_spend_probability = num_spend_days / history_num_days

    # Guard against zero/negative amounts, which would make log() undefined
    amounts = amounts[amounts > 0]
    if len(amounts) == 0:
        return SpendingModel(daily_spend_probability=0.0, lognorm_mean_log=0.0, lognorm_std_log=0.0)

    log_amounts = np.log(amounts)
    lognorm_mean_log = log_amounts.mean()
    # std of a single value is 0, which is valid (no spread) - only
    # a genuinely empty array would produce NaN, already handled above.
    lognorm_std_log = log_amounts.std() if len(log_amounts) > 1 else 0.0

    return SpendingModel(
        daily_spend_probability=daily_spend_probability,
        lognorm_mean_log=lognorm_mean_log,
        lognorm_std_log=lognorm_std_log,
    )


def fit_income_model(irregular_df):
    """
    Fits a simple model to genuine irregular income events.

    We exclude obvious non-income credits such as refunds and bank
    interest because they should not be treated as money the user
    can reliably expect to receive again.

    Remaining credits are modeled using:
      1. average gap between income events
      2. standard deviation of those gaps
      3. average income amount
      4. standard deviation of income amounts

    This remains deliberately simple because the available transaction
    history contains relatively few income observations.
    """
    income_txns = irregular_df[
        irregular_df["type"] == "CREDIT"
    ].copy()

    # Remove credits that are clearly not ordinary income.
    description = income_txns["description"].fillna("").str.upper()

    non_income_patterns = (
        description.str.contains("REFUND", na=False)
        | description.str.contains("INTEREST", na=False)
    )

    income_txns = (
        income_txns[~non_income_patterns]
        .sort_values("transactionDate")
        .copy()
    )

    amounts = income_txns["amount"].values

    if len(income_txns) == 0:
        # No usable income observed.
        return IncomeModel(
            mean_gap_days=10_000,
            std_gap_days=0.0,
            mean_amount=0.0,
            std_amount=0.0,
        )

    if len(income_txns) == 1:
        # Only one income event: there is not enough information
        # to estimate a realistic arrival pattern.
        return IncomeModel(
            mean_gap_days=30.0,
            std_gap_days=10.0,
            mean_amount=float(amounts[0]),
            std_amount=float(amounts[0]) * 0.2,
        )

    dates = income_txns["transactionDate"].values

    gaps_days = (
        np.diff(dates)
        .astype("timedelta64[D]")
        .astype(float)
    )

    mean_gap_days = float(gaps_days.mean())

    std_gap_days = (
        float(gaps_days.std())
        if len(gaps_days) > 1
        else max(mean_gap_days * 0.15, 1.0)
    )

    mean_amount = float(amounts.mean())

    std_amount = (
        float(amounts.std())
        if len(amounts) > 1
        else mean_amount * 0.15
    )

    return IncomeModel(
        mean_gap_days=mean_gap_days,
        std_gap_days=std_gap_days,
        mean_amount=mean_amount,
        std_amount=std_amount,
    )