"""
Flask backend for the Future You runway forecaster.

Exposes:
  GET /api/health
  GET /api/accounts
  GET /api/forecast
  POST /api/whatif

Data source:
  Uses Investec sandbox/live transaction data when valid credentials
  are available. Otherwise falls back to the bundled synthetic dataset.
"""

import sys
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request
from flask_cors import CORS

# Make the analysis pipeline importable
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from detect_recurring import load_transactions, detect_recurring_payments
from split_transactions import split_recurring_vs_irregular
from fit_models import fit_spending_model, fit_income_model
from simulate import (
    recurring_payments_by_day_of_month,
    run_monte_carlo,
    summarize_paths,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = Flask(__name__)
CORS(app)

SYNTHETIC_ACCOUNT_ID = "synthetic-demo-account"


def has_live_credentials():
    """Check whether all required Investec credentials are available."""
    return all([
        os.environ.get("INVESTEC_CLIENT_ID"),
        os.environ.get("INVESTEC_CLIENT_SECRET"),
        os.environ.get("INVESTEC_API_KEY"),
    ])


def get_available_accounts():
    """
    Returns:
        (accounts_list, data_source)

    Uses live Investec accounts when available.
    Falls back to one synthetic account if necessary.
    """
    if has_live_credentials():
        try:
            from investec_client import fetch_accounts

            raw_accounts = fetch_accounts()

            accounts = [
                {
                    "accountId": a["accountId"],
                    "accountName": (
                        a.get("accountName")
                        or a.get("referenceName")
                        or a["accountId"]
                    ),
                    "productName": a.get("productName", ""),
                }
                for a in raw_accounts
            ]

            if accounts:
                return accounts, "investec_live"

        except Exception as e:
            app.logger.warning(
                f"Investec accounts call failed, "
                f"falling back to synthetic: {e}"
            )

    return [
        {
            "accountId": SYNTHETIC_ACCOUNT_ID,
            "accountName": "Demo Student Account (synthetic)",
            "productName": "Synthetic",
        }
    ], "synthetic_fallback"


def get_transaction_data(account_id):
    """
    Returns:
        (dataframe, data_source_label)
    """

    if account_id == SYNTHETIC_ACCOUNT_ID or not has_live_credentials():
        df = load_transactions(
            DATA_DIR / "synthetic_transactions.csv"
        )
        return df, "synthetic_fallback"

    try:
        from investec_client import fetch_live_transaction_history

        df = fetch_live_transaction_history(account_id)

        return df, "investec_live"

    except Exception as e:
        app.logger.warning(
            f"Investec transactions call failed for {account_id}, "
            f"falling back: {e}"
        )

        df = load_transactions(
            DATA_DIR / "synthetic_transactions.csv"
        )

        return df, "synthetic_fallback"


def run_forecast_pipeline(
    df,
    horizon_days,
    num_simulations,
    extra_expense=None,
):
    """
    Runs:

        detect recurring
        -> split recurring/irregular
        -> fit spending model
        -> fit income model
        -> Monte Carlo simulation
        -> risk summary

    extra_expense:
        Optional dictionary:
        {
            "amount": float,
            "day": int
        }

        Used by the What-If endpoint.
    """

    # ---------------------------------------------------------
    # 1. Detect recurring payments
    # ---------------------------------------------------------

    recurring_payments = detect_recurring_payments(df)

    # ---------------------------------------------------------
    # 2. Split recurring vs irregular transactions
    # ---------------------------------------------------------

    recurring_df, irregular_df = split_recurring_vs_irregular(
        df,
        recurring_payments,
    )

    # ---------------------------------------------------------
    # 3. Determine available transaction history
    # ---------------------------------------------------------

    history_num_days = (
        df["transactionDate"].max()
        - df["transactionDate"].min()
    ).days + 1

    # ---------------------------------------------------------
    # 4. Fit spending and income models
    # ---------------------------------------------------------

    spending_model = fit_spending_model(
        irregular_df,
        history_num_days,
    )

    income_model = fit_income_model(
        irregular_df,
    )

    # ---------------------------------------------------------
    # 5. Build recurring payment schedule
    # ---------------------------------------------------------

    recurring_schedule = recurring_payments_by_day_of_month(
        recurring_payments
    )

    # ---------------------------------------------------------
    # 6. Starting balance and forecast start date
    # ---------------------------------------------------------

    starting_balance = float(
        df.iloc[-1]["runningBalance"]
    )

    last_date = df["transactionDate"].max()

    start_day_of_month = last_date.day

    # ---------------------------------------------------------
    # 7. Run Monte Carlo simulation
    # ---------------------------------------------------------

    all_paths = run_monte_carlo(
        starting_balance,
        horizon_days,
        recurring_schedule,
        spending_model,
        income_model,
        start_day_of_month,
        num_simulations=num_simulations,
    )

    # ---------------------------------------------------------
    # 8. Apply What-If expense if provided
    # ---------------------------------------------------------

    if (
        extra_expense is not None
        and extra_expense.get("amount", 0) > 0
    ):
        day_index = max(
            0,
            min(
                horizon_days - 1,
                extra_expense["day"] - 1,
            ),
        )

        all_paths = all_paths.copy()

        # Money spent on the selected day reduces all
        # subsequent balances.
        all_paths[:, day_index:] -= extra_expense["amount"]

    # ---------------------------------------------------------
    # 9. Summarise simulation paths
    # ---------------------------------------------------------

    summary = summarize_paths(all_paths)

    # ---------------------------------------------------------
    # 10. Return complete forecast result
    # ---------------------------------------------------------

    return {
        "starting_balance": round(
            starting_balance,
            2,
        ),

        "history": {
            "start_date": df[
                "transactionDate"
            ].min().strftime("%Y-%m-%d"),

            "end_date": df[
                "transactionDate"
            ].max().strftime("%Y-%m-%d"),

            "days": history_num_days,

            "transaction_count": len(df),
        },

        "recurring_payments": (
            recurring_payments.to_dict(
                orient="records"
            )
        ),

        "forecast": {
            "days": list(
                range(
                    1,
                    horizon_days + 1,
                )
            ),

            "p10": [
                round(x, 2)
                for x in summary[
                    "percentile_bands"
                ]["p10"].tolist()
            ],

            "p50": [
                round(x, 2)
                for x in summary[
                    "percentile_bands"
                ]["p50"].tolist()
            ],

            "p90": [
                round(x, 2)
                for x in summary[
                    "percentile_bands"
                ]["p90"].tolist()
            ],
        },

        "risk_summary": {
            "pct_never_negative": round(
                summary["pct_never_negative"],
                4,
            ),

            "pct_negative_within_7": round(
                summary["pct_negative_within_7"],
                4,
            ),

            "pct_negative_within_14": round(
                summary["pct_negative_within_14"],
                4,
            ),

            "pct_negative_within_30": round(
                summary["pct_negative_within_30"],
                4,
            ),

            "median_shortfall_day": (
                None
                if summary["median_shortfall_day"] is None
                else int(
                    summary["median_shortfall_day"]
                )
            ),
        },
    }


# =============================================================
# HEALTH
# =============================================================

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok"
    })


