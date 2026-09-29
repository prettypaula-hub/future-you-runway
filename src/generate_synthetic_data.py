"""
Generates synthetic transaction data shaped like what the Investec
sandbox API returns, so we can build and test locally before wiring
up real API calls.

Investec's transaction objects generally look like (simplified):
{
    "accountId": "...",
    "type": "DEBIT" | "CREDIT",
    "transactionType": "...",
    "status": "POSTED",
    "description": "...",
    "cardNumber": "...",
    "postingDate": "YYYY-MM-DD",
    "valueDate": "YYYY-MM-DD",
    "actionDate": "YYYY-MM-DD",
    "transactionDate": "YYYY-MM-DD",
    "amount": 123.45,
    "runningBalance": 4567.89
}

We reproduce the fields that matter for forecasting: date, amount,
type (DEBIT/CREDIT) and description.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

# Resolves to <project_root>/data regardless of where this script is run from
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

random.seed(42)  # reproducible synthetic data

START_DATE = date(2026, 1, 1)
NUM_DAYS = 270  # ~9 months of history

# Recurring outflows: (description, amount, day-of-month it lands on)
RECURRING_PAYMENTS = [
    ("Res Rent", 3200.00, 1),
    ("Netflix Subscription", 199.00, 5),
    ("Spotify Premium", 79.99, 8),
    ("Gym Membership", 350.00, 25),
    ("Cellphone Contract", 499.00, 20),
]

# Irregular income: student side-hustle / freelance style, not fixed payday
# Modeled as: roughly every 18-35 days, amount varies
INCOME_MIN_GAP_DAYS = 18
INCOME_MAX_GAP_DAYS = 35
INCOME_AMOUNT_MEAN = 4300.00
INCOME_AMOUNT_STD = 750.00

# Everyday spend: lognormal-ish daily spend, not every day
DAILY_SPEND_PROB = 0.55  # chance of any spend happening on a given day
DAILY_SPEND_MEAN_LOG = 3.35   # ln(~R28)
DAILY_SPEND_STD_LOG = 0.65

STARTING_BALANCE = 3800.00


def generate_transactions():
    transactions = []
    balance = STARTING_BALANCE
    current_date = START_DATE

    next_income_date = current_date + timedelta(
        days=random.randint(INCOME_MIN_GAP_DAYS, INCOME_MAX_GAP_DAYS)
    )

    for _ in range(NUM_DAYS):
        day_of_month = current_date.day

        # Recurring payments
        for desc, amount, dom in RECURRING_PAYMENTS:
            if day_of_month == dom:
                balance -= amount
                transactions.append({
                    "transactionDate": current_date.isoformat(),
                    "description": desc,
                    "type": "DEBIT",
                    "amount": round(amount, 2),
                    "runningBalance": round(balance, 2),
                })

        # Irregular income
        if current_date == next_income_date:
            amount = max(300.0, random.gauss(INCOME_AMOUNT_MEAN, INCOME_AMOUNT_STD))
            balance += amount
            transactions.append({
                "transactionDate": current_date.isoformat(),
                "description": "Client Payment / Side Hustle",
                "type": "CREDIT",
                "amount": round(amount, 2),
                "runningBalance": round(balance, 2),
            })
            next_income_date = current_date + timedelta(
                days=random.randint(INCOME_MIN_GAP_DAYS, INCOME_MAX_GAP_DAYS)
            )

        # Everyday spending (lognormal, irregular)
        if random.random() < DAILY_SPEND_PROB:
            amount = random.lognormvariate(DAILY_SPEND_MEAN_LOG, DAILY_SPEND_STD_LOG)
            amount = min(amount, 900.0)  # cap extreme outliers
            balance -= amount
            transactions.append({
                "transactionDate": current_date.isoformat(),
                "description": random.choice([
                    "Card Purchase - Checkers", "Card Purchase - Uber Eats",
                    "Card Purchase - Campus Cafe", "Card Purchase - Clicks",
                    "Card Purchase - Woolworths", "ATM Withdrawal",
                ]),
                "type": "DEBIT",
                "amount": round(amount, 2),
                "runningBalance": round(balance, 2),
            })

        current_date += timedelta(days=1)

    return transactions


def save_to_csv(transactions, path):
    fieldnames = ["transactionDate", "description", "type", "amount", "runningBalance"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(transactions)


if __name__ == "__main__":
    txns = generate_transactions()
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / "synthetic_transactions.csv"
    save_to_csv(txns, out_path)
    print(f"Generated {len(txns)} transactions -> {out_path}")
    print(f"Final balance: R{txns[-1]['runningBalance']:.2f}")
