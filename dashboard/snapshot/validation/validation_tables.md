## Cohort coverage and event rates (universe, cohorts 2017-2024)

|   cohort |   n |   any_new |   icr_fall |   new_loss |   drawdown50 |
|---------:|----:|----------:|-----------:|-----------:|-------------:|
|     2017 | 135 |     0.244 |      0.198 |      0.041 |        0.152 |
|     2018 | 136 |     0.485 |      0.253 |      0.098 |        0.45  |
|     2019 | 137 |     0.38  |      0.273 |      0.129 |        0.311 |
|     2020 | 146 |     0.192 |      0.16  |      0.082 |        0.059 |
|     2021 | 147 |     0.205 |      0.121 |      0.054 |        0.138 |
|     2022 | 147 |     0.199 |      0.239 |      0.045 |        0.043 |
|     2023 | 147 |     0.177 |      0.196 |      0.029 |        0.043 |
|     2024 | 147 |     0.177 |      0.119 |      0.007 |        0.116 |

## AUC by outcome and risk score (company-cluster bootstrap 95% CI)

| outcome       | risk_score                       |   n_obs |   n_events |   auc |   auc_lo95 |   auc_hi95 |   rts_minus_this_auc |   gap_lo95 |   gap_hi95 |
|:--------------|:---------------------------------|--------:|-----------:|------:|-----------:|-----------:|---------------------:|-----------:|-----------:|
| any_new_event | RTS-3 (100 - score)              |    1140 |        290 | 0.651 |      0.603 |      0.693 |                      |            |            |
| any_new_event | Naive DSCR (reported CFO)        |    1140 |        290 | 0.632 |      0.581 |      0.68  |                0.019 |     -0.002 |      0.044 |
| any_new_event | Interest cover (EBITDA/interest) |    1140 |        290 | 0.665 |      0.614 |      0.706 |               -0.013 |     -0.047 |      0.019 |
| any_new_event | Debt / EBITDA                    |    1140 |        290 | 0.689 |      0.64  |      0.729 |               -0.037 |     -0.075 |      0.002 |
| any_event     | RTS-3 (100 - score)              |    1142 |        323 | 0.688 |      0.641 |      0.733 |                      |            |            |
| any_event     | Naive DSCR (reported CFO)        |    1142 |        323 | 0.664 |      0.613 |      0.713 |                0.024 |      0.003 |      0.048 |
| any_event     | Interest cover (EBITDA/interest) |    1142 |        323 | 0.704 |      0.652 |      0.751 |               -0.016 |     -0.05  |      0.019 |
| any_event     | Debt / EBITDA                    |    1142 |        323 | 0.725 |      0.675 |      0.771 |               -0.037 |     -0.075 |      0.005 |
| icr_fall      | RTS-3 (100 - score)              |     756 |        145 | 0.499 |      0.417 |      0.567 |                      |            |            |
| icr_fall      | Naive DSCR (reported CFO)        |     756 |        145 | 0.49  |      0.408 |      0.568 |                0.009 |     -0.033 |      0.045 |
| icr_fall      | Interest cover (EBITDA/interest) |     756 |        145 | 0.467 |      0.384 |      0.544 |                0.032 |     -0.037 |      0.087 |
| icr_fall      | Debt / EBITDA                    |     756 |        145 | 0.525 |      0.451 |      0.601 |               -0.026 |     -0.087 |      0.034 |
| new_loss      | RTS-3 (100 - score)              |    1029 |         61 | 0.69  |      0.601 |      0.767 |                      |            |            |
| new_loss      | Naive DSCR (reported CFO)        |    1029 |         61 | 0.68  |      0.566 |      0.783 |                0.01  |     -0.056 |      0.087 |
| new_loss      | Interest cover (EBITDA/interest) |    1029 |         61 | 0.718 |      0.643 |      0.803 |               -0.028 |     -0.111 |      0.059 |
| new_loss      | Debt / EBITDA                    |    1029 |         61 | 0.719 |      0.615 |      0.806 |               -0.028 |     -0.126 |      0.072 |
| loss          | RTS-3 (100 - score)              |    1140 |        130 | 0.746 |      0.693 |      0.808 |                      |            |            |
| loss          | Naive DSCR (reported CFO)        |    1140 |        130 | 0.748 |      0.685 |      0.818 |               -0.002 |     -0.048 |      0.042 |
| loss          | Interest cover (EBITDA/interest) |    1140 |        130 | 0.805 |      0.74  |      0.871 |               -0.059 |     -0.111 |      0.001 |
| loss          | Debt / EBITDA                    |    1140 |        130 | 0.813 |      0.733 |      0.883 |               -0.067 |     -0.14  |      0.017 |
| drawdown50    | RTS-3 (100 - score)              |    1083 |        174 | 0.64  |      0.594 |      0.687 |                      |            |            |
| drawdown50    | Naive DSCR (reported CFO)        |    1083 |        174 | 0.614 |      0.561 |      0.675 |                0.026 |     -0.005 |      0.056 |
| drawdown50    | Interest cover (EBITDA/interest) |    1083 |        174 | 0.646 |      0.596 |      0.704 |               -0.007 |     -0.05  |      0.038 |
| drawdown50    | Debt / EBITDA                    |    1083 |        174 | 0.662 |      0.606 |      0.721 |               -0.022 |     -0.069 |      0.029 |
| icr_below_2   | RTS-3 (100 - score)              |     977 |         51 | 0.754 |      0.63  |      0.846 |                      |            |            |
| icr_below_2   | Naive DSCR (reported CFO)        |     977 |         51 | 0.723 |      0.602 |      0.814 |                0.032 |     -0.02  |      0.089 |
| icr_below_2   | Interest cover (EBITDA/interest) |     977 |         51 | 0.754 |      0.634 |      0.852 |                0     |     -0.079 |      0.089 |
| icr_below_2   | Debt / EBITDA                    |     977 |         51 | 0.787 |      0.684 |      0.861 |               -0.032 |     -0.138 |      0.061 |

