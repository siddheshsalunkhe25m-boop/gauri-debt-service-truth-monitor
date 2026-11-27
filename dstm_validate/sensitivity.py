"""Sensitivity of RTS to weights, covenant thresholds and the judgement calls (proxies).

Two lenses per scenario:
  * back-test: pooled AUC of RTS-3 for each outcome (does the ranking power survive the change?)
  * today:     class changes and Spearman rank correlation vs the base case on the latest data (full RTS).
This is a robustness check, NOT a search for the best weights: choosing weights by back-test AUC would be
in-sample fitting and would overstate performance.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from dstm_rts.config import RTSConfig
from dstm_rts.engine import run_rts

from .backtest import auc, breach_clock_test, calibration, run_backtest

WEIGHT_SCENARIOS = {
    "base 35/25/20/20": dict(w_dscr=0.35, w_minsky=0.25, w_refi=0.20, w_breach=0.20),
    "equal 25 each": dict(w_dscr=0.25, w_minsky=0.25, w_refi=0.25, w_breach=0.25),
    "DSCR-heavy 50/20/15/15": dict(w_dscr=0.50, w_minsky=0.20, w_refi=0.15, w_breach=0.15),
    "Minsky-heavy 25/40/15/20": dict(w_dscr=0.25, w_minsky=0.40, w_refi=0.15, w_breach=0.20),
    "Breach-heavy 25/20/15/40": dict(w_dscr=0.25, w_minsky=0.20, w_refi=0.15, w_breach=0.40),
    "drop FA-DSCR": dict(w_dscr=0.0),
    "drop Minsky": dict(w_minsky=0.0),
    "drop refinancing": dict(w_refi=0.0),
    "drop Breach Clock": dict(w_breach=0.0),
}

JUDGEMENT_SCENARIOS = {
    "interest add-back: always (literal formula)": dict(interest_addback="always"),
    "leases excluded from repayments": dict(include_lease_payments=False),
    "non-core: all other income": dict(noncore_mode="all_other_income"),
    "non-core: none": dict(noncore_mode="none"),
    "exceptional gains not deducted": dict(deduct_exceptional_gains=False),
    "payables norm 5 years": dict(payables_norm_years=5),
    "class cut-offs 65/40": dict(safe_min=65.0, watch_min=40.0),
    "class cut-offs 75/50": dict(safe_min=75.0, watch_min=50.0),
}

COVENANT_GRID = [(icr, de) for icr in (1.5, 2.0, 2.5, 3.0) for de in (3.0, 4.0, 5.0)]
OUTS = ["any_new_event", "icr_fall", "new_loss", "drawdown50"]


def _today(cl, cfg):
    s = run_rts(cl, cfg).scores
    return s.set_index("symbol")


def _compare(base: pd.DataFrame, alt: pd.DataFrame) -> dict:
    common = base.index.intersection(alt.index)
    b, a = base.loc[common], alt.loc[common]
    ok = b.rts.notna() & a.rts.notna()
    rho = spearmanr(b.rts[ok], a.rts[ok]).statistic if ok.sum() > 2 else np.nan
    changed = int((b.rts_class != a.rts_class).sum())
    dist = a.rts_class.value_counts()
    return {"spearman_vs_base": rho, "class_changes_vs_base": changed,
            "n_safe": int(dist.get("Safe", 0)), "n_watch": int(dist.get("Watch", 0)), "n_escalate": int(dist.get("Escalate", 0)),
            "moved_to_escalate": int(((b.rts_class != "Escalate") & (a.rts_class == "Escalate")).sum()),
            "moved_out_of_escalate": int(((b.rts_class == "Escalate") & (a.rts_class != "Escalate")).sum())}


def scenario_table(cl, prices, years, base_cfg: RTSConfig, scenarios: dict, today_symbols=None) -> pd.DataFrame:
    today_cl = cl if today_symbols is None else cl[cl.symbol.isin(today_symbols)]
    base_today = _today(today_cl, base_cfg)
    rows = []
    for name, kw in scenarios.items():
        cfg = replace(base_cfg, **kw)
        panel = run_backtest(cl, prices, years, cfg) if years else pd.DataFrame()
        r = {"scenario": name}
        for o in OUTS:
            r[f"backtest_auc_{o}"] = auc(panel[o], panel["risk_rts"]) if len(panel) and o in panel else np.nan
        r.update(_compare(base_today, _today(today_cl, cfg)))
        rows.append(r)
    return pd.DataFrame(rows)


def covenant_table(cl, base_cfg: RTSConfig, today_symbols=None) -> pd.DataFrame:
    today_cl = cl if today_symbols is None else cl[cl.symbol.isin(today_symbols)]
    base_today = _today(today_cl, base_cfg)
    rows = []
    for icr, de in COVENANT_GRID:
        cfg = replace(base_cfg, icr_min=icr, debt_ebitda_max=de)
        res = run_rts(today_cl, cfg)
        s = res.scores.set_index("symbol")
        b = res.breach
        r = {"icr_min": icr, "debt_ebitda_max": de,
             "n_already_in_breach": int((b.status == "already_in_breach").sum()),
             "median_p_base": float(b.p_breach_base.median()), "share_p_base_ge_20pct": float((b.p_breach_base >= 0.2).mean())}
        r.update(_compare(base_today, s))
        cal = calibration(breach_clock_test(cl, cfg))
        r.update({f"bc_test_{k}": v for k, v in cal.items()})
        rows.append(r)
    return pd.DataFrame(rows)
