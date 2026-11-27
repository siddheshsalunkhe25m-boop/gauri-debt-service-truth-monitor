"""Peer benchmarking: a company's metrics vs its NSE-industry peers and the whole universe.

Percentiles are "better-than" percentiles: 100 = best in the group whatever the metric's direction
(e.g. a LOW breach probability is good). Mid-rank method, so ties share a percentile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# metric column -> (label, higher_is_better, format)
METRICS = {
    "rts": ("RTS (0-100)", True, "{:.0f}"),
    "fa_dscr_3y": ("FA-DSCR, 3-yr", True, "{:.2f}x"),
    "reported_dscr_3y": ("Reported DSCR, 3-yr", True, "{:.2f}x"),
    "fa_dscr_maint_3y": ("FA-DSCR after maint. capex", True, "{:.2f}x"),
    "refi_dependence_3y": ("Refinancing dependence", False, "{:.0%}"),
    "p_breach_base": ("P(breach, 4q) baseline", False, "{:.0%}"),
    "breach_icr_now": ("Interest cover now (TTM)", True, "{:.1f}x"),
    "breach_debt_ebitda_now": ("Debt / EBITDA now (TTM)", False, "{:.1f}x"),
    "stretch_share_of_cfo": ("Payables stretch / CFO", False, "{:.0%}"),
}


def better_pct(values: pd.Series, x: float, higher_is_better: bool) -> float:
    v = values.dropna()
    if pd.isna(x) or len(v) < 2:
        return np.nan
    if not higher_is_better:
        v, x = -v, -x
    below = (v < x).sum()
    equal = (v == x).sum()
    return float(100 * (below + 0.5 * equal) / len(v))


def benchmark(scores: pd.DataFrame, symbol: str, sector_col: str = "sector") -> pd.DataFrame:
    row = scores[scores.symbol == symbol]
    if row.empty:
        return pd.DataFrame()
    row = row.iloc[0]
    peers = scores[scores[sector_col] == row[sector_col]]
    out = []
    for col, (label, hib, fmt) in METRICS.items():
        if col not in scores:
            continue
        x = row[col]
        out.append({"metric": col, "label": label, "higher_is_better": hib, "fmt": fmt, "value": x,
                    "sector_median": peers[col].replace([np.inf, -np.inf], np.nan).median(),
                    "universe_median": scores[col].replace([np.inf, -np.inf], np.nan).median(),
                    "sector_pct": better_pct(peers[col], x, hib) if pd.notna(x) else np.nan,
                    "universe_pct": better_pct(scores[col], x, hib) if pd.notna(x) else np.nan,
                    "n_sector": int(peers[col].notna().sum()), "n_universe": int(scores[col].notna().sum())})
    return pd.DataFrame(out)
