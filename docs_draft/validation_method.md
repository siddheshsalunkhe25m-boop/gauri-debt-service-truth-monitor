## How the test was set up

**Point-in-time cohorts.** Every company is scored as of 30 June of each year from 2017 to 2024, using only
what was public by then: fiscal years ending at least 90 days earlier (SEBI LODR gives 60 days for audited
annual results), quarters ending at least 45 days earlier, no TTM or market-snapshot numbers. Outcomes are
measured afterwards: the next two fiscal years for the financial outcomes, and the 24 months after the as-of
date for the share price. 2025 and 2026 cohorts are scored but excluded from the statistics because their
outcome windows are not complete.

**What is being tested.** RTS-3 = FA-DSCR (35) + Minsky state/migration (25) + refinancing dependence (20),
re-weighted to 100. The Breach Clock cannot be back-tested across years: Screener's public pages carry only 13
quarters (Sep 2023 onwards). It gets its own single-cohort test instead: forecast made as of 15 Nov 2025 with
quarters to Sep 2025, compared with the actual covenant test over Dec 2025 - Sep 2026.

**Outcomes (two-year window).**
| Outcome | Definition |
|---|---|
| icr_fall | interest cover (EBITDA / P&L interest) falls below 60% of its as-of level in either of the next two years (only companies with interest >= Rs 1 Cr and as-of cover <= 25x) |
| new_loss | a net loss in either of the next two years, for companies profitable at the as-of year |
| drawdown50 | share price falls more than 50% from its running peak within 24 months (weekly closes, price only) |
| any_new_event | any of the three - the headline test |
| loss / any_event | the same including companies already loss-making (persistence - reported, not headlined) |

**Benchmarks.** Plain metrics a credit analyst would use without forensic adjustments, scored on the same
companies: reported-CFO DSCR (3-yr pooled, no payables, exceptional, non-core or lease adjustments), interest
cover, Debt/EBITDA. If RTS-3 cannot beat these, the forensic adjustments add nothing.

**Statistics.** AUC (probability a company that later had an event scored riskier than one that did not; 0.5
= coin flip), with 95% intervals from a company-cluster bootstrap (whole companies resampled, because the same
company appears in up to 8 overlapping cohorts). Event rates by class, Minsky state and quintile; AUC per cohort.

**Leakage test.** For each cohort every value dated after the information cut-off is multiplied by a random
number between -3 and 3 and the cohort is re-scored. Any change in any score would prove future data leaked.

## Look-ahead and bias register

| Risk | Severity | What it does | What was done |
|---|---|---|---|
| Survivorship: universe = today's Nifty 200 | HIGH | Companies that failed between 2017 and 2024 are missing, so few severe events and an easier test | Case studies of failed names outside the index; augmented-sample AUC reported |
| Restatements: Screener shows the latest figures for past years | MEDIUM | An analyst in 2018 saw the originally published numbers; later restatements (Ind AS transition FY2017, mergers, demergers) can leak later knowledge into "past" data | Cannot be removed with Screener; flagged. Vintage data would need annual-report PDFs |
| Basis choice from today's pages | LOW-MEDIUM | Consolidated vs standalone picked with today's information | Affects few companies (stale consolidated pages); listed in data_quality |
| Overlapping outcome windows | MEDIUM | Consecutive cohorts share outcome years: observations are not independent | Company-cluster bootstrap; results also shown per cohort |
| Breach Clock not back-testable | HIGH for that component | Only 13 quarters on Screener | Single-cohort out-of-sample test; weight sensitivity incl. dropping it |
| Weights / thresholds chosen before the test, not tuned | - | Tuning on these results would be in-sample fitting | Sensitivity shown as robustness, not optimisation; no weights changed after seeing results |
| Price-only drawdown | LOW | Ignores dividends; suspended stocks (RCom, Jet) stop trading, so drawdown is understated | Coverage rule (75% of weeks); suspensions noted in case studies |
| Small number of events | MEDIUM | Wide intervals | Intervals reported; no claim made where the interval crosses 0.5 |
