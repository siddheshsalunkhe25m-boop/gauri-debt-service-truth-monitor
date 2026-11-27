"""Point-in-time back-test of the Repayment Truth Score.

For each cohort year Y (as of 30 June Y) every company is scored with `run_rts` on data truncated to what was
public then (pit.truncate), and its forward outcomes are measured afterwards (outcomes.py).

IMPORTANT LIMITATION: Screener's public pages carry only the last 13 quarters (Sep 2023 onwards), so the
Breach Clock cannot be computed for any cohort whose outcomes are already observable. The back-test therefore
validates RTS-3 = FA-DSCR + Minsky + refinancing (Breach Clock weight set to 0, others re-normalised).
The Breach Clock gets its own single-cohort out-of-sample test (breach_clock_test).
"""
from __future__ import annotations

import zlib
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd

from dstm_rts.breach import breach_clock
from dstm_rts.config import RTSConfig
from dstm_rts.engine import run_rts

from .outcomes import outcomes
from .pit import as_of, truncate

OUTCOMES = ["any_new_event", "any_event", "icr_fall", "new_loss", "loss", "drawdown50", "icr_below_2"]


# ------------------------------------------------------------------ scoring one cohort
def benchmarks(annual: pd.DataFrame, scores: pd.DataFrame, cfg: RTSConfig) -> pd.DataFrame:
    """Plain (non-forensic) comparators over the same window: reported-CFO DSCR, ICR, Debt/EBITDA."""
    rows = []
    for s in scores.itertuples(index=False):
        g = annual[annual.symbol == s.symbol]
        if g.empty or pd.isna(s.latest_fy):
            continue
        last = g[g.period_end == s.latest_fy].iloc[0]
        win = g[(g.fy_idx > last.fy_idx - cfg.refi_years) & (g.fy_idx <= last.fy_idx)]
        serv = (win["interest_paid"].fillna(0) + win["principal_repaid"].fillna(0))
        tot = serv.sum()
        # no debt service / no interest -> treated as very safe (same treatment as RTS gives debt-free firms),
        # so every risk score is compared on the same companies
        naive = win["cfo"].sum() / tot if tot >= cfg.min_debt_service else 99.0
        ip = last["interest_paid"]
        icr = last["ebitda"] / ip if pd.notna(ip) and ip > 0 else 999.0
        de = (last["total_borrowings"] / last["ebitda"]) if last["ebitda"] and last["ebitda"] > 0 else (
            np.inf if last["total_borrowings"] and last["total_borrowings"] > 0 else 0.0)
        rows.append({"symbol": s.symbol, "naive_dscr_3y": naive, "icr_asof_bench": icr, "debt_ebitda_asof": de})
    return pd.DataFrame(rows)


def score_cohort(cl: pd.DataFrame, year: int, cfg: RTSConfig, stale_months: int = 15) -> pd.DataFrame:
    asof = as_of(year)
    t = truncate(cl, asof)
    if t.empty:
        return pd.DataFrame()
    res = run_rts(t, cfg)
    s = res.scores
    if s.empty:
        return s
    cutoff = (date.fromisoformat(asof) - timedelta(days=int(30.5 * stale_months))).isoformat()
    s = s[s.latest_fy.notna() & (s.latest_fy >= cutoff)].copy()      # stale filers are not scored
    s = s.merge(benchmarks(res.annual, s, cfg), on="symbol", how="left")
    s["cohort"], s["asof"] = year, asof
    s["stressed_state"] = s.minsky_state.isin(["Speculative", "Ponzi"]).astype(int)
    s["migrated_down"] = (s.minsky_state.isin(["Speculative", "Ponzi"]) & (s.migration == "deteriorating")).astype(int)
    s["risk_rts"] = 100 - s["rts"]
    return s


def run_backtest(cl: pd.DataFrame, prices: pd.DataFrame, years, cfg: RTSConfig | None = None,
                 drop_breach: bool = True) -> pd.DataFrame:
    cfg = cfg or RTSConfig()
    if drop_breach:
        cfg = replace(cfg, w_breach=0.0)
    panel = []
    for y in years:
        s = score_cohort(cl, y, cfg)
        if s.empty:
            continue
        o = outcomes(cl, prices, s[["symbol", "latest_fy"]], s["asof"].iloc[0])
        panel.append(s.merge(o.drop(columns=["latest_fy"]), on=["symbol", "asof"], how="left"))
    return pd.concat(panel, ignore_index=True) if panel else pd.DataFrame()


