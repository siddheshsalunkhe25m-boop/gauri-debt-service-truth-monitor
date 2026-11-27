"""Fact packs: the ONLY information the model receives about a company.

Every fact is a computed number (or a short computed text) with a fixed id [F#], a display string and a unit.
No statements, filings, prices or free text from the web are sent. Tailored covenant levels and monitoring
trigger levels are calculated here by fixed, documented rules, so the model selects and explains levels; it
never invents them.

Tailored covenant rules (all round to the stated step, so they are reproducible):
  DSCR floor (FA basis, annual)    0.80 x 3-yr FA-DSCR, rounded DOWN to 0.05x, kept within [1.00x, 1.30x]
  ICR floor (TTM, quarterly)       0.70 x ICR now, rounded DOWN to 0.25x, kept within [policy, 2 x policy]
  Debt/EBITDA cap (TTM, quarterly) 1.30 x Debt/EBITDA now, rounded UP to 0.25x, kept within [2.00x, policy]
  Creditor-days cap                own 3-yr payable-days norm + 15 days (payables flagged only)
  Refinancing cap                  50% of annual debt service may be refinanced (refinancing > 50% only)
  Cash sweep                       50% of excess cash flow (refinancing > 50% or Escalate)
  DSRA                             next 2 quarters of interest (DSCR floor above current FA-DSCR, or Escalate)
Monitoring trigger (amber) rules
  ICR amber        tailored ICR floor x 1.25, rounded to 0.25x
  Debt/EBITDA amber tailored cap x 0.85, rounded to 0.25x
  Breach probability amber  the Watch override level (default 20%)
  Quarterly EBITDA amber    year-on-year fall of 15% or more in any quarter
  Creditor-days amber       own norm + 10 days
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from dstm_rts.config import RTSConfig
from dstm_rts.decision import recommend, red_flags

NUM_RE = re.compile(r"[-−]?\d[\d,]*(?:\.\d+)?")


@dataclass
class Fact:
    id: str
    key: str
    label: str
    value: Optional[float]
    unit: str            # x | pct | rs_cr | days | score | count | quarters | years | text
    display: str
    source: str = ""
    numbers: list = field(default_factory=list)      # numbers shown inside a text fact


def _ok(v) -> bool:
    try:
        return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) and not pd.isna(v)
    except (TypeError, ValueError):
        return False


def fmt(v, unit) -> str:
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "pct":
        return f"{v * 100:.0f}%"
    if unit == "rs_cr":
        return f"Rs {v:,.0f} Cr"
    if unit == "days":
        return f"{v:.0f} days"
    if unit == "quarters":
        return f"{v:.0f} quarters"
    if unit == "years":
        return f"{v:.0f} years"
    if unit in ("score", "count"):
        return f"{v:.0f}"
    return str(v)


def floor_to(x, step):
    return math.floor(x / step + 1e-9) * step


def ceil_to(x, step):
    return math.ceil(x / step - 1e-9) * step


class Pack:
    def __init__(self):
        self.facts: list[Fact] = []
        self.by_key: dict[str, Fact] = {}

    def add(self, key, label, value, unit, source="", display=None):
        if unit != "text" and not _ok(value):
            return None
        fid = f"F{len(self.facts) + 1}"
        disp = display if display is not None else (fmt(float(value), unit) if unit != "text" else str(value))
        # numbers shown in the label or display (e.g. "within 4 quarters", rule constants) may also be quoted
        shown = f"{label} {disp}" if unit == "text" else label           # a number fact's own value is checked by unit
        nums = [float(n.replace(",", "").replace("−", "-")) for n in NUM_RE.findall(shown)]
        f = Fact(fid, key, label, float(value) if unit != "text" else None, unit, disp, source, nums)
        self.facts.append(f)
        self.by_key[key] = f
        return f

    def ref(self, key) -> str:
        f = self.by_key.get(key)
        return f"{f.display} [{f.id}]" if f else ""

    def as_prompt(self) -> str:
        lines = []
        for f in self.facts:
            lines.append(f"[{f.id}] {f.label}: {f.display}")
        return "\n".join(lines)

    def to_records(self) -> list[dict]:
        return [asdict(f) for f in self.facts]


def tailored_levels(s: dict, a: dict, cfg: RTSConfig) -> dict:
    """Python-computed covenant and trigger levels (see module docstring). Returns key -> (value, unit, label, rule)."""
    out = {}
    dscr = s.get("fa_dscr_3y")
    if _ok(dscr):
        v = min(1.30, max(1.00, floor_to(0.80 * dscr, 0.05)))
        out["cov_dscr_floor"] = (v, "x", "Tailored DSCR floor (forensic-adjusted, annual)",
                                 "0.80 x 3-yr FA-DSCR, rounded down to 0.05x, within 1.00x-1.30x")
    icr = s.get("breach_icr_now")
    icr_floor = cfg.icr_min
    if _ok(icr):
        icr_floor = min(2 * cfg.icr_min, max(cfg.icr_min, floor_to(0.70 * icr, 0.25)))
    out["cov_icr_floor"] = (icr_floor, "x", "Tailored interest-cover floor (TTM EBITDA / interest, quarterly)",
                            "0.70 x ICR now, rounded down to 0.25x, within policy and 2 x policy")
    de = s.get("breach_debt_ebitda_now")
    cap = cfg.debt_ebitda_max
    if _ok(de) and de > 0:
        cap = cfg.debt_ebitda_max if de >= cfg.debt_ebitda_max else min(cfg.debt_ebitda_max, max(2.0, ceil_to(1.30 * de, 0.25)))
    out["cov_de_cap"] = (cap, "x", "Tailored Debt / TTM EBITDA cap (quarterly)",
                         "1.30 x Debt/EBITDA now, rounded up to 0.25x, within 2.00x and policy")
    out["trig_icr_amber"] = (round(icr_floor * 1.25 * 4) / 4, "x", "Amber trigger: interest cover below",
                             "tailored ICR floor x 1.25, rounded to 0.25x")
    out["trig_de_amber"] = (round(cap * 0.85 * 4) / 4, "x", "Amber trigger: Debt / EBITDA above",
                            "tailored cap x 0.85, rounded to 0.25x")
    out["trig_p_breach_amber"] = (cfg.watch_p_breach, "pct", "Amber trigger: modelled breach probability (4 quarters) at or above",
                                  "Watch override level")
    out["trig_q_ebitda_fall"] = (0.15, "pct", "Amber trigger: quarterly EBITDA fall year-on-year of at least",
                                 "fixed rule")
    norm = a.get("payable_days_norm")
    if _ok(norm) and _ok(a.get("payables_stretch")) and a.get("payables_stretch") > 0:
        out["cov_creditor_days_cap"] = (round(norm + 15), "days", "Creditor-days cap (own norm + 15 days)", "own 3-yr norm + 15 days")
        out["trig_creditor_days_amber"] = (round(norm + 10), "days", "Amber trigger: creditor days above", "own norm + 10 days")
    refi = s.get("refi_dependence_3y")
    if _ok(refi) and refi > 0.5:
        out["cov_refi_cap"] = (0.5, "pct", "Maximum share of annual debt service refinanced with new debt", "fixed rule")
    if (_ok(refi) and refi > 0.5) or s.get("rts_class") == "Escalate":
        out["cov_cash_sweep"] = (0.5, "pct", "Excess cash-flow sweep", "fixed rule")
    if (_ok(dscr) and "cov_dscr_floor" in out and out["cov_dscr_floor"][0] > dscr) or s.get("rts_class") == "Escalate":
        out["cov_dsra_quarters"] = (2, "quarters", "Debt-service reserve: quarters of interest", "fixed rule")
    return out


def build_pack(s: dict, a: dict, cfg: RTSConfig, peers: Optional[pd.DataFrame] = None) -> tuple[Pack, list, object]:
    """s: company_scores row (dict, incl. company_name, sector); a: latest scored annual row (dict)."""
    p = Pack()
    flags = red_flags(s, a, cfg)
    rec = recommend(s, cfg, flags)
    p.add("company", "Company", s.get("company_name"), "text", "universe list")
    p.add("sector", "Sector (NSE industry)", s.get("sector"), "text", "universe list")
    p.add("latest_fy", "Latest scored fiscal year ends", str(s.get("latest_fy"))[:10], "text", "Screener")
    # score
    p.add("rts", "Repayment Truth Score (0-100)", s.get("rts"), "score", "RTS")
    p.add("rts_class", "RTS class", s.get("rts_class"), "text", "RTS")
    p.add("rule_decision", "Rule-based decision (dashboard)", f"{rec.decision}: {rec.headline}", "text", "decision rules")
    for k, lbl in (("s_dscr", "Sub-score FA-DSCR"), ("s_minsky", "Sub-score Minsky"), ("s_refi", "Sub-score refinancing"),
                   ("s_breach", "Sub-score Breach Clock")):
        p.add(k, lbl + " (0-100)", s.get(k), "score", "RTS")
    # debt service
    p.add("fa_dscr_3y", "Forensic-adjusted DSCR, 3-yr pooled", s.get("fa_dscr_3y"), "x", "RTS")
    p.add("reported_dscr_3y", "Reported DSCR (reported CFO, no adjustments), 3-yr pooled", s.get("reported_dscr_3y"), "x", "RTS")
    p.add("fa_dscr_maint_3y", "FA-DSCR after maintenance capex (depreciation proxy), 3-yr", s.get("fa_dscr_maint_3y"), "x", "RTS")
    p.add("fa_dscr_latest", "Forensic-adjusted DSCR, latest year", s.get("fa_dscr_latest"), "x", "RTS")
    p.add("minsky_state", "Minsky state, latest year", s.get("minsky_state"), "text", "RTS")
    if isinstance(s.get("migration"), str):
        p.add("migration", "Minsky migration vs previous 3 years", s.get("migration"), "text", "RTS")
    p.add("minsky_path", "Minsky states, last 3 fiscal years (H/S/P)", s.get("minsky_path"), "text", "RTS")
    p.add("refi_3y", "Refinancing dependence (new borrowing / debt service), 3-yr", s.get("refi_dependence_3y"), "pct", "RTS")
    # latest year bridge
    for k, lbl, unit in (("cfo", "Reported CFO, latest year", "rs_cr"), ("payables_stretch", "Payables stretch beyond own norm", "rs_cr"),
                         ("exceptional_gain_deducted", "Exceptional gains deducted", "rs_cr"),
                         ("noncore_income_deducted", "Non-core other income deducted", "rs_cr"),
                         ("cfo_adj", "Forensic-adjusted CFO", "rs_cr"), ("cfads", "Cash available for debt service (CFADS)", "rs_cr"),
                         ("interest_paid", "Interest paid", "rs_cr"), ("principal_repaid", "Borrowing repayments", "rs_cr"),
                         ("lease_payments", "Lease payments", "rs_cr"), ("debt_service", "Total debt service", "rs_cr"),
                         ("borrowings_raised", "New borrowing raised", "rs_cr"), ("payable_days", "Payable days (on operating expenses)", "days"),
                         ("payable_days_norm", "Own 3-yr payable-days norm", "days"),
                         ("sloan_ratio", "Accrual (Sloan) ratio", "pct"), ("cash_conversion", "Cash conversion (CFO / EBITDA)", "pct")):
        p.add(k, lbl, a.get(k), unit, "Annual (latest scored year)")
    if a.get("interest_location"):
        p.add("interest_location", "Where interest is paid (cash flow)", a.get("interest_location"), "text", "Annual")
    # breach clock
    p.add("icr_now", "Interest cover now (TTM EBITDA / interest)", s.get("breach_icr_now"), "x", "Breach Clock")
    p.add("de_now", "Debt / TTM EBITDA now", s.get("breach_debt_ebitda_now"), "x", "Breach Clock")
    p.add("debt", "Debt used in the Breach Clock (latest balance sheet)", s.get("breach_debt"), "rs_cr", "Breach Clock")
    p.add("p_base", f"Probability of covenant breach within {cfg.breach_window_q} quarters, baseline", s.get("p_breach_base"), "pct", "Breach Clock")
    p.add("p_stress", f"Probability of covenant breach within {cfg.breach_window_q} quarters, stress", s.get("p_breach_stress"), "pct", "Breach Clock")
    if _ok(s.get("median_q_base")):
        p.add("median_q", "Median quarters to first breach, baseline", s.get("median_q_base"), "quarters", "Breach Clock")
    p.add("breach_status", "Breach Clock status", s.get("breach_status"), "text", "Breach Clock")
    # policy
    p.add("policy_icr", "Policy covenant: minimum interest cover", cfg.icr_min, "x", "settings")
    p.add("policy_de", "Policy covenant: maximum Debt / EBITDA", cfg.debt_ebitda_max, "x", "settings")
    p.add("window_q", "Breach window", cfg.breach_window_q, "quarters", "settings")
    p.add("stress_haircut", "Stress: EBITDA haircut", cfg.stress_ebitda_haircut, "pct", "settings")
    p.add("stress_uplift", "Stress: interest uplift", cfg.stress_interest_uplift, "pct", "settings")
    # peers
    if peers is not None and len(peers):
        b = peers.set_index("metric")
        for m, lbl in (("rts", "RTS"), ("fa_dscr_3y", "FA-DSCR 3-yr"), ("p_breach_base", "breach probability (lower is better)")):
            if m in b.index:
                p.add(f"sector_pct_{m}", f"Sector percentile, {lbl} (100 = best)", b.loc[m, "sector_pct"], "score", "peers")
                p.add(f"universe_pct_{m}", f"Universe percentile, {lbl} (100 = best)", b.loc[m, "universe_pct"], "score", "peers")
    # red flags
    for i, fl in enumerate(flags, 1):
        p.add(f"flag_{i}_{fl['code']}", f"Red flag ({fl['severity']})", fl["text"], "text", fl["source"])
    # process constants (fixed by the bank's monitoring process, so quotable)
    p.add("pooling_years", "Pooling window for DSCR and refinancing", cfg.refi_years, "years", "settings")
    p.add("dd_history_q", "History requested in due diligence", 8, "quarters", "monitoring process")
    p.add("response_days", "Borrower response deadline after a trigger", 30, "days", "monitoring process")
    p.add("stepdown_q", "Clean quarterly covenant tests needed before a pricing step-down", 2, "quarters", "decision rules")
    # tailored levels
    for k, (v, unit, lbl, rule) in tailored_levels(s, a, cfg).items():
        p.add(k, f"{lbl} [rule: {rule}]", v, unit, "tailored-level rules")
    return p, flags, rec
