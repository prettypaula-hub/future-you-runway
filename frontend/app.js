const API_BASE = "http://localhost:5000";

let currentAccountId = null;
let forecastChartInstance = null;
let whatifChartInstance = null;

// ---------- Tabs ----------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-page").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`page-${btn.dataset.tab}`).classList.add("active");
  });
});

// ---------- Boot sequence ----------
async function init() {
  const loadingEl = document.getElementById("loading");
  const contentEl = document.getElementById("content");
  const errorEl = document.getElementById("error");

  try {
    const accountsResp = await fetch(`${API_BASE}/api/accounts`);
    if (!accountsResp.ok) throw new Error(`Server responded with ${accountsResp.status}`);
    const accountsData = await accountsResp.json();

    renderDataSourceBadge(accountsData.data_source);
    populateAccountSelector(accountsData.accounts);

    currentAccountId = accountsData.accounts[0].accountId;
    await loadForecastFor(currentAccountId);

    loadingEl.classList.add("hidden");
    contentEl.classList.remove("hidden");
  } catch (err) {
    loadingEl.classList.add("hidden");
    errorEl.classList.remove("hidden");
    errorEl.textContent =
      "Couldn't load the app. Is the backend running at " + API_BASE + "? (" + err.message + ")";
  }
}

function populateAccountSelector(accounts) {
  const select = document.getElementById("account-select");
  select.innerHTML = accounts
    .map((a) => `<option value="${a.accountId}">${a.accountName}</option>`)
    .join("");

  select.addEventListener("change", async (e) => {
    currentAccountId = e.target.value;
    await loadForecastFor(currentAccountId);
    document.getElementById("whatif-result").classList.add("hidden");
  });
}

function renderDataSourceBadge(source) {
  const badge = document.getElementById("data-source-badge");
  badge.textContent =
    source === "investec_live"
      ? "Live Investec sandbox data"
      : "Synthetic demo data (no live credentials configured)";
}

// ---------- Overview tab ----------
async function loadForecastFor(accountId) {
  const response = await fetch(`${API_BASE}/api/forecast?account_id=${encodeURIComponent(accountId)}&horizon_days=30`);
  if (!response.ok) throw new Error(`Server responded with ${response.status}`);
  const data = await response.json();

  renderSummaryCards(data);
  renderChart(data);
  renderRecurringTable(data.recurring_payments);
  renderAssumptions(data.assumptions);
}

function renderSummaryCards(data) {function renderSummaryCards(data) {
  const container = document.getElementById("summary-cards");
  const risk = data.risk_summary;
  const balance = data.starting_balance;

  const finalMedian =
    data.forecast.p50[data.forecast.p50.length - 1];

  const recurringTotal = data.recurring_payments.reduce(
    (total, payment) => total + payment.typical_amount,
    0
  );

  const negative30 = risk.pct_negative_within_30 * 100;
  const stayingPositive = risk.pct_never_negative * 100;

  let riskLabel;
  if (negative30 === 0) {
    riskLabel = "Very low";
  } else if (negative30 < 1) {
    riskLabel = `${negative30.toFixed(2)}%`;
  } else {
    riskLabel = `${negative30.toFixed(1)}%`;
  }

  container.innerHTML = `
    <div class="stat-card">
      <div class="stat-value">
        R${balance.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        })}
      </div>
      <div class="stat-label">Current balance</div>
    </div>

    <div class="stat-card">
      <div class="stat-value safe">
        R${finalMedian.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        })}
      </div>
      <div class="stat-label">Median projected balance in ${data.horizon_days} days</div>
    </div>

    <div class="stat-card">
      <div class="stat-value safe">
        ${riskLabel}
      </div>
      <div class="stat-label">Chance of going below R0 within ${data.horizon_days} days</div>
    </div>

    <div class="stat-card">
      <div class="stat-value">
        R${recurringTotal.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        })}
      </div>
      <div class="stat-label">Detected recurring payments / month</div>
    </div>
  `;

  document.getElementById("horizon-label").textContent = data.horizon_days;
}}

function buildBandDatasets(p10, p50, p90, colorHex) {
  return [
    {
      label: "90th percentile",
      data: p90,
      borderColor: "rgba(0,0,0,0)",
      backgroundColor: `${colorHex}26`,
      fill: "+1",
      pointRadius: 0,
      tension: 0.2,
    },
    {
      label: "Median projected balance",
      data: p50,
      borderColor: colorHex,
      backgroundColor: "transparent",
      borderWidth: 2.5,
      pointRadius: 0,
      tension: 0.2,
    },
    {
      label: "10th percentile",
      data: p10,
      borderColor: "rgba(0,0,0,0)",
      backgroundColor: `${colorHex}26`,
      fill: false,
      pointRadius: 0,
      tension: 0.2,
    },
  ];
}