## Event rates by RTS class

| rts_class   |   n |   events |   rate | outcome       |
|:------------|----:|---------:|-------:|:--------------|
| Escalate    | 537 |      186 |  0.346 | any_new_event |
| Safe        | 224 |       24 |  0.107 | any_new_event |
| Watch       | 379 |       80 |  0.211 | any_new_event |
| Escalate    | 538 |      218 |  0.405 | any_event     |
| Safe        | 224 |       24 |  0.107 | any_event     |
| Watch       | 380 |       81 |  0.213 | any_event     |
| Escalate    | 485 |       91 |  0.188 | icr_fall      |
| Safe        |  59 |       11 |  0.186 | icr_fall      |
| Watch       | 212 |       43 |  0.203 | icr_fall      |
| Escalate    | 439 |       41 |  0.093 | new_loss      |
| Safe        | 223 |        3 |  0.013 | new_loss      |
| Watch       | 367 |       17 |  0.046 | new_loss      |
| Escalate    | 538 |      104 |  0.193 | loss          |
| Safe        | 224 |        4 |  0.018 | loss          |
| Watch       | 378 |       22 |  0.058 | loss          |
| Escalate    | 500 |      114 |  0.228 | drawdown50    |
| Safe        | 220 |       13 |  0.059 | drawdown50    |
| Watch       | 363 |       47 |  0.129 | drawdown50    |
| Escalate    | 402 |       39 |  0.097 | icr_below_2   |
| Safe        | 210 |        3 |  0.014 | icr_below_2   |
| Watch       | 365 |        9 |  0.025 | icr_below_2   |

## Event rates by Minsky state

| minsky_state   |   n |   events |   rate | outcome       |
|:---------------|----:|---------:|-------:|:--------------|
| Hedge          | 636 |      116 |  0.182 | any_new_event |
| Ponzi          | 225 |       98 |  0.436 | any_new_event |
| Speculative    | 279 |       76 |  0.272 | any_new_event |
| Hedge          | 637 |      117 |  0.184 | any_event     |
| Ponzi          | 226 |      122 |  0.54  | any_event     |
| Speculative    | 279 |       84 |  0.301 | any_event     |
| Hedge          | 306 |       60 |  0.196 | icr_fall      |
| Ponzi          | 199 |       49 |  0.246 | icr_fall      |
| Speculative    | 251 |       36 |  0.143 | icr_fall      |
| Hedge          | 620 |       21 |  0.034 | new_loss      |
| Ponzi          | 165 |       25 |  0.152 | new_loss      |
| Speculative    | 244 |       15 |  0.061 | new_loss      |
| Hedge          | 635 |       27 |  0.043 | loss          |
| Ponzi          | 226 |       71 |  0.314 | loss          |
| Speculative    | 279 |       32 |  0.115 | loss          |
| Hedge          | 614 |       66 |  0.107 | drawdown50    |
| Ponzi          | 195 |       65 |  0.333 | drawdown50    |
| Speculative    | 274 |       43 |  0.157 | drawdown50    |
| Hedge          | 605 |       13 |  0.021 | icr_below_2   |
| Ponzi          | 133 |       24 |  0.18  | icr_below_2   |
| Speculative    | 239 |       14 |  0.059 | icr_below_2   |

## Event rates: migrated down into Speculative/Ponzi (1) vs not (0)

|   migrated_down |   n |   events |   rate | outcome       |
|----------------:|----:|---------:|-------:|:--------------|
|               0 | 927 |      214 |  0.231 | any_new_event |
|               1 | 213 |       76 |  0.357 | any_new_event |
|               0 | 929 |      234 |  0.252 | any_event     |
|               1 | 213 |       89 |  0.418 | any_event     |
|               0 | 577 |      107 |  0.185 | icr_fall      |
|               1 | 179 |       38 |  0.212 | icr_fall      |
|               0 | 846 |       41 |  0.048 | new_loss      |
|               1 | 183 |       20 |  0.109 | new_loss      |
|               0 | 927 |       89 |  0.096 | loss          |
|               1 | 213 |       41 |  0.192 | loss          |
|               0 | 884 |      125 |  0.141 | drawdown50    |
|               1 | 199 |       49 |  0.246 | drawdown50    |
|               0 | 805 |       32 |  0.04  | icr_below_2   |
|               1 | 172 |       19 |  0.11  | icr_below_2   |

## AUC by cohort

