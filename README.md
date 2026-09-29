# Future You — Cashflow Runway Forecaster

A tool that answers one question: **"What's likely to happen to my money next?"**

Built for the Investec Developer Community "Future You" bounty.

## The problem

Most banking apps are excellent at showing you the past — a list of transactions,
a current balance. They're much less good at telling you what's coming. A
balance that looks healthy today can be wiped out in days by a rent payment,
loan instalment, or subscription you'd forgotten about — especially for anyone
whose income doesn't arrive on a predictable monthly payday (students,
freelancers, side-hustlers).

## Who it's for

Primarily aimed at **students and anyone with irregular income** — people for
whom "when does money arrive" is at least as uncertain as "how much do I
spend." The example scenario throughout this build is a student juggling rent,
subscriptions, and irregular side-hustle income.

## What it does

1. **Pulls transaction history** from the Investec API (Sandbox or live,
   depending on configured credentials)
2. **Detects recurring payments** (rent, subscriptions, loan instalments) by
   grouping transactions with consistent amounts and intervals
3. **Fits simple statistical models** to whatever is left over — everyday
   spending and irregular income — from the historical pattern
4. **Runs a Monte Carlo simulation**: thousands of simulated possible futures,
   each applying the known recurring payments plus random draws from the
   fitted spending/income models
5. **Reports a probabilistic forecast** — not "you'll have R X on day 30," but
   "here's the range of likely outcomes, and here's your risk of going
   negative"

See [`FORECAST_EXPLANATION.md`](./FORECAST_EXPLANATION.md) for the full
methodology, signals used, and assumptions.

## Which Investec API data it uses

- `GET /za/pb/v1/accounts` — to find the account to analyze
- `GET /za/pb/v1/accounts/{accountId}/transactions` — full transaction
  history, including `transactionDate`, `description`, `type` (DEBIT/CREDIT),
  `amount`, and `runningBalance`

Authentication uses the standard 2-legged OAuth client-credentials flow
(`client_id` + `client_secret` + `x-api-key` → bearer token).

## Architecture

```
future-you-runway/
├── src/                      # Core analysis pipeline (pure Python, no API dependency)
│   ├── generate_synthetic_data.py   # Synthetic transaction generator (for demo/testing)
│   ├── detect_recurring.py          # Recurring payment detection
│   ├── split_transactions.py        # Splits history into recurring vs irregular
│   ├── fit_models.py                # Fits spending & income distributions
│   ├── simulate.py                  # Monte Carlo simulation engine
│   └── visualize.py                 # Static chart generation (matplotlib)
├── backend/
│   ├── investec_client.py           # Investec API OAuth + data fetching
│   ├── app.py                       # Flask API (ties pipeline together)
│   └── requirements.txt
├── frontend/
│   ├── index.html / style.css / app.js   # Dashboard UI (vanilla JS, Chart.js)
└── data/
    └── synthetic_transactions.csv        # Bundled fallback dataset
```

The backend tries live Investec data first; if credentials are missing or
the API call fails for any reason, it **transparently falls back** to the
bundled synthetic dataset, so the app is always demoable. Which source was
used is reported explicitly in the API response (`data_source` field) —
never silently substituted without saying so.

## Setup & running it

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your Investec Sandbox credentials
(get these from the Investec Developer Community sandbox docs):

```
INVESTEC_CLIENT_ID=...
INVESTEC_CLIENT_SECRET=...
INVESTEC_API_KEY=...
```

If you skip this step, the app still runs — it'll just use the synthetic
dataset instead.

```bash
python app.py
```

The API is now running at `http://localhost:5000`.

### 2. Frontend

Just open `frontend/index.html` directly in a browser (or serve it with
VS Code's Live Server extension). It calls the backend at
`http://localhost:5000` automatically.

### 3. Command-line pipeline (no server needed)

Each stage of the pipeline can also be run standalone against the synthetic
dataset:

```bash
cd src
python generate_synthetic_data.py   # creates data/synthetic_transactions.csv
python detect_recurring.py          # prints detected recurring payments
python split_transactions.py        # prints the recurring/irregular split
python fit_models.py                # prints fitted distribution parameters
python simulate.py                  # runs the Monte Carlo forecast, prints summary
python visualize.py                 # saves a forecast chart to output/
```

## What it doesn't do

- It doesn't give financial advice or guarantee any outcome — it's a
  statistical simulation based on historical patterns, which may not hold in
  the future.
- It doesn't detect fraud or flag anomalous individual transactions.
- It doesn't handle multiple accounts simultaneously (uses the first account
  returned by the API).
- It doesn't account for payments that drift by more than a day or two from
  their usual day-of-month.
- It doesn't (yet) support the natural-language "can I afford X?" feature —
  noted as a stretch goal, not implemented in this submission.

## License

MIT — see [`LICENSE`](./LICENSE).
