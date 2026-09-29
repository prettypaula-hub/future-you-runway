# Knowledge / Gotchas

Notes from building this, in case they save someone else time.

## Investec API
- The Sandbox base URL is `https://openapisandbox.investec.com` — different
  from the production `https://openapi.investec.com`. Easy to mix up if
  you're following an older guide.
- The `Authorization` header value is `Basic <base64(client_id:client_secret)>`
  — Investec's docs provide this pre-encoded for sandbox credentials, but if
  you're constructing it yourself, double-check there's no trailing newline
  or extra whitespace in the encoded string.
- Access tokens are short-lived (~30 min). Cache the token and its expiry,
  don't re-authenticate on every request.
- Sandbox data is mock data and is **stateless** — don't expect balances to
  update if you simulate a transfer.

## Modeling gotchas
- Real transaction histories can have very few (or zero) irregular income
  events in a short pulled window — don't assume there will always be
  enough data points to compute a standard deviation. `np.std()` on an
  empty or single-element array can silently produce `NaN`, which then
  propagates through an entire Monte Carlo simulation without an obvious
  error — the output just looks wrong (identical NaN across every
  percentile), not crashed. Guard every distribution fit against 0-item and
  1-item cases explicitly.
- When tuning synthetic data for demos: if average income doesn't roughly
  balance average expenses over the history, the account can drift to an
  unrealistic wildly negative (or positive) balance by the end of the
  window, making the "current balance" starting point for the simulation
  unrepresentative. Worth sanity-checking the final balance after
  generating synthetic data, not just the transaction count.
- A starting balance that's healthy in isolation can still be immediately
  at risk if a large recurring payment (e.g. rent) is due very soon after
  the snapshot date — this isn't a bug, it's exactly the kind of risk this
  tool is meant to catch, but it can look alarming/deterministic in a demo
  if you're not expecting it.

## Local dev environment (Windows)
- PowerShell's `curl` is aliased to `Invoke-WebRequest`, which behaves
  differently from real curl (e.g. prompts a security warning on some
  responses, formats JSON output differently). `Invoke-WebRequest ... |
  Select-Object -Expand Content` gets you the raw JSON text.
- `venv\Scripts\activate` may be blocked by PowerShell's default execution
  policy. Fix with `Set-Execution Policy -ExecutionPolicy RemoteSigned -Scope
  CurrentUser` (only needs to be done once).
- File Explorer sometimes won't let you create a file starting with a dot
  (like `.env`), or silently appends `.txt`. Creating it via the terminal
  (`Set-Content -Path .env -Value "..."`) avoids this entirely.
- Always double check `pip install` is running inside the activated venv
  (prompt shows `(venv)`) — installing into the wrong Python environment is
  a very easy mistake to make and produces a confusing
  `ModuleNotFoundError` later.