|   cohort | outcome       |   n |   events |   auc_rts3 |   auc_naive_dscr |
|---------:|:--------------|----:|---------:|-----------:|-----------------:|
|     2017 | any_new_event | 135 |       33 |      0.738 |            0.691 |
|     2018 | any_new_event | 136 |       66 |      0.604 |            0.589 |
|     2019 | any_new_event | 137 |       52 |      0.687 |            0.689 |
|     2020 | any_new_event | 146 |       28 |      0.773 |            0.778 |
|     2021 | any_new_event | 146 |       30 |      0.66  |            0.669 |
|     2022 | any_new_event | 146 |       29 |      0.685 |            0.66  |
|     2023 | any_new_event | 147 |       26 |      0.517 |            0.509 |
|     2024 | any_new_event | 147 |       26 |      0.588 |            0.588 |
|     2017 | icr_fall      |  86 |       17 |      0.456 |            0.46  |
|     2018 | icr_fall      |  87 |       22 |      0.498 |            0.41  |
|     2019 | icr_fall      |  88 |       24 |      0.586 |            0.588 |
|     2020 | icr_fall      | 106 |       17 |      0.644 |            0.712 |
|     2021 | icr_fall      |  99 |       12 |      0.408 |            0.483 |
|     2022 | icr_fall      |  92 |       22 |      0.452 |            0.451 |
|     2023 | icr_fall      |  97 |       19 |      0.39  |            0.338 |
|     2024 | icr_fall      | 101 |       12 |      0.426 |            0.479 |
|     2017 | new_loss      | 123 |        5 |      0.707 |            0.788 |
|     2018 | new_loss      | 123 |       12 |      0.539 |            0.529 |
|     2019 | new_loss      | 124 |       16 |      0.702 |            0.693 |
|     2020 | new_loss      | 122 |       10 |      0.888 |            0.893 |
|     2021 | new_loss      | 130 |        7 |      0.646 |            0.65  |
|     2022 | new_loss      | 133 |        6 |      0.646 |            0.566 |
|     2023 | new_loss      | 136 |        4 |      0.627 |            0.729 |
|     2024 | new_loss      | 138 |        1 |      0.657 |            0.62  |
|     2017 | drawdown50    | 125 |       19 |      0.789 |            0.717 |
|     2018 | drawdown50    | 129 |       58 |      0.611 |            0.599 |
|     2019 | drawdown50    | 132 |       41 |      0.68  |            0.716 |
|     2020 | drawdown50    | 135 |        8 |      0.697 |            0.624 |
|     2021 | drawdown50    | 138 |       19 |      0.648 |            0.661 |
|     2022 | drawdown50    | 138 |        6 |      0.807 |            0.779 |
|     2023 | drawdown50    | 139 |        6 |      0.428 |            0.427 |
|     2024 | drawdown50    | 147 |       17 |      0.604 |            0.572 |

## Event rate by RTS quintile within cohort (1 = lowest RTS)

|   q |   n |   rate | outcome       |
|----:|----:|-------:|:--------------|
|   1 | 233 |  0.378 | any_new_event |
|   2 | 226 |  0.332 | any_new_event |
|   3 | 226 |  0.274 | any_new_event |
|   4 | 226 |  0.177 | any_new_event |
|   5 | 229 |  0.109 | any_new_event |
|   1 | 156 |  0.192 | icr_fall      |
|   2 | 149 |  0.181 | icr_fall      |
|   3 | 149 |  0.174 | icr_fall      |
|   4 | 149 |  0.228 | icr_fall      |
|   5 | 153 |  0.183 | icr_fall      |
|   1 | 209 |  0.1   | new_loss      |
|   2 | 203 |  0.089 | new_loss      |
|   3 | 206 |  0.078 | new_loss      |
|   4 | 203 |  0.015 | new_loss      |
|   5 | 208 |  0.014 | new_loss      |
|   1 | 219 |  0.256 | drawdown50    |
|   2 | 215 |  0.2   | drawdown50    |
|   3 | 215 |  0.167 | drawdown50    |
|   4 | 215 |  0.093 | drawdown50    |
|   5 | 219 |  0.087 | drawdown50    |

## Augmented sample (universe + case companies), any_new_event

| outcome       | risk_score                       |   n_obs |   n_events |   auc |   auc_lo95 |   auc_hi95 |   rts_minus_this_auc |   gap_lo95 |   gap_hi95 |
|:--------------|:---------------------------------|--------:|-----------:|------:|-----------:|-----------:|---------------------:|-----------:|-----------:|
| any_new_event | RTS-3 (100 - score)              |    1178 |        319 | 0.657 |      0.613 |      0.705 |                      |            |            |
| any_new_event | Naive DSCR (reported CFO)        |    1178 |        319 | 0.639 |      0.592 |      0.69  |                0.018 |     -0.004 |      0.047 |
| any_new_event | Interest cover (EBITDA/interest) |    1178 |        319 | 0.67  |      0.624 |      0.72  |               -0.013 |     -0.045 |      0.015 |
| any_new_event | Debt / EBITDA                    |    1178 |        319 | 0.695 |      0.649 |      0.747 |               -0.038 |     -0.072 |     -0.003 |

## Leakage test (future values scrambled; scores must not move)

|   cohort |   n_scored |   n_future_values_scrambled |   max_abs_score_change | classes_identical   | passed   |
|---------:|-----------:|----------------------------:|-----------------------:|:--------------------|:---------|
|     2017 |        140 |                      121723 |                      0 | True                | True     |
|     2018 |        141 |                      112049 |                      0 | True                | True     |
|     2019 |        142 |                      102294 |                      0 | True                | True     |
|     2020 |        151 |                       92006 |                      0 | True                | True     |
|     2021 |        152 |                       81630 |                      0 | True                | True     |
|     2022 |        152 |                       71203 |                      0 | True                | True     |
|     2023 |        152 |                       60817 |                      0 | True                | True     |
|     2024 |        152 |                       45667 |                      0 | True                | True     |

## Breach Clock out-of-sample (as of 15 Nov 2025 -> next 4 quarters)

|   n_simulated |   n_already_in_breach |   persistence_already_in_breach |   insufficient |   realised_rate |   mean_p_base |   mean_p_stress |   brier_base |   brier_climatology |   auc_base |   auc_stress |   n_events |
|--------------:|----------------------:|--------------------------------:|---------------:|----------------:|--------------:|----------------:|-------------:|--------------------:|-----------:|-------------:|-----------:|
|           127 |                    20 |                               1 |              4 |           0.039 |         0.037 |           0.101 |        0.039 |               0.038 |      0.775 |        0.959 |          5 |

## Case studies: did RTS flag before the event?

