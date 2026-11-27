"""Breach Clock: Monte Carlo projection of covenant headroom from the last 13 quarters.

METHOD (and its proxies)
------------------------
* Inputs: quarterly EBITDA (Screener "Operating Profit", excludes other income) and quarterly interest
  (P&L finance cost, includes lease interest) for up to 13 quarters, and the latest reported debt.
* Seasonality is preserved by projecting each quarter from the SAME quarter one year earlier:
      EBITDA[t+h]   = EBITDA[t+h-4]   + dE*      interest[t+h] = max(0, interest[t+h-4] + dI*)
  where (dE*, dI*) is one year-on-year change pair drawn with replacement from the history (paired
  bootstrap keeps the link between EBITDA and interest moves). 13 quarters give 9 such pairs.
  Additive changes are used because EBITDA can be zero or negative.
* Covenant tests each projected quarter on trailing-twelve-month figures:
      ICR        = TTM EBITDA / TTM interest      breach if < icr_min (default 2.0x)
      Debt/EBITDA = debt / TTM EBITDA              breach if > debt_ebitda_max (default 4.0x) or TTM EBITDA <= 0
* DEBT IS HELD AT THE LATEST REPORTED LEVEL (FY or half-year balance sheet, whichever is later; gross
  borrowings incl. lease liabilities by default). Screener has no quarterly debt, so the clock does not
  model new borrowing or repayment - a known simplification.
* Baseline: bootstrap as above (the recent YoY pattern, including its trend, repeats).
  Stress: simulated EBITDA cut by `stress_ebitda_haircut`, interest raised by `stress_interest_uplift`,
  and (by default) the YoY changes de-meaned so no growth tailwind is assumed.
* Outputs: probability of a breach within 4 quarters, median quarters to first breach over a 12-quarter
  horizon (None when fewer than half the paths breach: reported as "> 12"), and whether the company is
  already in breach on its last actual TTM numbers.
* Fewer than 8 quarters (e.g. recent listings / demergers) -> not simulated (component missing).
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import RTSConfig


@dataclass
class BreachResult:
    symbol: str
    n_quarters: int
    last_quarter: Optional[str]
    debt: float
    debt_date: Optional[str]
    ttm_ebitda: float
    ttm_interest: float
    icr_now: float
    debt_ebitda_now: float
    breach_now: bool
    breach_now_reason: str
    p_breach_base: float
    p_breach_stress: float
    median_q_base: Optional[float]
    median_q_stress: Optional[float]
    status: str            # ok | already_in_breach | insufficient_quarters | no_debt_no_interest
    n_paths: int
    seed: int


def _ratios(ttm_e, ttm_i, debt):
    with np.errstate(divide="ignore", invalid="ignore"):
        icr = np.where(ttm_i > 0, ttm_e / np.where(ttm_i > 0, ttm_i, 1), np.inf)
        de = np.where(ttm_e > 0, debt / np.where(ttm_e > 0, ttm_e, 1), np.inf)
    return icr, de


def _breach(icr, de, cfg, debt):
    b = icr < cfg.icr_min
    if debt > 0:
        b = b | (de > cfg.debt_ebitda_max)
    return b


def simulate_paths(ebitda: np.ndarray, interest: np.ndarray, debt: float, cfg: RTSConfig, stress: bool,
                   rng: np.random.Generator):
    """Projected quarterly paths. Returns (E, I, ttm_icr, ttm_de, first_breach):
    E, I: (paths, n_hist + H) quarterly EBITDA / interest; ttm_icr, ttm_de: (paths, H) TTM covenant ratios
    for each projected quarter; first_breach: (paths,) first breach quarter 1..H, inf if none."""
    n = len(ebitda)
    dE = ebitda[4:] - ebitda[:-4]
    dI = interest[4:] - interest[:-4]
    if stress and cfg.stress_remove_drift:
        dE, dI = dE - dE.mean(), dI - dI.mean()
    H, P = cfg.horizon_q, cfg.n_paths
    E = np.empty((P, n + H))
    I = np.empty((P, n + H))
    E[:, :n], I[:, :n] = ebitda, interest
    draws = rng.integers(0, len(dE), size=(P, H))
    for h in range(H):
        t = n + h
        E[:, t] = E[:, t - 4] + dE[draws[:, h]]
        I[:, t] = np.maximum(I[:, t - 4] + dI[draws[:, h]], 0.0)
    if stress:                                      # shock applies to simulated quarters only
        sim = E[:, n:]
        E[:, n:] = np.where(sim > 0, sim * (1 - cfg.stress_ebitda_haircut), sim * (1 + cfg.stress_ebitda_haircut))
        I[:, n:] = I[:, n:] * (1 + cfg.stress_interest_uplift)
    first = np.full(P, np.inf)
    icr_all, de_all = np.empty((P, H)), np.empty((P, H))
    for h in range(1, H + 1):
        t = n + h - 1
        ttm_e = E[:, t - 3:t + 1].sum(axis=1)
        ttm_i = I[:, t - 3:t + 1].sum(axis=1)
        icr, de = _ratios(ttm_e, ttm_i, debt)
        icr_all[:, h - 1], de_all[:, h - 1] = icr, de
        b = _breach(icr, de, cfg, debt)
        first = np.where(np.isinf(first) & b, h, first)
    return E, I, icr_all, de_all, first


def simulate(ebitda: np.ndarray, interest: np.ndarray, debt: float, cfg: RTSConfig, stress: bool,
             rng: np.random.Generator) -> np.ndarray:
    """Return first-breach quarter (1..H) per path, np.inf if no breach within the horizon."""
    return simulate_paths(ebitda, interest, debt, cfg, stress, rng)[4]


def fan(symbol: str, q: pd.DataFrame, debt: float, cfg: RTSConfig, seed_offset: Optional[int] = None,
        quantiles=(0.05, 0.25, 0.5, 0.75, 0.95)) -> Optional[dict]:
    """Fan-chart data for one company: historic TTM ratios + quantiles of projected TTM ICR and Debt/EBITDA,
    baseline and stress. Uses the same seed and draw order as breach_clock(), so the fan and the reported
    probabilities come from the same simulated paths."""
    q = q.sort_values("period_end").dropna(subset=["ebitda", "interest_expense"]).tail(13)
    e, i = q["ebitda"].to_numpy(float), q["interest_expense"].to_numpy(float)
    n = len(e)
    if n - 4 < cfg.min_yoy_pairs:
        return None
    debt = float(debt) if debt is not None and not np.isnan(debt) else 0.0
    seed_offset = zlib.crc32(symbol.encode()) % 100000 if seed_offset is None else seed_offset
    rng = np.random.default_rng(cfg.seed + seed_offset)
    hist_end = list(q["period_end"])
    hist_icr, hist_de = [], []
    for k in range(3, n):
        te, ti = e[k - 3:k + 1].sum(), i[k - 3:k + 1].sum()
        hist_icr.append(te / ti if ti > 0 else np.inf)
        hist_de.append(debt / te if te > 0 else np.inf)
    last = pd.Timestamp(hist_end[-1])
    fut_end = [(last + pd.offsets.QuarterEnd(h)).strftime("%Y-%m-%d") for h in range(1, cfg.horizon_q + 1)]
    out = {"hist_end": hist_end[3:], "hist_icr": hist_icr, "hist_de": hist_de, "fut_end": fut_end,
           "quantiles": list(quantiles), "debt": debt}
    for name, stress in (("base", False), ("stress", True)):
        _, _, icr, de, first = simulate_paths(e, i, debt, cfg, stress, rng)
        big = 1e6                                                       # inf (no interest / EBITDA <= 0) -> large
        out[f"{name}_icr_q"] = np.quantile(np.where(np.isfinite(icr), icr, big), quantiles, axis=0)
        out[f"{name}_de_q"] = np.quantile(np.where(np.isfinite(de), de, big), quantiles, axis=0)
        out[f"{name}_p_breach_by_q"] = [(first <= h).mean() for h in range(1, cfg.horizon_q + 1)]
    return out


def _median_q(first: np.ndarray) -> Optional[float]:
    med = float(np.median(first))
    return None if np.isinf(med) else med


def breach_clock(symbol: str, q: pd.DataFrame, debt: float, debt_date: Optional[str], cfg: RTSConfig,
                 seed_offset: int = 0) -> BreachResult:
    """q: this company's quarters (period_end, ebitda, interest_expense), any order."""
    q = q.sort_values("period_end").dropna(subset=["ebitda", "interest_expense"]).tail(13)
    e, i = q["ebitda"].to_numpy(float), q["interest_expense"].to_numpy(float)
    n = len(e)
    last_q = q["period_end"].iloc[-1] if n else None
    debt = float(debt) if debt is not None and not np.isnan(debt) else 0.0
    base = dict(symbol=symbol, n_quarters=n, last_quarter=last_q, debt=debt, debt_date=debt_date,
                n_paths=cfg.n_paths, seed=cfg.seed + seed_offset)
    if n < 4:
        return BreachResult(**base, ttm_ebitda=np.nan, ttm_interest=np.nan, icr_now=np.nan, debt_ebitda_now=np.nan,
                            breach_now=False, breach_now_reason="", p_breach_base=np.nan, p_breach_stress=np.nan,
                            median_q_base=None, median_q_stress=None, status="insufficient_quarters")
    ttm_e, ttm_i = e[-4:].sum(), i[-4:].sum()
    icr_now, de_now = (float(x[0]) for x in _ratios(np.array([ttm_e]), np.array([ttm_i]), debt))
    b_now = bool(_breach(np.array([icr_now]), np.array([de_now]), cfg, debt)[0])
    reason = "; ".join(r for r, c in [(f"ICR {icr_now:.2f}x < {cfg.icr_min}x", icr_now < cfg.icr_min),
                                      (f"Debt/EBITDA {de_now:.2f}x > {cfg.debt_ebitda_max}x" if np.isfinite(de_now)
                                       else "TTM EBITDA <= 0", debt > 0 and de_now > cfg.debt_ebitda_max)] if c)
    common = dict(ttm_ebitda=float(ttm_e), ttm_interest=float(ttm_i), icr_now=icr_now, debt_ebitda_now=de_now,
                  breach_now=b_now, breach_now_reason=reason)
    if debt <= 0 and ttm_i <= 0:
        return BreachResult(**base, **common, p_breach_base=0.0, p_breach_stress=0.0, median_q_base=None,
                            median_q_stress=None, status="no_debt_no_interest")
    if b_now:
        return BreachResult(**base, **common, p_breach_base=1.0, p_breach_stress=1.0, median_q_base=0.0,
                            median_q_stress=0.0, status="already_in_breach")
    if n - 4 < cfg.min_yoy_pairs:
        return BreachResult(**base, **common, p_breach_base=np.nan, p_breach_stress=np.nan, median_q_base=None,
                            median_q_stress=None, status="insufficient_quarters")
    rng = np.random.default_rng(cfg.seed + seed_offset)
    fb = simulate(e, i, debt, cfg, False, rng)
    fs = simulate(e, i, debt, cfg, True, rng)
    w = cfg.breach_window_q
    return BreachResult(**base, **common, p_breach_base=float((fb <= w).mean()), p_breach_stress=float((fs <= w).mean()),
                        median_q_base=_median_q(fb), median_q_stress=_median_q(fs), status="ok")


def run_breach_clock(quarters: pd.DataFrame, debt: pd.DataFrame, cfg: RTSConfig) -> pd.DataFrame:
    debt_col = "total_borrowings"
    out = []
    dmap = debt.set_index("symbol") if len(debt) else pd.DataFrame()
    for sym, g in quarters.groupby("symbol", sort=True):
        d, dd = np.nan, None
        if sym in dmap.index:
            row = dmap.loc[sym]
            d = row[debt_col]
            if cfg.debt_measure == "net":
                c = row.get("cash_and_equivalents")
                d = d - (c if c is not None and not np.isnan(c) else 0.0)
            dd = row["debt_date"]
        # seed depends only on the symbol, so a company's result does not change with the universe
        out.append(breach_clock(sym, g, d, dd, cfg, seed_offset=zlib.crc32(sym.encode()) % 100000).__dict__)
    return pd.DataFrame(out)
