"""Point-in-time information sets for the back-test.

A cohort is scored AS OF 30 June of year Y (a common date for every company), using only what a credit
analyst could have read by then:
  * fiscal-year statements whose year ended at least `fy_lag_days` (90) before the as-of date. SEBI LODR
    gives listed companies 60 days after year-end for audited annual results, so March year-ends are in.
  * quarterly results whose quarter ended at least `q_lag_days` (45) before the as-of date.
  * half-year balance sheets dated at least `q_lag_days` before the as-of date.
  * no TTM columns and no market snapshot (they are "today" numbers).

LOOK-AHEAD RISKS THIS DOES NOT REMOVE (reported in the validation report):
  * Restatements: Screener shows the latest reported figure for every past year, not the figure first
    published (re-stated comparatives, Ind AS transition in FY2017, mergers / demergers). No vintage data.
  * Universe: today's Nifty 200 constituents (survivorship); case studies partly offset this.
  * Basis choice (consolidated vs standalone) is made from today's pages.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def as_of(year: int) -> str:
    return f"{year}-06-30"


def truncate(cl: pd.DataFrame, asof: str, fy_lag_days: int = 90, q_lag_days: int = 45) -> pd.DataFrame:
    a = date.fromisoformat(asof)
    fy_cut = (a - timedelta(days=fy_lag_days)).isoformat()
    q_cut = (a - timedelta(days=q_lag_days)).isoformat()
    pe = cl["period_end"].fillna("")
    keep = ((cl.frequency == "FY") & (pe != "") & (pe <= fy_cut)) | \
           ((cl.frequency == "Q") & (pe != "") & (pe <= q_cut)) | \
           ((cl.frequency == "interim") & (pe != "") & (pe <= q_cut))
    return cl[keep].copy()