| case       | peer       | event                                                                                                                                                          | event_date   |   pre_event_cohorts_scored | first_watch_or_escalate_asof   | first_escalate_asof   | last_pre_event_class   |   last_pre_event_rts | last_pre_event_state   | peer_last_pre_event_class   |   peer_last_pre_event_rts | peer_ever_flagged_pre_event   |
|:-----------|:-----------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------|---------------------------:|:-------------------------------|:----------------------|:-----------------------|---------------------:|:-----------------------|:----------------------------|--------------------------:|:------------------------------|
| COFFEEDAY  | JUBLFOOD   | Defaults to lenders from early 2019; founder's death Jul 2019 (Business Standard); SEBI later found ~Rs 3,535 Cr moved to promoter entity MACEL (Sessions 7-8) | 2019-01-31   |                          3 | 2016-06-30                     | 2016-06-30            | Escalate               |               18.448 | Speculative            | Watch                       |                    96.094 | True                          |
| ZEEL       | SUNTV      | Share price fell ~30% in a day on 25 Jan 2019 on promoter-pledge fears (Business Standard, BloombergQuint)                                                     | 2019-01-25   |                          3 | 2017-06-30                     | 2017-06-30            | Escalate               |               24.842 | Ponzi                  | Watch                       |                    64.561 | True                          |
| RCOM       | BHARTIARTL | Ericsson's insolvency petition for unpaid dues (Sep 2017); NCLT admission May 2018; CIRP from Jun 2019                                                         | 2017-09-30   |                          2 | 2016-06-30                     | 2016-06-30            | Escalate               |                3.925 | Ponzi                  | Watch                       |                    89.363 | True                          |
| JETAIRWAYS | INDIGO     | First debt default (31 Dec 2018); operations suspended 17 Apr 2019 (AP, Reuters)                                                                               | 2018-12-31   |                          3 | 2016-06-30                     | 2016-06-30            | Escalate               |               32.828 | Speculative            | Safe                        |                    96.094 | False                         |

## Case study paths

