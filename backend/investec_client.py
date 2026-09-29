"""
Minimal client for the Investec Open API (Sandbox or live).

Authentication flow (client_credentials grant):
1. POST to the identity token endpoint with client_id/client_secret as
   HTTP Basic Auth, and your API key in an x-api-key header.
2. Receive a bearer access token, valid for a limited time.
3. Use that token as a Bearer token on all subsequent requests.

Docs reference: Investec Developer Community quick-start guide
(github.com/Investec-Developer-Community/community-wiki).

Credentials are read from environment variables - never hardcode
them in source. See .env.example for what's required.
"""
from dotenv import load_dotenv

load_dotenv()
import os
import base64
from datetime import datetime, timedelta

import requests
import pandas as pd

# Sandbox and live use different base URLs. Configurable via env var
# so switching between them (or if Investec changes the URL) doesn't
# require a code change.
API_BASE_URL = os.environ.get("INVESTEC_API_BASE_URL", "https://openapisandbox.investec.com")
TOKEN_URL = f"{API_BASE_URL}/identity/v2/oauth2/token"


class InvestecClient:
    def __init__(self, client_id=None, client_secret=None, api_key=None):
        self.client_id = client_id or os.environ.get("INVESTEC_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("INVESTEC_CLIENT_SECRET")
        self.api_key = api_key or os.environ.get("INVESTEC_API_KEY")

        if not all([self.client_id, self.client_secret, self.api_key]):
            raise ValueError(
                "Missing Investec API credentials. Set INVESTEC_CLIENT_ID, "
                "INVESTEC_CLIENT_SECRET and INVESTEC_API_KEY (e.g. in a .env file)."
            )

        self._access_token = None
        self._token_expires_at = None

    def _get_access_token(self):
        """Returns a valid bearer token, fetching a new one if needed."""
        if self._access_token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._access_token

        basic_auth = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        response = requests.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic_auth}",
                "x-api-key": self.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        # Refresh a little early to avoid edge-of-expiry failures
        expires_in = token_data.get("expires_in", 1800)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

        return self._access_token

    def _authed_get(self, path):
        token = self._get_access_token()
        response = requests.get(
            f"{API_BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_accounts(self):
        """Returns the list of accounts available to these credentials."""
        data = self._authed_get("/za/pb/v1/accounts")
        return data["data"]["accounts"]

    def get_transactions(self, account_id, from_date=None, to_date=None):
        """
        Returns raw transaction records for one account.
        from_date / to_date: "YYYY-MM-DD" strings, optional.
        """
        path = f"/za/pb/v1/accounts/{account_id}/transactions"
        params = []
        if from_date:
            params.append(f"fromDate={from_date}")
        if to_date:
            params.append(f"toDate={to_date}")
        if params:
            path += "?" + "&".join(params)

        data = self._authed_get(path)

        #print("\n========== INVESTEC RAW RESPONSE ==========")
        print("Response keys:", data.keys())
        print("Data keys:", data.get("data", {}).keys())
        print("Number of transactions:",
            len(data.get("data", {}).get("transactions", [])))
        print("Full data response:")
        print(data.get("data"))
        #print("===========================================\n")

        return data["data"]["transactions"]


def transactions_to_dataframe(raw_transactions):
    """
    Converts Investec's raw transaction JSON into the same schema our
    pipeline already uses: transactionDate, description, type, amount,
    runningBalance. This is the one place that would need updating if
    Investec's field names ever change.
    """
    rows = []
    for txn in raw_transactions:
        rows.append({
            "transactionDate": txn.get("transactionDate") or txn.get("postingDate"),
            "description": txn.get("description", ""),
            "type": txn.get("type", "").upper(),  # DEBIT / CREDIT
            "amount": float(txn.get("amount", 0.0)),
            "runningBalance": float(txn.get("runningBalance", 0.0)),
        })

    df = pd.DataFrame(rows)
    df["transactionDate"] = pd.to_datetime(df["transactionDate"])
    return df.sort_values("transactionDate").reset_index(drop=True)


def fetch_live_transaction_history(account_id, from_date=None, to_date=None):
    """
    Fetches transaction history for one account.

    If no date range is supplied, fetch the previous 12 months so that
    recurring-payment detection has enough historical data.
    """
    client = InvestecClient()

    today = datetime.now().date()

    if to_date is None:
        to_date = today.isoformat()

    if from_date is None:
        from_date = (today - timedelta(days=365)).isoformat()

    raw_transactions = client.get_transactions(
        account_id,
        from_date,
        to_date,
    )

    print(
        f"Investec transaction request: "
        f"{from_date} -> {to_date}; "
        f"received {len(raw_transactions)} transactions"
    )

    return transactions_to_dataframe(raw_transactions)

def fetch_accounts():
    """Returns the raw list of accounts (clients) available to these credentials."""
    client = InvestecClient()
    return client.get_accounts()


if __name__ == "__main__":
    # Quick manual test - requires real credentials in your environment.
    accounts = fetch_accounts()
    print(f"Found {len(accounts)} account(s).")
    if accounts:
        df = fetch_live_transaction_history(accounts[0]["accountId"])
        print(f"Fetched {len(df)} live transactions for the first account.")
        print(df.head())
