# Gauri · Debt-Service Truth Monitor (DSTM)

**Live app:** https://gauri-debt-service-truth-monitor-www.streamlit.app (Streamlit Community Cloud)

For a **credit analyst** deciding whether to sanction, renew, enhance, reprice or put a borrower on watch.
Universe: Nifty 200 non-financial companies (NSE industry "Financial Services" excluded; Screener's bank/NBFC
layout is also excluded as a safety net).

Two packages:

| Package | What it does |
|---|---|
| `dstm_data` | Data layer: Screener.in public pages -> SQLite cache -> tidy long tables (`observations`, `credit_lines`) |
| `dstm_rts` | Repayment Truth Score engine + Excel calculation sheet with live formulas |
| `dashboard` | Streamlit dashboard for the credit analyst (portfolio, drill-down, peers, refresh, downloads) |
| `dstm_ai` | AI credit pack (note, tailored covenants, triggers, due-diligence questions) via the Anthropic API, with number check, template fallback and usage log - see AI_LAYER.md |
| `dstm_validate` | Point-in-time back-test, leakage test, Breach Clock out-of-sample test, case studies, sensitivity |

## Setup (Windows / Mac / Linux)

```
pip install -r requirements.txt
copy ind_nifty200list.csv .          (the NSE list, next to this README)
python -m dstm_data refresh          # ~1 hour first time (1 request/second); later runs refresh only stale companies
python -m dstm_rts run               # scores + data/rts/RTS_calculation.xlsx
python -m dstm_validate              # back-test + cases + sensitivity -> data/validation/
streamlit run dashboard/app.py       # dashboard (Windows: double-click run_dashboard.bat)
python -m dstm_ai note TATASTEEL     # AI credit pack (needs ANTHROPIC_API_KEY; template otherwise)
python -m pytest -q tests            # 73 tests

Replaying the browser capture instead of fetching live:
python -m dstm_data refresh --replay dstm_capture_full.json.gz --basis primary --force --extra COFFEEDAY,ZEEL,RCOM,JETAIRWAYS,SUNTV
```

Useful options: `refresh --symbols TCS,LT`, `--force`, `--offline` (no network, rebuild from cache),
`--basis primary` (consolidated only, standalone as fallback), `--replay capture.json` (replay responses
captured in a browser with `tools/capture_screener.js`), `dstm_rts run --config my.json` (override any
setting), `dstm_rts run --demo` (synthetic demo universe).

## Data layer (dstm_data)

* requests + BeautifulSoup, Chrome User-Agent, at most 1 request/second, retries on 429/5xx/network errors
  (backoff 2-4-8 s, honours Retry-After), no retry on 403/404.
* SQLite cache (`data/dstm.db`): compressed raw responses; a failed fetch never overwrites a good copy, so
  the last good data is served (offline fallback). Companies older than 7 days are "stale"; only those are refreshed.
* `audit_log`: one row per HTTP attempt (URL, UTC time, status, bytes, ms, attempt, error).
* Both consolidated and standalone kept (`basis`, `basis_role`): lenders lend to the legal entity, and
  consolidated debt of groups with captive finance arms (L&T, M&M, Bajaj Auto ...) includes the NBFC's book.
* Verified Screener behaviour (2026-11-23): the schedules API `consolidated` flag is **presence-based** -
  any value (even `false`) returns consolidated; omit it for standalone. Stale consolidated pages
  (e.g. COLPAL to 2010, GVT&D to 2010) fall back to standalone. "(S)" columns, "10m" part-years and the
  half-year balance-sheet column are flagged.
* Interest paid: financing cash flow -> operating cash flow (flagged) -> P&L interest (flagged).
  Repayments include "Redemption of debentures"-type lines; unknown financing lines are reported in `data_quality`.

## Repayment Truth Score (dstm_rts)

| Step | Definition |
|---|---|
| CFO_adj | CFO - payables stretch beyond own 3-yr norm - positive exceptional items - non-core income inside CFO |
| CFADS | CFO_adj + interest add-back (only the interest paid inside CFO, see proxies) |
| FA-DSCR | CFADS / (interest paid + repayments); variant: (CFADS - depreciation) / same |
| Minsky | Hedge: CFADS >= interest + repayments; Speculative: >= interest; Ponzi: < interest. Migration vs mean of prior 3 years; universe migration matrices |
| Refinancing dependence | new borrowing / (interest + repayments), 3-yr pooled |
| Breach Clock | paired seasonal year-on-year bootstrap of 13 quarters of EBITDA and interest; covenants ICR >= 2.0x, Debt/EBITDA <= 4.0x; P(breach within 4 quarters), median quarters to breach; baseline and stress (EBITDA -25%, interest +20%, no growth drift) |
| RTS | 0.35 S_dscr + 0.25 S_minsky + 0.20 S_refi + 0.20 S_breach (weights in `RTSConfig`, re-normalised if a component is missing) |
| Class | Safe >= 70, Watch >= 45, else Escalate; overrides (already in breach, P >= 50%, Ponzi -> Escalate; P >= 20%, Speculative & deteriorating, maint. DSCR < 1, refinancing > 75%, payables stretch > 10% of CFO -> Watch) |

### Proxies (honest list - also in the code docstrings)
1. **Payable days on operating expenses** (Sales - Operating Profit), as COGS is not available for every company.
2. **Non-core income** = other income (normal) - interest & dividends received (those are in investing CF under
   Ind AS 7). CFO already strips some gains, so this is conservative.