| case       | role     | symbol     |   cohort | latest_fy   |    rts | rts_class   | minsky_state   | migration     |   fa_dscr_3y |   naive_dscr_3y |   refi_dependence_3y |   loss |   max_drawdown_24m |
|:-----------|:---------|:-----------|---------:|:------------|-------:|:------------|:---------------|:--------------|-------------:|----------------:|---------------------:|-------:|-------------------:|
| COFFEEDAY  | stressed | COFFEEDAY  |     2016 | 2016-03-31  | 42.785 | Escalate    | Ponzi          | deteriorating |        1.107 |           1.251 |                0     |      0 |              0.243 |
| COFFEEDAY  | stressed | COFFEEDAY  |     2017 | 2017-03-31  | 73.017 | Watch       | Hedge          | improving     |        1.083 |           1.249 |                0     |      0 |              0.38  |
| COFFEEDAY  | stressed | COFFEEDAY  |     2018 | 2018-03-31  | 18.448 | Escalate    | Speculative    | stable        |        0.249 |           0.323 |                0.887 |      0 |              0.953 |
| COFFEEDAY  | stressed | COFFEEDAY  |     2019 | 2019-03-31  |  0     | Escalate    | Ponzi          | deteriorating |        0.09  |           0.133 |                1.169 |      1 |                    |
| COFFEEDAY  | stressed | COFFEEDAY  |     2020 | 2020-03-31  |  5.155 | Escalate    | Ponzi          | deteriorating |       -0.15  |           0.104 |                0.794 |      1 |                    |
| COFFEEDAY  | stressed | COFFEEDAY  |     2021 | 2021-03-31  | 11.218 | Escalate    | Ponzi          | stable        |       -0.232 |           0.091 |                0.708 |      1 |              0.628 |
| COFFEEDAY  | stressed | COFFEEDAY  |     2022 | 2022-03-31  | 26.455 | Escalate    | Ponzi          | stable        |       -0.488 |           0.14  |                0.098 |      1 |              0.55  |
| COFFEEDAY  | stressed | COFFEEDAY  |     2023 | 2023-03-31  | 39.581 | Escalate    | Speculative    | improving     |       -0.133 |           1.091 |                0.198 |      1 |              0.689 |
| COFFEEDAY  | stressed | COFFEEDAY  |     2024 | 2024-03-31  | 33.652 | Escalate    | Speculative    | improving     |        0.232 |           0.701 |                0.435 |      1 |              0.613 |
| COFFEEDAY  | stressed | COFFEEDAY  |     2025 | 2025-03-31  | 29.41  | Escalate    | Speculative    | stable        |        0.373 |           0.854 |                0.449 |      0 |                    |
| COFFEEDAY  | stressed | COFFEEDAY  |     2026 | 2026-03-31  | 18.662 | Escalate    | Ponzi          | deteriorating |        0.158 |           0.621 |                0.254 |        |                    |
| COFFEEDAY  | peer     | JUBLFOOD   |     2016 | 2016-03-31  | 96.094 | Safe        | Hedge          | stable        |              |          99     |                0     |      0 |              0.36  |
| COFFEEDAY  | peer     | JUBLFOOD   |     2017 | 2017-03-31  | 96.094 | Safe        | Hedge          | stable        |              |          99     |                0     |      0 |              0.319 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2018 | 2018-03-31  | 96.094 | Watch       | Hedge          | stable        |              |          99     |                0     |      0 |              0.319 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2019 | 2019-03-31  | 96.094 | Safe        | Hedge          | stable        |              |          99     |                0     |      0 |              0.318 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2020 | 2020-03-31  | 91.517 | Safe        | Hedge          | stable        |        2.303 |           9.461 |                0     |      0 |              0.461 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2021 | 2021-03-31  | 87.982 | Watch       | Hedge          | stable        |        1.882 |           5.802 |                0     |      0 |              0.516 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2022 | 2022-03-31  | 87.243 | Safe        | Hedge          | stable        |        2.023 |           4.78  |                0.098 |      0 |              0.319 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2023 | 2023-03-31  | 86.955 | Safe        | Hedge          | stable        |        2.14  |           7.915 |                0.14  |      0 |              0.251 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2024 | 2024-03-31  | 67.174 | Watch       | Hedge          | stable        |        1.986 |           9.416 |                0.887 |      0 |              0.448 |
| COFFEEDAY  | peer     | JUBLFOOD   |     2025 | 2025-03-31  | 69.926 | Watch       | Hedge          | stable        |        1.826 |           7.68  |                0.693 |      0 |                    |
| COFFEEDAY  | peer     | JUBLFOOD   |     2026 | 2026-03-31  | 71.003 | Watch       | Hedge          | stable        |        1.749 |           5.995 |                0.61  |        |                    |
| ZEEL       | stressed | ZEEL       |     2016 | 2016-03-31  | 95.651 | Safe        | Hedge          | stable        |       10.735 |          12.496 |                0.018 |      0 |              0.232 |
| ZEEL       | stressed | ZEEL       |     2017 | 2017-03-31  | 66.132 | Escalate    | Ponzi          | deteriorating |        2.696 |          17.793 |                0.025 |      0 |              0.47  |
| ZEEL       | stressed | ZEEL       |     2018 | 2018-03-31  | 24.842 | Escalate    | Ponzi          | deteriorating |       -2.146 |           6.411 |                0.006 |      0 |              0.772 |
| ZEEL       | stressed | ZEEL       |     2019 | 2019-03-31  | 24.686 | Escalate    | Ponzi          | deteriorating |       -5.87  |           4.497 |                0.013 |      0 |              0.692 |
| ZEEL       | stressed | ZEEL       |     2020 | 2020-03-31  | 28.701 | Escalate    | Ponzi          | stable        |       -2.831 |           2.934 |                0.008 |      0 |              0.421 |
| ZEEL       | stressed | ZEEL       |     2021 | 2021-03-31  | 98.864 | Safe        | Hedge          | improving     |        9.935 |          92.048 |                0.045 |      0 |              0.524 |
| ZEEL       | stressed | ZEEL       |     2022 | 2022-03-31  | 99.324 | Safe        | Hedge          | improving     |       14.52  |          98.952 |                0.027 |      0 |              0.536 |
| ZEEL       | stressed | ZEEL       |     2023 | 2023-03-31  | 67.606 | Escalate    | Ponzi          | deteriorating |       10.5   |          37.635 |                0.046 |      0 |              0.671 |
| ZEEL       | stressed | ZEEL       |     2024 | 2024-03-31  | 98.132 | Watch       | Hedge          | improving     |        2.824 |           8.079 |                0.028 |      0 |              0.532 |
| ZEEL       | stressed | ZEEL       |     2025 | 2025-03-31  | 85.475 | Safe        | Hedge          | improving     |        4.77  |          12.072 |                0.581 |      0 |                    |
| ZEEL       | stressed | ZEEL       |     2026 | 2026-03-31  | 86.073 | Escalate    | Hedge          | improving     |        6.473 |          16.452 |                0.557 |        |                    |
| ZEEL       | peer     | SUNTV      |     2016 | 2016-03-31  | 43.352 | Escalate    | Speculative    | deteriorating |        1.57  |           2.086 |                0.997 |      0 |              0.274 |
| ZEEL       | peer     | SUNTV      |     2017 | 2017-03-31  | 68.817 | Watch       | Hedge          | improving     |        2.045 |           2.513 |                0.997 |      0 |              0.531 |
| ZEEL       | peer     | SUNTV      |     2018 | 2018-03-31  | 64.561 | Watch       | Hedge          | stable        |        1.998 |           2.488 |                0.997 |      0 |              0.677 |
| ZEEL       | peer     | SUNTV      |     2019 | 2019-03-31  | 71.243 | Watch       | Hedge          | stable        |        5.984 |           6.693 |                0.994 |      0 |              0.509 |
| ZEEL       | peer     | SUNTV      |     2020 | 2020-03-31  | 72.51  | Watch       | Hedge          | stable        |        6.185 |           7.615 |                0.943 |      0 |              0.325 |
| ZEEL       | peer     | SUNTV      |     2021 | 2021-03-31  | 74.47  | Watch       | Hedge          | stable        |        6.238 |           8.394 |                0.865 |      0 |              0.325 |
| ZEEL       | peer     | SUNTV      |     2022 | 2022-03-31  | 75.781 | Watch       | Hedge          | stable        |        5.218 |           7.012 |                0.812 |      0 |              0.248 |
| ZEEL       | peer     | SUNTV      |     2023 | 2023-03-31  | 78.11  | Safe        | Hedge          | stable        |        8.652 |          12.136 |                0.719 |      0 |              0.388 |
| ZEEL       | peer     | SUNTV      |     2024 | 2024-03-31  | 77.813 | Safe        | Hedge          | stable        |       10.421 |          14.864 |                0.731 |      0 |              0.469 |
| ZEEL       | peer     | SUNTV      |     2025 | 2025-03-31  | 88.609 | Safe        | Hedge          | stable        |       29.814 |          88.537 |                0.299 |      0 |                    |
| ZEEL       | peer     | SUNTV      |     2026 | 2026-03-31  | 92.248 | Safe        | Hedge          | stable        |       34.547 |         152.378 |                0.154 |        |                    |
| RCOM       | stressed | RCOM       |     2016 | 2016-03-31  | 40.268 | Escalate    | Hedge          | improving     |        0.849 |           0.878 |                0.767 |      1 |              0.784 |
| RCOM       | stressed | RCOM       |     2017 | 2017-03-31  |  3.925 | Escalate    | Ponzi          | deteriorating |        0.474 |           0.578 |                0.843 |      1 |              0.963 |
| RCOM       | stressed | RCOM       |     2018 | 2018-03-31  |  0.305 | Escalate    | Ponzi          | deteriorating |        0.525 |           0.645 |                0.988 |      1 |              0.969 |
| RCOM       | stressed | RCOM       |     2019 | 2019-03-31  |  2.686 | Escalate    | Ponzi          | deteriorating |       -0.247 |           0.06  |                0.893 |      1 |              0.667 |
| RCOM       | stressed | RCOM       |     2020 | 2020-03-31  | 10.831 | Escalate    | Ponzi          | stable        |       -0.171 |           0.216 |                0.723 |      1 |              0.517 |
| RCOM       | stressed | RCOM       |     2021 | 2021-03-31  | 24.086 | Escalate    | Ponzi          | stable        |       -3.607 |           0.604 |                0.193 |      1 |              0.744 |
| RCOM       | stressed | RCOM       |     2022 | 2022-03-31  | 28.906 | Escalate    | Ponzi          | stable        |      -37.716 |           2.913 |                0     |      1 |              0.614 |
| RCOM       | stressed | RCOM       |     2023 | 2023-03-31  | 28.906 | Escalate    | Ponzi          | stable        |      -66.267 |           2.992 |                0     |      1 |              0.477 |
| RCOM       | stressed | RCOM       |     2024 | 2024-03-31  | 28.906 | Escalate    | Ponzi          | stable        |      -72.222 |           0.135 |                0     |      1 |              0.694 |
| RCOM       | stressed | RCOM       |     2025 | 2025-03-31  | 28.906 | Escalate    | Ponzi          | stable        |      -42.874 |          -0.661 |                0     |      1 |                    |
| RCOM       | stressed | RCOM       |     2026 | 2026-03-31  | 28.906 | Escalate    | Ponzi          | stable        |      -17.618 |          -0.189 |                0     |        |                    |
| RCOM       | peer     | BHARTIARTL |     2016 | 2016-03-31  | 92.336 | Safe        | Hedge          | stable        |        7.01  |           8.069 |                0.15  |      0 |              0.332 |
| RCOM       | peer     | BHARTIARTL |     2017 | 2017-03-31  | 89.363 | Watch       | Hedge          | stable        |        5.215 |           6.586 |                0.269 |      0 |              0.469 |
| RCOM       | peer     | BHARTIARTL |     2018 | 2018-03-31  | 91.762 | Watch       | Hedge          | stable        |        3.742 |           5.301 |                0.173 |      1 |              0.263 |
| RCOM       | peer     | BHARTIARTL |     2019 | 2019-03-31  | 28.587 | Escalate    | Speculative    | deteriorating |        1.014 |           1.419 |                0.874 |      1 |              0.323 |
| RCOM       | peer     | BHARTIARTL |     2020 | 2020-03-31  | 19.948 | Escalate    | Speculative    | deteriorating |        0.42  |           0.566 |                0.671 |      1 |              0.309 |
| RCOM       | peer     | BHARTIARTL |     2021 | 2021-03-31  | 24.027 | Escalate    | Speculative    | stable        |        0.447 |           0.524 |                0.664 |      0 |              0.155 |
| RCOM       | peer     | BHARTIARTL |     2022 | 2022-03-31  | 27.05  | Escalate    | Speculative    | stable        |        0.602 |           0.716 |                0.543 |      0 |              0.117 |
| RCOM       | peer     | BHARTIARTL |     2023 | 2023-03-31  | 59.848 | Watch       | Hedge          | improving     |        1.076 |           1.295 |                0.515 |      0 |              0.106 |
| RCOM       | peer     | BHARTIARTL |     2024 | 2024-03-31  | 76.44  | Watch       | Hedge          | improving     |        1.518 |           1.939 |                0.427 |      0 |              0.172 |
| RCOM       | peer     | BHARTIARTL |     2025 | 2025-03-31  | 76.693 | Watch       | Hedge          | stable        |        1.786 |           2.427 |                0.401 |      0 |                    |
| RCOM       | peer     | BHARTIARTL |     2026 | 2026-03-31  | 78.733 | Watch       | Hedge          | stable        |        1.8   |           2.309 |                0.327 |        |                    |
| JETAIRWAYS | stressed | JETAIRWAYS |     2016 | 2016-03-31  | 30.696 | Escalate    | Speculative    | improving     |        0.188 |           0.385 |                0.553 |      1 |              0.602 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2017 | 2017-03-31  | 13.318 | Escalate    | Ponzi          | stable        |        0.064 |           0.335 |                0.624 |      1 |              0.922 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2018 | 2018-03-31  | 32.828 | Escalate    | Speculative    | improving     |        0.158 |           0.433 |                0.468 |      1 |              0.961 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2019 | 2019-03-31  | 11.727 | Escalate    | Ponzi          | deteriorating |       -0.031 |           0.356 |                0.531 |      1 |              0.781 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2020 | 2020-03-31  | 10.746 | Escalate    | Ponzi          | stable        |       -1.439 |           0.129 |                0.726 |      1 |              0.555 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2021 | 2021-03-31  |  8.335 | Escalate    | Ponzi          | stable        |       -4.058 |          -0.151 |                0.823 |      1 |              0.599 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2022 | 2022-03-31  |  3.906 | Escalate    | Ponzi          | stable        |      -23.597 |          -2.785 |                2.231 |      1 |              0.645 |
| JETAIRWAYS | stressed | JETAIRWAYS |     2023 | 2023-03-31  | 55.278 | Escalate    | Hedge          | improving     |      -21.023 |           0.278 |                0.039 |        |                    |
| JETAIRWAYS | stressed | JETAIRWAYS |     2024 | 2023-03-31  | 55.278 | Escalate    | Hedge          | improving     |      -21.023 |           0.278 |                0.039 |        |                    |
| JETAIRWAYS | peer     | INDIGO     |     2016 | 2016-03-31  | 96.094 | Safe        | Hedge          | stable        |       31.755 |         250     |                0     |      0 |              0.276 |
| JETAIRWAYS | peer     | INDIGO     |     2017 | 2017-03-31  | 96.094 | Safe        | Hedge          | stable        |       37.446 |         238     |                0     |      0 |              0.49  |
| JETAIRWAYS | peer     | INDIGO     |     2018 | 2018-03-31  | 96.094 | Safe        | Hedge          | stable        |       43.961 |         216.02  |                0     |      1 |              0.529 |
| JETAIRWAYS | peer     | INDIGO     |     2019 | 2019-03-31  | 93.699 | Safe        | Hedge          | stable        |       18.24  |          33.625 |                0.096 |      1 |              0.529 |
| JETAIRWAYS | peer     | INDIGO     |     2020 | 2020-03-31  | 95.254 | Safe        | Hedge          | stable        |        4.333 |          41.326 |                0.034 |      1 |              0.295 |
| JETAIRWAYS | peer     | INDIGO     |     2021 | 2021-03-31  | 11.64  | Escalate    | Ponzi          | deteriorating |        0.523 |           2.541 |                0.534 |      1 |              0.295 |
| JETAIRWAYS | peer     | INDIGO     |     2022 | 2022-03-31  |  6.521 | Escalate    | Ponzi          | deteriorating |        0.093 |           0.393 |                0.739 |      1 |              0.158 |
| JETAIRWAYS | peer     | INDIGO     |     2023 | 2023-03-31  | 41.236 | Escalate    | Hedge          | improving     |        0.244 |           0.568 |                0.601 |      0 |              0.213 |
| JETAIRWAYS | peer     | INDIGO     |     2024 | 2024-03-31  | 48.589 | Watch       | Hedge          | improving     |        0.841 |           1.503 |                0.414 |      1 |              0.326 |
| JETAIRWAYS | peer     | INDIGO     |     2025 | 2025-03-31  | 90.7   | Safe        | Hedge          | improving     |        1.791 |           4.733 |                0     |      1 |                    |
| JETAIRWAYS | peer     | INDIGO     |     2026 | 2026-03-31  | 82.972 | Escalate    | Hedge          | stable        |        1.5   |           5.433 |                0     |        |                    |