const chartBaseOptions = {
  responsive: true,
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { labels: { color: "#8A94A6", usePointStyle: true, boxWidth: 8 } },
    tooltip: {
      callbacks: { label: (ctx) => `${ctx.dataset.label}: R${ctx.parsed.y.toFixed(2)}` },
    },
  },
  scales: {
    x: {
      title: { display: true, text: "Days from today", color: "#8A94A6" },
      ticks: { color: "#8A94A6" },
      grid: { color: "#263A57" },
    },
    y: {
      title: { display: true, text: "Balance (R)", color: "#8A94A6" },
      ticks: { color: "#8A94A6" },
      grid: { color: "#263A57" },
    },
  },
};

function renderChart(data) {
  const ctx = document.getElementById("forecastChart").getContext("2d");
  const { days, p10, p50, p90 } = data.forecast;

  if (forecastChartInstance) forecastChartInstance.destroy();

  forecastChartInstance = new Chart(ctx, {
    type: "line",
    data: { labels: days, datasets: buildBandDatasets(p10, p50, p90, "#4ECDC4") },
    options: chartBaseOptions,
  });
}
function renderRecurringTable(recurringPayments) {
  const tbody = document.querySelector("#recurring-table tbody");

  console.log("Recurring payments received by frontend:", recurringPayments);

  if (!recurringPayments || recurringPayments.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="color: var(--text-muted);">
          No recurring payments detected for this account.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = recurringPayments.map((p) => `
    <tr>
      <td>${p.description}</td>
      <td>
        R${Number(p.typical_amount).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2
        })}
      </td>
      <td>${Math.round(Number(p.typical_interval_days))} days</td>
      <td>${p.occurrences}</td>
    </tr>
  `).join("");
}

function renderAssumptions(assumptions) {
  const list = document.getElementById("assumptions-list");
  list.innerHTML = assumptions.map((a) => `<li>${a}</li>`).join("");
}

// ---------- What If tab ----------
document.getElementById("whatif-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const amount = parseFloat(document.getElementById("whatif-amount").value);
  const day = parseInt(document.getElementById("whatif-day").value, 10);
  const submitBtn = e.target.querySelector("button");

  submitBtn.disabled = true;
  submitBtn.textContent = "Running simulation…";

  try {
    const response = await fetch(`${API_BASE}/api/whatif`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_id: currentAccountId,
        amount,
        day,
        horizon_days: 30,
      }),
    });
    if (!response.ok) throw new Error(`Server responded with ${response.status}`);
    const data = await response.json();

    renderWhatifResult(data);
  } catch (err) {
    alert("Couldn't run that scenario: " + err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Run scenario";
  }
});
function renderWhatifResult(data) {
  const resultEl = document.getElementById("whatif-result");
  resultEl.classList.remove("hidden");

  const baseline = data.baseline.risk_summary;
  const withExpense = data.with_expense.risk_summary;

  const baselinePct = baseline.pct_never_negative * 100;
  const withExpensePct = withExpense.pct_never_negative * 100;

  const difference = withExpensePct - baselinePct;

  // Final median balances
  const baselineFinal =
    data.baseline.forecast.p50[data.baseline.forecast.p50.length - 1];

  const withExpenseFinal =
    data.with_expense.forecast.p50[
      data.with_expense.forecast.p50.length - 1
    ];

  const balanceImpact = withExpenseFinal - baselineFinal;

  const formatProbability = (value) => {
    if (value >= 99.995) return "99.99%+";
    if (value < 0.01) return "<0.01%";
    return `${value.toFixed(2)}%`;
  };

  const formatMoney = (value) =>
    `R${Math.abs(value).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;

  const container = document.getElementById("whatif-summary-cards");

  container.innerHTML = `
    <div class="stat-card">
      <div class="stat-value safe">
        ${formatMoney(baselineFinal)}
      </div>
      <div class="stat-label">
        Projected median balance after ${data.baseline.horizon_days} days — baseline
      </div>
    </div>

    <div class="stat-card">
      <div class="stat-value ${withExpenseFinal >= 0 ? "safe" : "risk"}">
        ${formatMoney(withExpenseFinal)}
      </div>
      <div class="stat-label">
        Projected median balance after ${data.with_expense.horizon_days} days — with expense
      </div>
    </div>

    <div class="stat-card">
      <div class="stat-value risk">
        -${formatMoney(balanceImpact)}
      </div>
      <div class="stat-label">
        Change in projected median balance
      </div>
    </div>

    <div class="stat-card">
      <div class="stat-value">
        ${formatProbability(withExpensePct)}
      </div>
      <div class="stat-label">
        Chance of staying positive with this expense
      </div>
    </div>
  `;

  const ctx = document.getElementById("whatifChart").getContext("2d");

  if (whatifChartInstance) {
    whatifChartInstance.destroy();
  }

  const { days } = data.baseline.forecast;

  whatifChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: days,
      datasets: [
        {
          label: "Median balance — baseline",
          data: data.baseline.forecast.p50,
          borderColor: "#4ECDC4",
          backgroundColor: "transparent",
          borderWidth: 2.5,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Median balance — with expense",
          data: data.with_expense.forecast.p50,
          borderColor: "#FF6B6B",
          backgroundColor: "transparent",
          borderWidth: 2.5,
          borderDash: [6, 4],
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    },
    options: chartBaseOptions,
  });
}

init();