3. **Interest add-back "auto"**: the textbook FA-DSCR adds interest back to CFO; most Indian companies report
   interest paid in financing, so their CFO is already pre-interest and a blanket add-back double-counts.
   `interest_addback="always"` reproduces the literal formula. With a P&L-interest fallback the location is inferred.
4. **Repayments are gross** (include roll-overs of short-term debt / CP); scheduled principal is not on Screener.
5. **Lease principal** = Screener "Financial liabilities" outflow, included in repayments (Ind AS 116).
6. **Maintenance capex** = depreciation.
7. **Breach Clock debt** held at the latest reported balance sheet (no quarterly debt); covenant ICR is EBITDA-based.

### Calculation sheet (`RTS_calculation.xlsx`)
README -> Settings (named, editable levers) -> **Sources** (every Screener number with source line, flag, URL,
fetch time) -> Annual (inputs are green links to Sources; every step a formula) -> Quarters -> BreachClock
(TTM covenant tests as formulas; Monte Carlo probabilities as blue Python values with seed) -> Company (pooled
FA-DSCR, sub-scores, RTS, class) -> Migration (COUNTIFS matrices) -> Checks (Excel vs Python; all 0).

### Tests
`tests/test_rts.py` hand-works Sessions 5-8 numbers (Apex Auto: cash conversion 20%, accrual 4.4%; DSCR/Minsky
with the S9-10 debt service of 30 + 50; Healthy vs Growth Pharma accruals -1.6% / 11.0%) plus written-out cases
for the payables stretch, deductions, interest add-back modes, leases, migration matrix, Breach Clock
(deterministic decline: breach at quarter 3, stress at quarter 1) and the score arithmetic.
`tests/test_data_layer.py` covers parsing, URL/flag rules, basis choice, fallbacks, retries, rate limit and the cache.

## Dashboard (`streamlit run dashboard/app.py`, or double-click `run_dashboard.bat` on Windows)

* **Portfolio (landing):** Safe / Watch / Escalate counts; top 10 to review today (Escalate > Watch > Safe, then
  already in breach, breach probability, downward migration, lowest RTS); every company sorted by Breach Clock
  (click a row to open it); Minsky transition heatmaps (year-to-year, and latest vs 3 years earlier) plus a
  company x year state grid. Filters: sector, class, case studies.
* **Company drill-down:** RTS and sub-scores; recommended decision (Enhance / Renew / Reprice / Watch / Hold) with a
  covenant package and today's headroom; tabs: forensic vs reported DSCR and the CFO-to-CFADS bridge, Minsky history,
  Breach Clock fan charts (baseline / stress), red flags, peer percentiles (NSE industry and universe), source lines
  with URLs, and a one-company calculation workbook.
* **Method & data:** fetch status, audit log, validation status, definitions and proxies.
* **Live Screener data (sidebar, and a button on each company page):** fetches the latest published figures from
  Screener.in on demand - chosen companies, companies missing or older than 7 days, or the entire universe - at
  1 request/second (~13 s per company, ~35 min for everything). The fetch runs in a background thread on the server,
  so it keeps going if the tab is closed; progress, time left and a Stop button are shown to every visitor, and the
  dashboard re-scores automatically when it ends ("Show fetched so far" re-scores mid-run). If Screener cannot be
  reached from the server, nothing changes and the message says so. *Import browser capture* (.json / .json.gz) is
  the fallback when the server is blocked.
* **Sidebar:** data source, latest fetch time and how many companies were fetched live; model settings (covenants,
  weights, class cut-offs, judgement calls); downloads (scores CSV, full calculation workbook, settings JSON).
* **Data merge and offline fallback:** companies in the live cache `data/dstm.db` replace their rows in the snapshot
  `dashboard/snapshot/credit_lines.parquet`; every other company keeps its snapshot figures, so fetching one company
  never shrinks the portfolio. Each company page shows when its figures were fetched and whether they are live or
  from the snapshot. With neither, a synthetic demo with a red banner. `DSTM_DATA_DIR` / `DSTM_SNAPSHOT_DIR` override folders.
* The recommended decision is a rule-based suggestion (`dstm_rts/decision.py`); the analyst decides.

## Hosting (Streamlit Community Cloud) and data refresh

* App: Streamlit Community Cloud, repository `gauri-debt-service-truth-monitor`, branch `main`, main file
  `dashboard/app.py`, custom subdomain `gauri-debt-service-truth-monitor-www`. Optional secrets (App settings > Secrets):
  `ANTHROPIC_API_KEY`, `DSTM_AI_MODEL` (see `.streamlit/secrets.toml.example`); without a key the AI tab uses the template.
* Data: the GitHub Action **Refresh Screener data** (`.github/workflows/refresh-data.yml`) runs every Monday 04:00 IST
  and on demand (Actions tab > Run workflow). It fetches Screener at 1 request/second (~40 minutes), runs the back-test,
  and commits `dashboard/snapshot/` (credit lines, fetch status, validation tables). The app redeploys on that commit and
  opens on real data. If a run gets too few companies, the previous snapshot is kept.
* Hosted storage is temporary: figures fetched with "Live Screener data" inside the hosted app and the AI log last
  until the app restarts or redeploys (which also happens after the weekly snapshot commit, which brings fresh data).
  Download the AI appendix from the Method & data page after a session; the committed snapshot is the durable data.