# =============================================================
# ACCOUNTS
# =============================================================

@app.route("/api/accounts")
def accounts():

    accounts_list, data_source = get_available_accounts()

    return jsonify({
        "accounts": accounts_list,
        "data_source": data_source,
    })


# =============================================================
# FORECAST
# =============================================================

@app.route("/api/forecast")
def forecast():

    account_id = request.args.get(
        "account_id",
        SYNTHETIC_ACCOUNT_ID,
    )

    horizon_days = int(
        request.args.get(
            "horizon_days",
            30,
        )
    )

    num_simulations = int(
        request.args.get(
            "num_simulations",
            5000,
        )
    )

    df, data_source = get_transaction_data(
        account_id
    )

    result = run_forecast_pipeline(
        df,
        horizon_days,
        num_simulations,
    )

    result["data_source"] = data_source

    result["account_id"] = account_id

    result["horizon_days"] = horizon_days

    result["num_simulations"] = num_simulations

    result["assumptions"] = [
        (
            "Recurring payments are assumed to fall "
            "on a fixed day-of-month."
        ),

        (
            "Everyday spending is modeled as a lognormal "
            "distribution fit to historical non-recurring debits."
        ),

        (
            "Income timing and amount are modeled from "
            "historical non-recurring credits; a small sample "
            "size widens uncertainty here."
        ),

        (
            "Spending and income are simulated independently "
            "day-to-day (a simplification)."
        ),
    ]

    return jsonify(result)


# =============================================================
# WHAT IF
# =============================================================

@app.route("/api/whatif", methods=["POST"])
def whatif():

    body = request.get_json(force=True)

    account_id = body.get(
        "account_id",
        SYNTHETIC_ACCOUNT_ID,
    )

    amount = float(
        body.get(
            "amount",
            0,
        )
    )

    day = int(
        body.get(
            "day",
            1,
        )
    )

    horizon_days = int(
        body.get(
            "horizon_days",
            30,
        )
    )

    num_simulations = int(
        body.get(
            "num_simulations",
            3000,
        )
    )

    df, data_source = get_transaction_data(
        account_id
    )

    # Baseline forecast
    baseline = run_forecast_pipeline(
        df,
        horizon_days,
        num_simulations,
    )

    # Forecast with hypothetical expense
    with_expense = run_forecast_pipeline(
        df,
        horizon_days,
        num_simulations,
        extra_expense={
            "amount": amount,
            "day": day,
        },
    )

    return jsonify({
        "data_source": data_source,

        "account_id": account_id,

        "hypothetical_expense": {
            "amount": amount,
            "day": day,
        },

        "baseline": baseline,

        "with_expense": with_expense,
    })


# =============================================================
# START SERVER
# =============================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5000,
    )