"""Repayment Truth Score (0-100, higher = repayment capacity is more real) and Safe / Watch / Escalate.

RTS = w_dscr x S_dscr + w_minsky x S_minsky + w_refi x S_refi + w_breach x S_breach   (weights re-normalised
over the components that could be computed; missing components are listed in `missing_components`).

Sub-scores (0-100)
  S_dscr    piecewise-linear in the 3-year POOLED FA-DSCR (sum CFADS / sum debt service, robust to a lumpy
            repayment year): 0.8x->0, 1.0x->30, 1.25x->55, 1.5x->70, 2.0x->85, 3.0x->100. No debt service -> 100.
  S_minsky  0.75 x state (Hedge 100 / Speculative 50 / Ponzi 0) + 0.25 x migration (improving 100 / stable 50 /
            deteriorating 0); state only if there is no prior history.
  S_refi    100 x (1 - min(1, 3-yr pooled new borrowing / debt service)).
  S_breach  100 x (1 - (0.6 P_base + 0.4 P_stress)), P = probability of a covenant breach within 4 quarters.

Class: Safe >= 70, Watch >= 45, else Escalate; then overrides can only make the class WORSE:
  Escalate  already in covenant breach on actual TTM figures; P_base >= 50%; latest year Ponzi (unless improving).
  Watch     P_base >= 20%; Ponzi but improving; Speculative and deteriorating; FA-DSCR after maintenance
            capex < 1.0x; refinancing dependence > 75%; payables stretch > 10% of reported CFO.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RTSConfig

CLASS_ORDER = {"Safe": 0, "Watch": 1, "Escalate": 2}


def interp(x: float, points: list) -> float:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return float(np.interp(x, xs, ys))          # flat beyond the end points


def _pooled(num, den, min_den):
    num, den = np.nansum(num), np.nansum(den)
    return num / den if den >= min_den else np.nan


def company_scores(annual: pd.DataFrame, breach: pd.DataFrame, cfg: RTSConfig) -> pd.DataFrame:
    w = cfg.weights
    bmap = breach.set_index("symbol") if len(breach) else pd.DataFrame()
    rows = []
    for sym, g in annual.groupby("symbol", sort=True):
        g = g.sort_values("period_end")
        valid = g[g["minsky_state"].notna()]
        r = {"symbol": sym}
        reasons, triggers = [], []
        if valid.empty:
            r.update({"latest_fy": None, "rts": np.nan, "rts_class": "Insufficient data",
                      "reasons": "no fiscal year with both cash flow and debt-service data", "missing_components": "all"})
            rows.append(r)
            continue
        last = valid.iloc[-1].copy()
        last["migration"] = last["migration"] if isinstance(last["migration"], str) else None
        win = valid[valid["fy_idx"] > last["fy_idx"] - cfg.refi_years]   # scored years among the last N fiscal years
        serv = win[~win["no_debt_service"]]
        r["latest_fy"] = last["period_end"]
        r["latest_fy_label"] = last["period_label"]
        r["fy_window"] = f"{win['period_end'].iloc[0]} .. {win['period_end'].iloc[-1]}"
        # ---------------------------------------------------------------- FA-DSCR
        r["fa_dscr_latest"] = last["fa_dscr"]
        r["fa_dscr_maint_latest"] = last["fa_dscr_after_maint"]
        r["fa_dscr_3y"] = _pooled(serv["cfads"], serv["debt_service"], cfg.min_debt_service)
        r["fa_dscr_maint_3y"] = _pooled(serv["cfads"] - serv["depreciation"].fillna(0), serv["debt_service"], cfg.min_debt_service)
        rs = win[win["reported_service"] >= cfg.min_debt_service]
        r["reported_dscr_3y"] = _pooled(rs["cfo"], rs["reported_service"], cfg.min_debt_service) if len(rs) else np.nan
        r["reported_dscr_latest"] = last.get("reported_dscr", np.nan)
        no_service = serv.empty or np.isnan(r["fa_dscr_3y"])
        r["s_dscr"] = 100.0 if no_service else interp(r["fa_dscr_3y"], cfg.dscr_points)
        # ---------------------------------------------------------------- Minsky
        r["minsky_state"] = last["minsky_state"]
        r["migration"] = last["migration"]
        st = cfg.minsky_state_score[last["minsky_state"]]
        if last["migration"]:
            r["s_minsky"] = cfg.minsky_state_weight * st + (1 - cfg.minsky_state_weight) * cfg.migration_score[last["migration"]]
        else:
            r["s_minsky"] = float(st)
        r["minsky_path"] = " > ".join(f"{p[:4]}:{s[0]}" for p, s in zip(win["period_end"], win["minsky_state"]))
        # ---------------------------------------------------------------- refinancing dependence
        r["refi_dependence_3y"] = (0.0 if no_service else
                                   _pooled(serv["borrowings_raised"], serv["debt_service"], cfg.min_debt_service))
        r["s_refi"] = np.nan if np.isnan(r["refi_dependence_3y"]) else 100 * (1 - min(1.0, max(0.0, r["refi_dependence_3y"])))
        # ---------------------------------------------------------------- Breach Clock
        b = bmap.loc[sym] if sym in bmap.index else None
        for k in ["p_breach_base", "p_breach_stress", "median_q_base", "median_q_stress", "icr_now",
                  "debt_ebitda_now", "breach_now", "status", "n_quarters", "debt", "debt_date"]:
            r[("breach_" + k) if not k.startswith(("p_", "median", "breach")) else k] = (b[k] if b is not None else np.nan)
        pb, ps = r["p_breach_base"], r["p_breach_stress"]
        r["s_breach"] = np.nan if b is None or pd.isna(pb) else 100 * (1 - (cfg.breach_base_weight * pb + (1 - cfg.breach_base_weight) * ps))
        # ---------------------------------------------------------------- RTS
        comps = {"dscr": r["s_dscr"], "minsky": r["s_minsky"], "refi": r["s_refi"], "breach": r["s_breach"]}
        avail = {k: v for k, v in comps.items() if v is not None and not pd.isna(v)}
        wsum = sum(w[k] for k in avail)
        r["rts"] = sum(w[k] * v for k, v in avail.items()) / wsum if wsum else np.nan
        r["missing_components"] = ", ".join(k for k in comps if k not in avail)
        cls = "Safe" if r["rts"] >= cfg.safe_min else ("Watch" if r["rts"] >= cfg.watch_min else "Escalate")
        r["score_class"] = cls
        # ---------------------------------------------------------------- reasons & overrides
        stretch_share = (last["payables_stretch"] / abs(last["cfo"])) if last["cfo"] else np.nan
        r["payables_stretch_latest"] = last["payables_stretch"]
        r["stretch_share_of_cfo"] = stretch_share
        r["cfo_latest"], r["cfo_adj_latest"] = last["cfo"], last["cfo_adj"]
        r["interest_location_latest"] = last["interest_location"]

        def trig(level, text):
            triggers.append((level, text))

        if b is not None and bool(b["breach_now"]) is True:
            trig("Escalate", f"already outside covenant on actual TTM ({b['breach_now_reason']})")
        elif not pd.isna(pb) and pb >= cfg.escalate_p_breach:
            trig("Escalate", f"{pb:.0%} probability of covenant breach within {cfg.breach_window_q} quarters (baseline)")
        elif not pd.isna(pb) and pb >= cfg.watch_p_breach:
            trig("Watch", f"{pb:.0%} probability of covenant breach within {cfg.breach_window_q} quarters (baseline)")
        if last["minsky_state"] == "Ponzi":
            if last["migration"] == "improving":
                trig("Watch", "Ponzi in latest year (cash after adjustments does not cover interest) but improving")
            else:
                trig("Escalate", "Ponzi in latest year: adjusted operating cash does not cover interest paid")
        if last["minsky_state"] == "Speculative" and last["migration"] == "deteriorating":
            trig("Watch", "Speculative and deteriorating: covers interest but not principal, worse than its 3-yr history")
        if not no_service and not pd.isna(r["fa_dscr_maint_3y"]) and r["fa_dscr_maint_3y"] < 1.0:
            trig("Watch", f"FA-DSCR after maintenance capex (depreciation proxy) {r['fa_dscr_maint_3y']:.2f}x < 1.0x")
        if not pd.isna(r["refi_dependence_3y"]) and r["refi_dependence_3y"] > cfg.watch_refi_dependence:
            trig("Watch", f"{min(r['refi_dependence_3y'], 9.99):.0%} of debt service funded by new borrowing (3-yr)")
        if not pd.isna(stretch_share) and stretch_share > cfg.watch_stretch_share:
            trig("Watch", f"payables stretched Rs {last['payables_stretch']:,.0f} Cr beyond own norm "
                          f"= {stretch_share:.0%} of reported CFO")
        final = cls
        for lvl, _ in triggers:
            if CLASS_ORDER[lvl] > CLASS_ORDER[final]:
                final = lvl
        r["rts_class"] = final
        # driver sentences, worst component first
        if no_service:
            reasons.append("negligible debt service in the window: DSCR not binding")
        else:
            reasons.append(f"FA-DSCR {r['fa_dscr_3y']:.2f}x (3-yr pooled; latest {last['fa_dscr']:.2f}x)")
        reasons.append(f"Minsky {last['minsky_state']}" + (f", {last['migration']}" if last["migration"] else ""))
        if not pd.isna(r["refi_dependence_3y"]):
            reasons.append(f"refinancing dependence {min(r['refi_dependence_3y'], 9.99):.0%}")
        if not pd.isna(pb):
            mq = r["median_q_base"]
            reasons.append(f"breach P(4q) {pb:.0%} base / {ps:.0%} stress; median quarters to breach "
                           f"{'>' + str(cfg.horizon_q) if mq is None or pd.isna(mq) else int(mq)}")
        elif b is not None:
            reasons.append(f"Breach Clock not run ({b['status']})")
        r["triggers"] = " | ".join(f"[{l}] {t}" for l, t in triggers)
        r["reasons"] = "; ".join(reasons)
        rows.append(r)
    return pd.DataFrame(rows)