## Sensitivity: weights

| scenario                 |   backtest_auc_any_new_event |   backtest_auc_icr_fall |   backtest_auc_new_loss |   backtest_auc_drawdown50 |   spearman_vs_base |   class_changes_vs_base |   n_safe |   n_watch |   n_escalate |   moved_to_escalate |   moved_out_of_escalate |
|:-------------------------|-----------------------------:|------------------------:|------------------------:|--------------------------:|-------------------:|------------------------:|---------:|----------:|-------------:|--------------------:|------------------------:|
| base 35/25/20/20         |                        0.651 |                   0.499 |                   0.69  |                     0.64  |              1     |                       0 |       41 |        62 |           49 |                   0 |                       0 |
| equal 25 each            |                        0.647 |                   0.503 |                   0.676 |                     0.634 |              0.994 |                       2 |       41 |        64 |           47 |                   0 |                       2 |
| DSCR-heavy 50/20/15/15   |                        0.649 |                   0.49  |                   0.694 |                     0.639 |              0.993 |                       5 |       41 |        57 |           54 |                   5 |                       0 |
| Minsky-heavy 25/40/15/20 |                        0.657 |                   0.519 |                   0.705 |                     0.65  |              0.994 |                       2 |       41 |        64 |           47 |                   0 |                       2 |
| Breach-heavy 25/20/15/40 |                        0.652 |                   0.502 |                   0.69  |                     0.641 |              0.992 |                      12 |       41 |        74 |           37 |                   0 |                      12 |
| drop FA-DSCR             |                        0.636 |                   0.535 |                   0.654 |                     0.624 |              0.936 |                      12 |       41 |        74 |           37 |                   0 |                      12 |
| drop Minsky              |                        0.634 |                   0.472 |                   0.657 |                     0.614 |              0.986 |                       5 |       41 |        57 |           54 |                   5 |                       0 |
| drop refinancing         |                        0.649 |                   0.503 |                   0.712 |                     0.647 |              0.942 |                       3 |       41 |        63 |           48 |                   1 |                       2 |
| drop Breach Clock        |                        0.651 |                   0.499 |                   0.69  |                     0.64  |              0.986 |                       5 |       41 |        57 |           54 |                   5 |                       0 |

