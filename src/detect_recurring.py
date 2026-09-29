"""
Detect recurring payments (subscriptions, rent, debit orders) from a
transaction history.

Approach:
1. Group DEBIT transactions by description.
2. Require a minimum number of occurrences.
3. Check that payment amounts are reasonably consistent.
4. Check that transaction gaps match a common recurring frequency:
   - weekly
   - biweekly
   - monthly
   - quarterly
5. Return the recurring payment with its typical amount and frequency.

The method is deliberately transparent and rule-based so that every
detection can be explained.
"""

from pathlib import Path

import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_transactions(path):
    df = pd.read_csv(path, parse_dates=["transactionDate"])
    return df.sort_values("transactionDate").reset_index(drop=True)


def classify_interval(mean_gap):
    """
    Classify a recurring payment based on its average gap.

    Returns:
        frequency name, expected interval in days
    """

    if 5 <= mean_gap <= 9:
        return "weekly", 7

    if 12 <= mean_gap <= 17:
        return "biweekly", 14

    if 25 <= mean_gap <= 35:
        return "monthly", 30

    if 80 <= mean_gap <= 100:
        return "quarterly", 90

    return None, None


def detect_recurring_payments(
    df,
    min_occurrences=3,
    amount_cv_threshold=0.15,
    interval_tolerance_days=5.0,
):
    """
    Returns a DataFrame with one row per detected recurring payment.

    Columns:
        description
        typical_amount
        typical_interval_days
        frequency
        occurrences
        amount_cv
        interval_std_days
        last_seen_date
    """

    debits = df[df["type"] == "DEBIT"].copy()

    results = []

    for description, group in debits.groupby("description"):

        group = group.sort_values("transactionDate")

        # Need at least 3 occurrences to establish a pattern.
        if len(group) < min_occurrences:
            continue

        # ---------------------------------------------------------
        # Amount consistency
        # ---------------------------------------------------------

        amounts = group["amount"].astype(float).to_numpy()

        amount_mean = amounts.mean()
        amount_std = amounts.std()

        amount_cv = (
            amount_std / amount_mean
            if amount_mean != 0
            else np.inf
        )

        # ---------------------------------------------------------
        # Date gaps
        # ---------------------------------------------------------

        dates = pd.to_datetime(group["transactionDate"])

        gaps_days = dates.diff().dt.days.dropna().to_numpy()

        if len(gaps_days) == 0:
            continue

        gap_mean = gaps_days.mean()
        gap_std = gaps_days.std()

        # ---------------------------------------------------------
        # Determine frequency
        # ---------------------------------------------------------

        frequency, expected_interval = classify_interval(gap_mean)

        if frequency is None:
            continue

        # ---------------------------------------------------------
        # Check interval consistency
        #
        # We compare each observed gap with the expected frequency.
        # This handles calendar months better than requiring every
        # monthly gap to be exactly 30 days.
        # ---------------------------------------------------------

        interval_deviation = np.abs(
            gaps_days - expected_interval
        )

        interval_consistent = (
            interval_deviation <= interval_tolerance_days
        ).mean() >= 0.75

        # ---------------------------------------------------------
        # Final recurring decision
        # ---------------------------------------------------------

        is_recurring = (
            amount_cv <= amount_cv_threshold
            and interval_consistent
        )

        if not is_recurring:
            continue

        results.append({
            "description": description,
            "typical_amount": round(amount_mean, 2),
            "typical_interval_days": round(gap_mean, 1),
            "frequency": frequency,
            "occurrences": len(group),
            "amount_cv": round(amount_cv, 3),
            "interval_std_days": round(gap_std, 2),
            "last_seen_date": (
                dates.max().date().isoformat()
            ),
        })

    # -------------------------------------------------------------
    # Handle no detections safely
    # -------------------------------------------------------------

    columns = [
        "description",
        "typical_amount",
        "typical_interval_days",
        "frequency",
        "occurrences",
        "amount_cv",
        "interval_std_days",
        "last_seen_date",
    ]

    result = pd.DataFrame(results, columns=columns)

    if result.empty:
        return result

    return (
        result
        .sort_values("typical_amount", ascending=False)
        .reset_index(drop=True)
    )


if __name__ == "__main__":

    df = load_transactions(
        DATA_DIR / "synthetic_transactions.csv"
    )

    recurring = detect_recurring_payments(df)

    print(f"Loaded {len(df)} transactions.")
    print(f"Detected {len(recurring)} recurring payments:\n")

    if recurring.empty:
        print("No recurring payments detected.")
    else:
        print(recurring.to_string(index=False))

    # -------------------------------------------------------------
    # Calculate estimated monthly recurring spend
    # -------------------------------------------------------------

    if recurring.empty:
        total_monthly_recurring = 0.0
    else:
        total_monthly_recurring = (
            recurring["typical_amount"]
            / (recurring["typical_interval_days"] / 30.0)
        ).sum()

    print(
        f"\nEstimated total recurring spend: "
        f"~R{total_monthly_recurring:.2f}/month"
    )