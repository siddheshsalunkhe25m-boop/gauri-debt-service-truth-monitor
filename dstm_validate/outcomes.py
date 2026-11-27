"""Forward outcomes for a cohort scored as of `asof` (only used as the thing to predict, never as input).

  icr_fall     interest cover (annual EBITDA / P&L interest) in either of the next two fiscal years falls
               below 60% of its as-of level. Defined only where interest >= Rs 1 Cr and as-of ICR <= 25x
               (debt-free companies' ICR is noise).
  icr_below_2  ICR drops below 2.0x in either of the next two fiscal years (from >= 2.0x).
  loss         a net loss in either of the next two fiscal years.
  drawdown50   share price falls more than 50% from its running peak within 24 months after the as-of date
               (weekly closes, price only). Needs >= 75% of the weeks.
  any_event    any of icr_fall, loss, drawdown50.
  new_loss     a loss in either of the next two years for a company PROFITABLE at the as-of year (excludes
               companies already loss-making, whose "prediction" is mere persistence).
  any_new_event  icr_fall or new_loss or drawdown50 - the stricter headline test.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


def annual_pl(cl: pd.DataFrame) -> pd.DataFrame:
    d = cl[(cl.basis_role == "primary") & (cl.frequency == "FY") & cl.field.isin(["ebitda", "interest_expense", "net_profit"])]
    w = d.pivot_table(index=["symbol", "period_end"], columns="field", values="value", aggfunc="first").reset_index()
    for f in ["ebitda", "interest_expense", "net_profit"]:
        if f not in w:
            w[f] = np.nan
    w["icr"] = np.where(w["interest_expense"] > 0, w["ebitda"] / w["interest_expense"].where(w["interest_expense"] > 0), np.nan)
    return w.sort_values(["symbol", "period_end"])


def max_drawdown(prices: pd.DataFrame, start: str, days: int = 730, min_coverage: float = 0.75):
    """prices: one symbol's rows (date, close). Returns (mdd, n_weeks) or (nan, n) when coverage is short."""
    end = (date.fromisoformat(start) + timedelta(days=days)).isoformat()
    p = prices[(prices.date > start) & (prices.date <= end)].sort_values("date")["close"].to_numpy(float)
    if len(p) < min_coverage * days / 7:
        return np.nan, len(p)
    peak = np.maximum.accumulate(p)
    return float(np.max(1 - p / peak)), len(p)


def outcomes(cl: pd.DataFrame, prices: pd.DataFrame, scored: pd.DataFrame, asof: str) -> pd.DataFrame:
    """scored: rows with symbol and latest_fy (the last FY in the information set)."""
    pl = annual_pl(cl)
    px = prices.groupby("symbol") if len(prices) else None
    out = []
    for r in scored.itertuples(index=False):
        g = pl[pl.symbol == r.symbol]
        base = g[g.period_end == r.latest_fy]
        hi = (date.fromisoformat(r.latest_fy) + timedelta(days=2 * 365 + 31)).isoformat()
        fut = g[(g.period_end > r.latest_fy) & (g.period_end <= hi)]
        o = {"symbol": r.symbol, "asof": asof, "latest_fy": r.latest_fy, "n_future_fy": len(fut)}
        if len(base) and len(fut):
            b = base.iloc[0]
            icr0, int0 = b["icr"], b["interest_expense"]
            o["icr_asof"] = icr0
            fut_icr = np.where(fut["interest_expense"] > 0, fut["ebitda"] / fut["interest_expense"].where(fut["interest_expense"] > 0), np.inf)
            if pd.notna(icr0) and int0 >= 1 and icr0 <= 25:
                o["icr_fall"] = int(np.nanmin(fut_icr) < 0.6 * icr0)
            if pd.notna(icr0) and icr0 >= 2 and int0 >= 1:
                o["icr_below_2"] = int(np.nanmin(fut_icr) < 2.0)
            if fut["net_profit"].notna().any():
                o["loss"] = int((fut["net_profit"] < 0).any())
                if pd.notna(b["net_profit"]) and b["net_profit"] > 0:
                    o["new_loss"] = o["loss"]
        if px is not None and r.symbol in px.groups:
            mdd, n = max_drawdown(px.get_group(r.symbol), asof)
            o["max_drawdown_24m"] = mdd
            o["price_weeks"] = n
            if pd.notna(mdd):
                o["drawdown50"] = int(mdd > 0.5)
        evs = [o.get(k) for k in ("icr_fall", "loss", "drawdown50") if o.get(k) is not None]
        o["any_event"] = int(any(evs)) if evs else np.nan
        nevs = [o.get(k) for k in ("icr_fall", "new_loss", "drawdown50") if o.get(k) is not None]
        o["any_new_event"] = int(any(nevs)) if nevs else np.nan
        out.append(o)
    df = pd.DataFrame(out)
    for c in ["icr_fall", "icr_below_2", "loss", "new_loss", "drawdown50", "max_drawdown_24m", "icr_asof", "any_new_event"]:
        if c not in df:
            df[c] = np.nan
    return df