## Sensitivity: judgement calls / proxies

| scenario                                    |   backtest_auc_any_new_event |   backtest_auc_icr_fall |   backtest_auc_new_loss |   backtest_auc_drawdown50 |   spearman_vs_base |   class_changes_vs_base |   n_safe |   n_watch |   n_escalate |   moved_to_escalate |   moved_out_of_escalate |
|:--------------------------------------------|-----------------------------:|------------------------:|------------------------:|--------------------------:|-------------------:|------------------------:|---------:|----------:|-------------:|--------------------:|------------------------:|
| base                                        |                        0.651 |                   0.499 |                   0.69  |                     0.64  |              1     |                       0 |       41 |        62 |           49 |                   0 |                       0 |
| interest add-back: always (literal formula) |                        0.64  |                   0.502 |                   0.686 |                     0.629 |              0.989 |                       9 |       45 |        63 |           44 |                   0 |                       5 |
| leases excluded from repayments             |                        0.647 |                   0.502 |                   0.69  |                     0.635 |              0.989 |                       5 |       42 |        61 |           49 |                   0 |                       0 |
| non-core: all other income                  |                        0.646 |                   0.505 |                   0.69  |                     0.628 |              0.963 |                       5 |       39 |        60 |           53 |                   4 |                       0 |
| non-core: none                              |                        0.646 |                   0.485 |                   0.684 |                     0.639 |              0.995 |                       4 |       43 |        62 |           47 |                   0 |                       2 |
| exceptional gains not deducted              |                        0.646 |                   0.496 |                   0.664 |                     0.637 |              0.995 |                       3 |       44 |        59 |           49 |                   0 |                       0 |
| payables norm 5 years                       |                        0.653 |                   0.499 |                   0.691 |                     0.641 |              0.997 |                       8 |       45 |        60 |           47 |                   0 |                       2 |
| class cut-offs 65/40                        |                        0.651 |                   0.499 |                   0.69  |                     0.64  |              1     |                       2 |       41 |        64 |           47 |                   0 |                       2 |
| class cut-offs 75/50                        |                        0.651 |                   0.499 |                   0.69  |                     0.64  |              1     |                       4 |       41 |        58 |           53 |                   4 |                       0 |

