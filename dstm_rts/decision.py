"""Rule-based credit decision suggestion and covenant package. DECISION SUPPORT ONLY: the analyst decides.

Decision ladder (worst rule wins)
  Hold          Insufficient data: no fiscal year with cash flow AND debt service.
  Watch         RTS class Escalate: refer to credit committee; no enhancement; renew only with tighter terms,
                repricing and security top-up; consider reducing exposure.
  Reprice       RTS class Watch: renew with a higher spread and tighter covenants; no enhancement until the
                triggers clear.
  Renew         Safe: renew on existing terms.
  Enhance       Safe AND RTS >= 80 AND 3-yr FA-DSCR >= 1.5x AND refinancing dependence <= 50% AND
                baseline P(breach in 4q) < 5% AND no trigger: eligible for sanction of new / enhanced limits.

Covenants
  Financial: the policy covenants (ICR >= icr_min, Debt/EBITDA <= debt_ebitda_max, TTM, tested quarterly),
  each shown with today's headroom. If headroom on either is under 25% the covenant is marked "tight".
  Add-ons are switched on by the specific weakness found (each line says why).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import RTSConfig


@dataclass
class Recommendation:
    decision: str                 # Hold | Watch | Reprice | Renew | Enhance
    headline: str
    rationale: list = field(default_factory=list)
    covenants: list = field(default_factory=list)       # (covenant, level, why)
    pricing: str = ""
    monitoring: str = ""


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def headroom(now, limit, higher_is_better=True):
    """Fraction by which the metric can deteriorate before it breaches the covenant."""
    now = _num(now)
    if now is None:
        return None
    if math.isinf(now):
        return 1.0 if higher_is_better else -1.0
    if higher_is_better:
        return 1 - limit / now if now > 0 else -1.0
    return limit / now - 1 if now > 0 else 1.0


def recommend(s: dict, cfg: RTSConfig, flags: list | None = None) -> Recommendation:
    """s: one row of company_scores() as a dict; flags: red-flag dicts from red_flags()."""
    flags = flags or []
    cls = s.get("rts_class")
    rts = _num(s.get("rts"))
    dscr = _num(s.get("fa_dscr_3y"))
    dscr_m = _num(s.get("fa_dscr_maint_3y"))
    refi = _num(s.get("refi_dependence_3y"))
    pb = _num(s.get("p_breach_base"))
    state, mig = s.get("minsky_state"), s.get("migration")
    trig = s.get("triggers") or ""

    if cls in (None, "Insufficient data"):
        return Recommendation("Hold", "Hold: not enough data to score repayment capacity",
                              ["No fiscal year with both operating cash flow and debt-service data on Screener."],
                              [("Information", "Audited cash-flow statement with interest and repayment detail",
                                "needed before any decision")], "", "")

    r = []
    if dscr is not None:
        r.append(f"Forensic-adjusted DSCR {dscr:.2f}x over 3 years" +
                 (f" (reported basis {_num(s.get('reported_dscr_3y')):.2f}x)" if _num(s.get("reported_dscr_3y")) is not None else ""))
    else:
        r.append("Negligible debt service in the last 3 years")
    r.append(f"Minsky state {state}" + (f", {mig}" if isinstance(mig, str) and mig else ""))
    if refi is not None:
        r.append(f"{min(refi, 9.99):.0%} of debt service funded by new borrowing (3-yr)")
    if pb is not None:
        r.append(f"{pb:.0%} probability of covenant breach within {cfg.breach_window_q} quarters (baseline), "
                 f"{_num(s.get('p_breach_stress')) or 0:.0%} under stress")
    elif s.get("breach_status"):
        r.append(f"Breach Clock not run ({s.get('breach_status')})")

    if cls == "Escalate":
        dec, head = "Watch", "Put on watch: refer to credit committee, no enhancement"
        pricing = "Reprice upward (risk-based spread) at renewal; consider reducing exposure or security top-up"
        mon = "Monthly MIS and quarterly covenant certificate; early-warning review within 30 days"
    elif cls == "Watch":
        dec, head = "Reprice", "Renew with repricing and tighter covenants; no enhancement until triggers clear"
        pricing = "Add a risk premium to the spread; step-down once triggers clear for 2 consecutive quarters"
        mon = "Quarterly covenant certificate and MIS"
    else:
        eligible = (rts is not None and rts >= 80 and (dscr is None or dscr >= 1.5) and (refi is None or refi <= 0.5)
                    and (pb is None or pb < 0.05) and not trig)
        if eligible:
            dec, head = "Enhance", "Eligible to sanction / enhance limits on standard terms"
            pricing = "Standard grid pricing"
        else:
            dec, head = "Renew", "Renew on existing terms"
            pricing = "Existing pricing"
        mon = "Half-yearly covenant certificate"

    cov = []
    icr_now, de_now = _num(s.get("breach_icr_now")), _num(s.get("breach_debt_ebitda_now"))
    hi = headroom(icr_now, cfg.icr_min, True)
    hd = headroom(de_now, cfg.debt_ebitda_max, False)
    def hr(h):
        if h is None:
            return "headroom n/a"
        if h < 0:
            return "ALREADY BREACHED"
        return f"headroom {h:.0%}" + (" (tight)" if h < 0.25 else "")
    cov.append(("Interest cover (TTM EBITDA / interest), quarterly", f">= {cfg.icr_min:.1f}x",
                f"now {icr_now:.2f}x, {hr(hi)}" if icr_now is not None and not math.isinf(icr_now) else "no interest cost now"))
    cov.append(("Debt / TTM EBITDA (gross, incl. lease liabilities), quarterly", f"<= {cfg.debt_ebitda_max:.1f}x",
                f"now {de_now:.2f}x, {hr(hd)}" if de_now is not None and not math.isinf(de_now) else
                ("TTM EBITDA <= 0" if de_now is not None else "n/a")))
    if dscr is not None and (dscr < 1.2 or cls != "Safe"):
        cov.append(("Minimum DSCR (forensic-adjusted CFO basis), annual", ">= 1.2x",
                    f"3-yr FA-DSCR {dscr:.2f}x; plus a debt-service reserve of next 2 quarters' interest"))
    if refi is not None and refi > 0.5:
        cov.append(("No refinancing of scheduled principal with new debt without lender consent; 50% excess cash sweep",
                    "-", f"{min(refi, 9.99):.0%} of debt service was funded by new borrowing"))
    if dscr_m is not None and dscr_m < 1.0:
        cov.append(("Capex covenant: growth capex only from equity or surplus cash", "-",
                    f"DSCR after maintenance capex (depreciation proxy) {dscr_m:.2f}x < 1.0x"))
    codes = {f["code"] for f in flags}
    if "payables_stretch" in codes:
        cov.append(("Information covenant: quarterly creditor ageing; creditor days capped at own 3-yr norm + 15 days",
                    "-", "payables stretched beyond the company's own norm flattered CFO"))
    if "lease_heavy" in codes:
        cov.append(("Debt definition includes lease liabilities", "-", "lease payments are a large part of debt service"))
    if "interest_location_inferred" in codes or "pnl_interest_fallback" in codes:
        cov.append(("Information covenant: cash-flow statement with interest paid shown separately", "-",
                    "interest paid not shown as a cash-flow line on Screener; location inferred"))
    if state == "Ponzi":
        cov.append(("Security top-up / additional collateral; promoter guarantee", "-",
                     "adjusted operating cash does not cover interest"))
    if pb is not None and pb >= cfg.watch_p_breach:
        cov.append(("Equity-cure right limited to 2 uses; standstill not to be assumed", "-",
                    f"{pb:.0%} modelled chance of a covenant breach within {cfg.breach_window_q} quarters"))
    return Recommendation(dec, head, r, cov, pricing, mon)


def red_flags(s: dict, annual_last: dict | None, cfg: RTSConfig) -> list:
    """Red flags for one company: RTS triggers + forensic / data-quality flags. Each: code, severity, text."""
    out = []
    a = annual_last or {}
    for t in (s.get("triggers") or "").split(" | "):
        if not t:
            continue
        lvl = "high" if t.startswith("[Escalate]") else "medium"
        out.append({"code": "trigger", "severity": lvl, "text": t.split("] ", 1)[-1], "source": "RTS rule"})
    if s.get("breach_status") == "already_in_breach" and not any("already outside" in f["text"] for f in out):
        out.append({"code": "breach_now", "severity": "high", "text": "Already outside covenant on actual TTM",
                    "source": "Breach Clock"})
    st = _num(a.get("payables_stretch"))
    cfo = _num(a.get("cfo"))
    if st and st > 0:
        share = st / abs(cfo) if cfo else None
        out.append({"code": "payables_stretch", "severity": "medium" if (share or 0) > cfg.watch_stretch_share else "low",
                    "text": f"Payables Rs {st:,.0f} Cr above own norm ({a.get('stretch_note')})"
                            + (f" = {share:.0%} of reported CFO" if share is not None else ""),
                    "source": "Annual: trade payables vs operating expenses"})
    exc = _num(a.get("exceptional_gain_deducted"))
    if exc and exc > 0:
        out.append({"code": "exceptional_gain", "severity": "low", "text": f"Exceptional gain Rs {exc:,.0f} Cr deducted from CFO",
                    "source": "P&L: Other Income > Exceptional items"})
    nc = _num(a.get("noncore_income_deducted"))
    if nc and cfo and nc / abs(cfo) > 0.15:
        out.append({"code": "noncore_income", "severity": "low",
                    "text": f"Non-core other income Rs {nc:,.0f} Cr = {nc / abs(cfo):.0%} of CFO", "source": "P&L: Other Income"})
    flag = a.get("interest_paid_flag") or ""
    if flag == "fallback_pnl_interest":
        out.append({"code": "interest_location_inferred", "severity": "low",
                    "text": f"No interest-paid cash-flow line: P&L interest used; {a.get('interest_location')}",
                    "source": "Cash flow"})
    elif flag == "interest_in_cfo":
        out.append({"code": "interest_in_cfo", "severity": "info", "text": "Interest paid reported inside operating cash flow (added back)",
                    "source": "Cash flow"})
    lease, serv = _num(a.get("lease_payments")), _num(a.get("debt_service"))
    if lease and serv and lease / serv > 0.25:
        out.append({"code": "lease_heavy", "severity": "info", "text": f"Lease payments {lease / serv:.0%} of debt service",
                    "source": "Cash flow: Financial liabilities"})
    sl = _num(a.get("sloan_ratio"))
    if sl is not None and sl > 0.10:
        out.append({"code": "accruals", "severity": "medium", "text": f"Accrual (Sloan) ratio {sl:.1%} > 10%: profit not backed by cash",
                    "source": "Sessions 7-8 diagnostic"})
    cc = _num(a.get("cash_conversion"))
    if cc is not None and cc < 0.5:
        out.append({"code": "cash_conversion", "severity": "medium", "text": f"Cash conversion CFO/EBITDA {cc:.0%} < 50%",
                    "source": "Sessions 5-6 diagnostic"})
    if s.get("missing_components"):
        out.append({"code": "missing", "severity": "info", "text": f"Not scored: {s['missing_components']} (weights re-normalised)",
                    "source": "RTS"})
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    return sorted(out, key=lambda f: order[f["severity"]])
