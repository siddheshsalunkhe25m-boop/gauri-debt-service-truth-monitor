"""Annual RTS metrics per company-year: forensic-adjusted CFO, FA-DSCR, Minsky state, refinancing dependence.

PROXIES AND JUDGEMENT CALLS (stated honestly; all switchable in RTSConfig)
---------------------------------------------------------------------------
1. Payables stretch. Screener gives no cost of goods sold for every company, so payable days are
   measured against OPERATING EXPENSES (Sales - Operating Profit = material + employee + other expenses):
       payable_days = trade_payables / opex_annualised x 365
   The company's own norm is the mean payable days of the previous 3 fiscal years (2 minimum). The
   stretch is the payables balance ABOVE that norm: max(0, payables - norm_days x opex/365). Only an
   increase is penalised; it is a balance-level excess, so a lasting stretch is deducted until the
   rolling norm catches up (at most 3 years).
2. Exceptional / non-core income. Screener's "Exceptional items" (pre-tax, from the Other Income
   breakdown) is deducted when positive. Non-core income is "Other income normal" minus interest and
   dividends received: under Ind AS 7 those two sit in investing cash flow, so only the remainder can
   be inside CFO. CFO under the indirect method already strips some non-cash gains (e.g. profit on sale
   of assets), so this adjustment is deliberately CONSERVATIVE and may over-penalise in some years.
3. Interest add-back. The textbook FA-DSCR adds interest paid back to CFO because CFO is "after
   interest". Most Indian companies report interest paid under FINANCING, so their CFO is already
   before interest and adding it back would double-count. Default "auto": add back only the interest
   actually deducted inside CFO (data layer: interest_paid_in_cfo). When the data layer had to fall back
   to P&L interest (no interest line in cash flow), the location is INFERRED: if "Other financing items"
   shows an outflow of at least 80% of P&L interest, interest is taken to be in financing (no add-back),
   otherwise it is assumed to be inside CFO (add back).
   Cash available for debt service:  CFADS = CFO_adj + interest add-back.
4. Repayment of borrowings is GROSS (Screener "Repayment of borrowings" + any "Redemption of
   debentures"-type line). Gross repayments include roll-overs of short-term / working-capital debt and
   commercial paper, so DSCR understates capacity for heavy roll-over users; the refinancing-dependence
   metric shows that side. Scheduled principal (current maturities of long-term debt) is not on Screener.
5. Lease payments. Under Ind AS 116 lease rent is outside EBITDA and CFO; the lease principal is paid in
   financing ("Financial liabilities" on Screener, used as the lease-payment proxy). It is added to
   repayments by default so lease-heavy borrowers (airlines, retail) are not flattered.
6. Maintenance capex is proxied by DEPRECIATION (no split of capex into maintenance / growth exists).
7. Minsky states use CFADS (= CFO_adj where interest is paid in financing, which is the usual case):
       Hedge        CFADS >= interest + repayments
       Speculative  interest <= CFADS < interest + repayments
       Ponzi        CFADS < interest
   A company with (almost) no debt service is Hedge ("no debt service").
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RTSConfig

STATE_ORD = {"Ponzi": 0, "Speculative": 1, "Hedge": 2}
ORD_STATE = {v: k for k, v in STATE_ORD.items()}


def _nz(x):
    return 0.0 if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def interest_location(row, cfg: RTSConfig) -> tuple[float, str]:
    """Interest already deducted inside CFO (Rs Cr) and how that was decided."""
    flag = row.get("interest_paid_flag") or ""
    ip = row.get("interest_paid")
    if ip is None or np.isnan(ip):
        return 0.0, "interest unknown"
    if flag == "interest_in_cfo":
        return float(ip), "interest paid inside CFO (cash-flow line)"
    if flag == "interest_split_cfo_cff":
        return _nz(row.get("interest_paid_in_cfo")), "interest split between CFO and CFF (cash-flow lines)"
    if flag == "fallback_pnl_interest":
        ofi = row.get("other_financing_items")
        if ofi is not None and not np.isnan(ofi) and -ofi >= cfg.fallback_other_financing_share * ip:
            return 0.0, "P&L interest used; inferred paid in financing ('Other financing items' outflow covers it)"
        return float(ip), "P&L interest used; inferred paid inside CFO (no financing line covers it)"
    return 0.0, "interest paid in financing (cash-flow line)"


def annual_metrics(panel: pd.DataFrame, cfg: RTSConfig) -> pd.DataFrame:
    """panel: output of inputs.annual_panel. Returns one row per symbol-FY with every intermediate step."""
    out = []
    for sym, g in panel.groupby("symbol", sort=True):
        g = g.sort_values("period_end").reset_index(drop=True)
        days_hist = []
        for i, r in g.iterrows():
            r = r.to_dict()
            m = {"symbol": sym, "period_end": r["period_end"], "period_label": r.get("period_label"),
                 "period_months": r.get("period_months") or 12}
            months = m["period_months"] or 12
            # ---- payables stretch ------------------------------------------------------------
            opex = r.get("operating_expenses")
            opex_ann = opex * 12.0 / months if opex is not None and not np.isnan(opex) else np.nan
            tp = r.get("trade_payables")
            days = tp / opex_ann * 365 if opex_ann and opex_ann > 0 and tp is not None and not np.isnan(tp) else np.nan
            prior = [d for d in days_hist[-cfg.payables_norm_years:] if not np.isnan(d)]
            norm = float(np.mean(prior)) if len(prior) >= cfg.payables_min_history else np.nan
            if np.isnan(days) or np.isnan(norm):
                stretch, stretch_note = 0.0, "no adjustment (insufficient payables history)" if np.isnan(norm) else "no adjustment (payables missing)"
            else:
                stretch = max(0.0, tp - norm * opex_ann / 365)
                stretch_note = f"payable days {days:.0f} vs own {len(prior)}-yr norm {norm:.0f}"
            days_hist.append(days)
            # ---- exceptional / non-core -------------------------------------------------------
            exc = r.get("exceptional_items")
            exc_gain = max(_nz(exc), 0.0) if cfg.deduct_exceptional_gains else 0.0
            oin = r.get("other_income_recurring")
            if oin is None or np.isnan(oin):        # fall back: total other income less exceptional
                oin = _nz(r.get("other_income")) - _nz(exc)
            if cfg.noncore_mode == "ex_investing_receipts":
                noncore = max(oin - _nz(r.get("interest_received")) - _nz(r.get("dividends_received")), 0.0)
            elif cfg.noncore_mode == "all_other_income":
                noncore = max(oin, 0.0)
            else:
                noncore = 0.0
            cfo = r.get("cfo")
            cfo_adj = cfo - stretch - exc_gain - noncore if cfo is not None and not np.isnan(cfo) else np.nan
            # ---- debt service -------------------------------------------------------------------
            ip = r.get("interest_paid")
            in_cfo, loc_note = interest_location(r, cfg)
            addback = {"auto": in_cfo, "always": _nz(ip), "never": 0.0}[cfg.interest_addback]
            cfads = cfo_adj + addback
            rep = r.get("principal_repaid")
            lease = _nz(r.get("financial_liabilities_paid")) if cfg.include_lease_payments else 0.0
            repayments = (rep + lease) if rep is not None and not np.isnan(rep) else np.nan
            service = _nz(ip) + repayments if not np.isnan(repayments) and ip is not None and not np.isnan(ip) else np.nan
            dep = r.get("depreciation")
            no_service = not np.isnan(service) and service < cfg.min_debt_service
            if np.isnan(service) or np.isnan(cfads):
                dscr = dscr_m = np.nan
                state = None
            elif no_service:
                dscr = dscr_m = np.nan
                state = "Hedge"
            else:
                dscr = cfads / service
                dscr_m = (cfads - _nz(dep)) / service
                state = "Hedge" if cfads >= service else ("Speculative" if cfads >= _nz(ip) else "Ponzi")
            raised = r.get("borrowings_raised")
            refi = (raised / service) if (not np.isnan(service) and not no_service and raised is not None
                                          and not np.isnan(raised)) else (0.0 if no_service else np.nan)
            # ---- reported DSCR: what an analyst sees with NO forensic adjustment -----------------
            #      reported CFO / (interest paid + borrowing repayments); no stretch, exceptional,
            #      non-core, interest add-back or lease adjustments
            rep_service = (_nz(ip) + rep) if rep is not None and not np.isnan(rep) and ip is not None and not np.isnan(ip) else np.nan
            reported_dscr = (cfo / rep_service if cfo is not None and not np.isnan(cfo) and not np.isnan(rep_service)
                             and rep_service >= cfg.min_debt_service else np.nan)
            # ---- diagnostics (not scored): Sessions 5-8 cash-quality checks ---------------------
            ta = r.get("total_assets")
            prev_ta = g.loc[i - 1, "total_assets"] if i > 0 else np.nan
            avg_ta = np.nanmean([ta, prev_ta]) if not (np.isnan(_nan(ta)) and np.isnan(_nan(prev_ta))) else np.nan
            np_ = r.get("net_profit")
            sloan = (np_ - cfo) / avg_ta if avg_ta and not np.isnan(avg_ta) and np_ is not None and cfo is not None else np.nan
            ebitda = r.get("ebitda")
            cce = cfo / ebitda if ebitda and ebitda > 0 and cfo is not None else np.nan
            m.update({
                "cfo": cfo, "trade_payables": tp, "operating_expenses": opex, "opex_annualised": opex_ann,
                "payable_days": days, "payable_days_norm": norm, "payables_stretch": stretch, "stretch_note": stretch_note,
                "exceptional_items": exc, "exceptional_gain_deducted": exc_gain, "other_income_recurring": oin,
                "interest_received": r.get("interest_received"), "dividends_received": r.get("dividends_received"),
                "noncore_income_deducted": noncore, "cfo_adj": cfo_adj,
                "interest_paid": ip, "interest_paid_flag": r.get("interest_paid_flag"), "interest_in_cfo": in_cfo,
                "interest_location": loc_note, "interest_addback": addback, "cfads": cfads,
                "principal_repaid": rep, "lease_payments": lease, "repayments": repayments, "debt_service": service,
                "no_debt_service": bool(no_service), "fa_dscr": dscr, "depreciation": dep, "fa_dscr_after_maint": dscr_m,
                "minsky_state": state, "borrowings_raised": raised, "refi_dependence": refi,
                "reported_service": rep_service, "reported_dscr": reported_dscr,
                "net_profit": np_, "ebitda": ebitda, "sloan_ratio": sloan, "cash_conversion": cce,
                "total_borrowings": r.get("total_borrowings"),
            })
            out.append(m)
    df = pd.DataFrame(out)
    if len(df):
        df = add_migration(df, cfg)
    return df


def _nan(x):
    return np.nan if x is None else x


def add_migration(df: pd.DataFrame, cfg: RTSConfig) -> pd.DataFrame:
    """Direction vs the mean state of the previous N years (Ponzi=0, Speculative=1, Hedge=2)."""
    df = df.sort_values(["symbol", "period_end"]).copy()
    df["fy_idx"] = df.groupby("symbol").cumcount() + 1          # 1 = earliest fiscal year on Screener
    df["state_ord"] = df["minsky_state"].map(STATE_ORD)
    df["prev_state"] = df.groupby("symbol")["minsky_state"].shift(1)
    dirs, base = [], []
    for _, g in df.groupby("symbol", sort=False):
        ords = g["state_ord"].tolist()
        for i, o in enumerate(ords):
            prior = [x for x in ords[max(0, i - cfg.migration_years):i] if x is not None and not np.isnan(x)]
            if o is None or np.isnan(o) or not prior:
                dirs.append(None)
                base.append(np.nan)
                continue
            mu = float(np.mean(prior))
            base.append(mu)
            d = o - mu
            dirs.append("improving" if d >= cfg.migration_threshold else
                        "deteriorating" if d <= -cfg.migration_threshold else "stable")
    df["prior_state_mean"] = base
    df["migration"] = dirs
    return df


def migration_matrices(annual: pd.DataFrame, years: int = 3) -> dict:
    """1-year pooled transition matrix (all consecutive company-years) and the latest N-year matrix
    (state N years before each company's latest FY -> latest FY). Counts and row percentages."""
    order = ["Hedge", "Speculative", "Ponzi"]
    a = annual.dropna(subset=["minsky_state"]).sort_values(["symbol", "period_end"])
    one = a.dropna(subset=["prev_state"])
    m1 = pd.crosstab(one["prev_state"], one["minsky_state"]).reindex(index=order, columns=order, fill_value=0)
    rows = []
    for sym, g in a.groupby("symbol"):          # state exactly N fiscal years before the latest scored year
        prev = g[g["fy_idx"] == g["fy_idx"].iloc[-1] - years]
        if len(prev):
            rows.append((prev.iloc[0]["minsky_state"], g.iloc[-1]["minsky_state"]))
    mN = (pd.crosstab(pd.Series([r[0] for r in rows], name="from"), pd.Series([r[1] for r in rows], name="to"))
          .reindex(index=order, columns=order, fill_value=0)) if rows else pd.DataFrame(0, index=order, columns=order)
    pct = lambda m: (m.div(m.sum(axis=1).replace(0, np.nan), axis=0) * 100).round(1)
    return {"one_year_counts": m1, "one_year_pct": pct(m1), f"{years}_year_counts": mN, f"{years}_year_pct": pct(mN)}