# ------------------------------------------------------------------ leakage test
def leakage_check(cl: pd.DataFrame, year: int, cfg: RTSConfig, seed: int = 1) -> dict:
    """Scramble every value dated after the as-of information cut-off; the cohort's scores must not move."""
    asof = as_of(year)
    rng = np.random.default_rng(seed)
    allowed = truncate(cl, asof).index
    future = cl.index.difference(allowed)
    cl2 = cl.copy()
    cl2.loc[future, "value"] = cl2.loc[future, "value"].to_numpy() * rng.uniform(-3, 3, len(future))
    a = score_cohort(cl, year, cfg).set_index("symbol")
    b = score_cohort(cl2, year, cfg).set_index("symbol")
    cols = ["rts", "fa_dscr_3y", "refi_dependence_3y", "s_minsky"]
    diff = (a[cols] - b.loc[a.index, cols]).abs().max().max() if len(a) else 0.0
    same_class = bool((a["rts_class"] == b.loc[a.index, "rts_class"]).all()) if len(a) else True
    return {"cohort": year, "n_scored": len(a), "n_future_values_scrambled": len(future),
            "max_abs_score_change": float(np.nan_to_num(diff)), "classes_identical": same_class,
            "passed": bool(np.nan_to_num(diff) < 1e-9 and same_class)}