## Sensitivity: covenant thresholds (today + Breach Clock test)

|   icr_min |   debt_ebitda_max |   n_already_in_breach |   median_p_base |   share_p_base_ge_20pct |   spearman_vs_base |   class_changes_vs_base |   n_safe |   n_watch |   n_escalate |   moved_to_escalate |   moved_out_of_escalate |   bc_test_n_simulated |   bc_test_n_already_in_breach |   bc_test_persistence_already_in_breach |   bc_test_insufficient |   bc_test_realised_rate |   bc_test_mean_p_base |   bc_test_mean_p_stress |   bc_test_brier_base |   bc_test_brier_climatology |   bc_test_auc_base |   bc_test_auc_stress |   bc_test_n_events |
|----------:|------------------:|----------------------:|----------------:|------------------------:|-------------------:|------------------------:|---------:|----------:|-------------:|--------------------:|------------------------:|----------------------:|------------------------------:|----------------------------------------:|-----------------------:|------------------------:|----------------------:|------------------------:|---------------------:|----------------------------:|-------------------:|---------------------:|-------------------:|
|       1.5 |                 3 |                    27 |               0 |                   0.211 |              0.997 |                       2 |       41 |        60 |           51 |                   2 |                       0 |                   115 |                            32 |                                   1     |                      4 |                   0.035 |                 0.02  |                   0.096 |                0.026 |                       0.034 |              0.739 |                0.667 |                  4 |
|       1.5 |                 4 |                    22 |               0 |                   0.178 |              1     |                       0 |       41 |        62 |           49 |                   0 |                       0 |                   127 |                            20 |                                   1     |                      4 |                   0.039 |                 0.033 |                   0.097 |                0.035 |                       0.038 |              0.777 |                0.959 |                  5 |
|       1.5 |                 5 |                    16 |               0 |                   0.138 |              0.999 |                       3 |       41 |        65 |           46 |                   0 |                       3 |                   131 |                            16 |                                   1     |                      4 |                   0.031 |                 0.023 |                   0.079 |                0.044 |                       0.03  |              0.822 |                0.972 |                  4 |
|       2   |                 3 |                    27 |               0 |                   0.211 |              0.997 |                       2 |       41 |        60 |           51 |                   2 |                       0 |                   115 |                            32 |                                   1     |                      4 |                   0.035 |                 0.02  |                   0.096 |                0.026 |                       0.034 |              0.739 |                0.664 |                  4 |
|       2   |                 4 |                    22 |               0 |                   0.178 |              1     |                       0 |       41 |        62 |           49 |                   0 |                       0 |                   127 |                            20 |                                   1     |                      4 |                   0.039 |                 0.037 |                   0.101 |                0.038 |                       0.038 |              0.775 |                0.959 |                  5 |
|       2   |                 5 |                    16 |               0 |                   0.145 |              0.999 |                       3 |       41 |        65 |           46 |                   0 |                       3 |                   131 |                            16 |                                   1     |                      4 |                   0.031 |                 0.029 |                   0.086 |                0.05  |                       0.03  |              0.822 |                0.967 |                  4 |
|       2.5 |                 3 |                    27 |               0 |                   0.211 |              0.997 |                       2 |       41 |        60 |           51 |                   2 |                       0 |                   115 |                            32 |                                   1     |                      4 |                   0.035 |                 0.02  |                   0.098 |                0.026 |                       0.034 |              0.736 |                0.658 |                  4 |
|       2.5 |                 4 |                    22 |               0 |                   0.178 |              1     |                       0 |       41 |        62 |           49 |                   0 |                       0 |                   125 |                            22 |                                   0.909 |                      4 |                   0.04  |                 0.032 |                   0.097 |                0.035 |                       0.038 |              0.778 |                0.957 |                  5 |
|       2.5 |                 5 |                    18 |               0 |                   0.145 |              0.999 |                       3 |       41 |        65 |           46 |                   0 |                       3 |                   128 |                            19 |                                   0.895 |                      4 |                   0.031 |                 0.024 |                   0.086 |                0.04  |                       0.03  |              0.964 |                0.962 |                  4 |
|       3   |                 3 |                    27 |               0 |                   0.211 |              0.997 |                       2 |       41 |        60 |           51 |                   2 |                       0 |                   115 |                            32 |                                   1     |                      4 |                   0.035 |                 0.027 |                   0.108 |                0.031 |                       0.034 |              0.73  |                0.649 |                  4 |
|       3   |                 4 |                    23 |               0 |                   0.184 |              0.999 |                       0 |       41 |        62 |           49 |                   0 |                       0 |                   124 |                            23 |                                   1     |                      4 |                   0.04  |                 0.036 |                   0.116 |                0.036 |                       0.039 |              0.778 |                0.953 |                  5 |
|       3   |                 5 |                    19 |               0 |                   0.151 |              0.998 |                       2 |       41 |        64 |           47 |                   0 |                       2 |                   126 |                            21 |                                   1     |                      4 |                   0.024 |                 0.033 |                   0.111 |                0.033 |                       0.023 |              0.965 |                0.951 |                  3 |