# ------------------------------------------------------------------ statistics
def auc(y, s) -> float:
    """Probability a random event case has a higher risk score than a random non-event (ties count half)."""
    d = pd.DataFrame({"y": y, "s": s}).dropna()
    d = d[np.isfinite(d.s) | (d.s == np.inf)]
    n1, n0 = int((d.y == 1).sum()), int((d.y == 0).sum())
    if n1 == 0 or n0 == 0:
        return np.nan
    r = d.s.rank(method="average")
    return float((r[d.y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


RISK_SCORES = {
    "RTS-3 (100 - score)": ("risk_rts", 1),
    "Naive DSCR (reported CFO)": ("naive_dscr_3y", -1),
    "Interest cover (EBITDA/interest)": ("icr_asof_bench", -1),
    "Debt / EBITDA": ("debt_ebitda_asof", 1),
}


def auc_table(panel: pd.DataFrame, outcome: str, n_boot: int = 1000, seed: int = 7) -> pd.DataFrame:
    """Pooled AUC per risk score with a company-cluster bootstrap CI, and the RTS-minus-benchmark gap."""
    d = panel[panel[outcome].notna()].copy()
    for name, (col, sign) in RISK_SCORES.items():
        d[name] = sign * d[col].replace([np.inf, -np.inf], [1e9, -1e9])
    syms = d.symbol.unique()
    groups = {s: g.index.to_numpy() for s, g in d.groupby("symbol")}
    rng = np.random.default_rng(seed)
    point = {n: auc(d[outcome], d[n]) for n in RISK_SCORES}
    boots = {n: [] for n in RISK_SCORES}
    for _ in range(n_boot):
        pick = rng.choice(syms, size=len(syms), replace=True)
        idx = np.concatenate([groups[s] for s in pick])
        b = d.loc[idx]
        for n in RISK_SCORES:
            boots[n].append(auc(b[outcome], b[n]))
    rows = []
    base = np.array(boots["RTS-3 (100 - score)"])
    for n in RISK_SCORES:
        arr = np.array(boots[n])
        gap = base - arr
        rows.append({"outcome": outcome, "risk_score": n, "n_obs": int(d[n].notna().sum()),
                     "n_events": int(d.loc[d[n].notna(), outcome].sum()), "auc": point[n],
                     "auc_lo95": np.nanpercentile(arr, 2.5), "auc_hi95": np.nanpercentile(arr, 97.5),
                     "rts_minus_this_auc": point["RTS-3 (100 - score)"] - point[n] if n != "RTS-3 (100 - score)" else np.nan,
                     "gap_lo95": np.nanpercentile(gap, 2.5) if n != "RTS-3 (100 - score)" else np.nan,
                     "gap_hi95": np.nanpercentile(gap, 97.5) if n != "RTS-3 (100 - score)" else np.nan})
    return pd.DataFrame(rows)


def rate_table(panel: pd.DataFrame, by: str, outcome: str) -> pd.DataFrame:
    d = panel[panel[outcome].notna()]
    t = d.groupby(by)[outcome].agg(["count", "sum", "mean"]).rename(columns={"count": "n", "sum": "events", "mean": "rate"})
    t["outcome"] = outcome
    return t.reset_index()


def cohort_auc(panel: pd.DataFrame, outcome: str) -> pd.DataFrame:
    rows = []
    for y, g in panel.groupby("cohort"):
        rows.append({"cohort": y, "outcome": outcome, "n": int(g[outcome].notna().sum()),
                     "events": int(g[outcome].sum(skipna=True)), "auc_rts3": auc(g[outcome], g["risk_rts"]),
                     "auc_naive_dscr": auc(g[outcome], -g["naive_dscr_3y"])})
    return pd.DataFrame(rows)


def quintile_table(panel: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Event rate by RTS quintile within each cohort (Q1 = lowest score = riskiest), pooled."""
    d = panel[panel[outcome].notna() & panel["rts"].notna()].copy()
    d["q"] = d.groupby("cohort")["rts"].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False) + 1
                                                  if len(x) >= 5 else np.nan)
    t = d.groupby("q")[outcome].agg(["count", "mean"]).rename(columns={"count": "n", "mean": "rate"}).reset_index()
    t["outcome"] = outcome
    return t


# ------------------------------------------------------------------ Breach Clock single-cohort test
def breach_clock_test(cl: pd.DataFrame, cfg: RTSConfig, asof: str = "2025-11-15",
                      horizon_end: str = "2026-09-30") -> pd.DataFrame:
    """Forecast as of `asof` (quarters to Sep 2025, debt from the last published balance sheet) against the
    realised covenant test in the next four quarters (actual TTM EBITDA / interest; actual debt from the
    latest balance sheet published before each quarter end, FY Mar 2026 or the Sep 2026 half-year)."""
    prim = cl[cl.basis_role == "primary"]
    q = prim[(prim.frequency == "Q") & prim.field.isin(["ebitda", "interest_expense"])]
    qw = q.pivot_table(index=["symbol", "period_end"], columns="field", values="value", aggfunc="first").reset_index()
    debt = prim[prim.frequency.isin(["FY", "interim"]) & (prim.field == "total_borrowings")][["symbol", "period_end", "value"]]
    t = truncate(cl, asof)
    tq = t[(t.basis_role == "primary") & (t.frequency == "Q")]
    tdebt = t[(t.basis_role == "primary") & t.frequency.isin(["FY", "interim"]) & (t.field == "total_borrowings")]
    rows = []
    for sym, g in qw.groupby("symbol"):
        g = g.dropna(subset=["ebitda", "interest_expense"]).sort_values("period_end")
        hist = g[g.period_end <= tq.period_end.max()] if len(tq) else g.iloc[:0]
        if len(hist) == 0:
            continue
        fut = g[(g.period_end > hist.period_end.max()) & (g.period_end <= horizon_end)]
        d_hist = tdebt[tdebt.symbol == sym].sort_values("period_end")
        if len(hist) < 4 or d_hist.empty or len(fut) < 4:
            continue
        d0, dd0 = float(d_hist.value.iloc[-1]), d_hist.period_end.iloc[-1]
        res = breach_clock(sym, hist, d0, dd0, cfg, seed_offset=zlib.crc32(sym.encode()) % 100000)
        # realised: rolling TTM over actual quarters, debt = latest balance sheet dated <= that quarter end
        allq = g[g.period_end <= horizon_end]
        dsym = debt[debt.symbol == sym].sort_values("period_end")
        realised, first_q = 0, None
        for k, qe in enumerate(fut.period_end.head(4), 1):
            w = allq[allq.period_end <= qe].tail(4)
            te, ti = w.ebitda.sum(), w.interest_expense.sum()
            dv = dsym[dsym.period_end <= qe]
            dq = float(dv.value.iloc[-1]) if len(dv) else d0
            icr = te / ti if ti > 0 else np.inf
            de = dq / te if te > 0 else np.inf
            if icr < cfg.icr_min or (dq > 0 and de > cfg.debt_ebitda_max):
                realised, first_q = 1, k
                break
        rows.append({"symbol": sym, "asof": asof, "n_hist_q": len(hist), "debt_asof": d0, "debt_date": dd0,
                     "status": res.status, "breach_at_asof": int(res.breach_now), "p_base": res.p_breach_base,
                     "p_stress": res.p_breach_stress, "realised_breach_4q": realised, "first_breach_q": first_q})
    return pd.DataFrame(rows)


def calibration(bt: pd.DataFrame) -> dict:
    d = bt[(bt.status == "ok") & bt.p_base.notna()]
    out = {"n_simulated": len(d), "n_already_in_breach": int((bt.status == "already_in_breach").sum()),
           "persistence_already_in_breach": float(bt.loc[bt.status == "already_in_breach", "realised_breach_4q"].mean())
           if (bt.status == "already_in_breach").any() else np.nan,
           "insufficient": int((bt.status == "insufficient_quarters").sum())}
    if len(d):
        out.update({"realised_rate": float(d.realised_breach_4q.mean()), "mean_p_base": float(d.p_base.mean()),
                    "mean_p_stress": float(d.p_stress.mean()),
                    "brier_base": float(((d.p_base - d.realised_breach_4q) ** 2).mean()),
                    "brier_climatology": float(((d.realised_breach_4q.mean() - d.realised_breach_4q) ** 2).mean()),
                    "auc_base": auc(d.realised_breach_4q, d.p_base), "auc_stress": auc(d.realised_breach_4q, d.p_stress),
                    "n_events": int(d.realised_breach_4q.sum())})
    return out
