"""Template fallback: the same four outputs written by fixed rules from the same fact pack (used when no API key,
an API error, or a draft that fails the number check twice). Every number is taken from a fact and cited."""
from __future__ import annotations

from .facts import Pack

DD_BANK = {
    "payables_stretch": [("Please provide creditor ageing for the last {dd_history_q} and explain why payable days rose "
                          "to {payable_days} against your own norm of {payable_days_norm}.",
                          "Payables above norm boost reported cash flow without lasting cash generation."),
                         ("Have any supplier terms been renegotiated, or are supply-chain finance / bill discounting "
                          "arrangements used that move payables?", "Supplier finance can disguise borrowing as payables.")],
    "exceptional_gain": [("Please describe the exceptional gains of {exceptional_gain_deducted} and confirm whether any "
                          "similar receipts are expected again.", "One-off gains are not repeatable repayment capacity.")],
    "noncore_income": [("Please break down other income of {noncore_income_deducted} by source and state which part is "
                        "received in cash.", "Non-core income may not be available for debt service.")],
    "interest_location_inferred": [("Please provide the cash-flow statement with interest paid shown as a separate line.",
                                    "Interest paid had to be inferred, which affects the DSCR.")],
    "interest_in_cfo": [("Please confirm the interest paid included within operating cash flow for the latest year.",
                         "Interest inside operating cash flow is added back before computing DSCR.")],
    "lease_heavy": [("Please provide the lease maturity profile and any renewal or escalation terms.",
                     "Lease payments are a large part of debt service.")],
    "accruals": [("Please reconcile net profit to operating cash flow for the last {pooling_years}, explaining the largest "
                  "accrual items.", "Profit not backed by cash flow is a classic earnings-quality warning.")],
    "cash_conversion": [("Please explain why operating cash flow was only {cash_conversion} of EBITDA, listing the "
                         "working-capital items involved.", "Low cash conversion weakens repayment capacity.")],
    "breach_now": [("Please provide the latest covenant compliance certificates for all lenders and any waivers obtained.",
                    "The borrower is already outside the policy covenant on actual figures.")],
    "trigger": [],
    "missing": [],
}
TRIGGER_DD = [   # (text fragment of an RTS rule trigger, question, why)
    ("already outside covenant", "Please provide the latest covenant compliance certificates for every lender and any waivers "
     "or standstills agreed.", "The borrower is already outside the policy covenant on actual figures."),
    ("Ponzi", "Please explain how interest was paid in the latest year given that adjusted operating cash flow did not cover "
     "it, listing every source of funds used.", "Interest met from borrowing or asset sales is not sustainable."),
    ("funded by new borrowing", "Please list all borrowings refinanced in the last {pooling_years} with lender, amount and "
     "new tenor, and the refinancing plan for the next {dd_history_q}.", "Repayment relies on continued access to new debt."),
    ("maintenance capex", "Please split capital expenditure into maintenance and growth for the last {pooling_years} and "
     "give the funding plan for committed growth capex.", "Depreciation used as the maintenance proxy exceeds spare cash."),
    ("probability of covenant breach", "Please provide quarterly EBITDA and interest projections for the next {dd_history_q} "
     "with the main assumptions.", "The Breach Clock shows a material chance of a covenant breach."),
    ("Speculative and deteriorating", "Please explain the decline in operating cash flow relative to debt service and the "
     "actions planned to restore it.", "The borrower now covers interest but not principal from operations."),
]
GENERIC = [("Please provide the debt maturity schedule for the next {dd_history_q}, including undrawn committed lines.",
            "Repayment capacity depends on the timing of maturities and available liquidity."),
           ("Please list all borrowings refinanced in the last {pooling_years} with lender, amount and new tenor.",
            "Refinancing dependence of {refi_3y} needs to be understood lender by lender."),
           ("Please provide related-party loans, guarantees and investments outstanding at year-end.",
            "Related-party exposures can drain cash available for debt service.")]


def _r(p: Pack, key: str) -> str:
    return p.ref(key) or "not available"


def _fill(text: str, p: Pack) -> str:
    out = text
    for k in list(p.by_key):
        out = out.replace("{" + k + "}", _r(p, k))
    return out


def _cash_quality(p: Pack) -> str:
    g = p.by_key.get
    parts = [(k, lbl) for k, lbl in (("payables_stretch", "a payables stretch beyond the company's own norm of"),
                                     ("exceptional_gain_deducted", "exceptional gains of"),
                                     ("noncore_income_deducted", "non-core other income of"))
             if g(k) and g(k).value and abs(g(k).value) >= 0.5]
    head = f"In the latest year reported CFO was {_r(p, 'cfo')}"
    if not parts:
        txt = f"{head} and no forensic deduction was needed, so forensic-adjusted CFO is {_r(p, 'cfo_adj')}."
    else:
        txt = (f"{head}; the forensic adjustments removed " + ", ".join(f"{lbl} {_r(p, k)}" for k, lbl in parts) +
               f", leaving forensic-adjusted CFO of {_r(p, 'cfo_adj')}.")
    if g("cash_conversion"):
        txt += f" Cash conversion (CFO / EBITDA) was {_r(p, 'cash_conversion')}"
        txt += f" and the accrual ratio {_r(p, 'sloan_ratio')}." if g("sloan_ratio") else "."
    return txt


def template_output(p: Pack, flags: list, rec) -> dict:
    g = p.by_key.get
    cls = g("rts_class").display if g("rts_class") else "n/a"
    name = g("company").display if g("company") else "The borrower"
    dec = rec.decision
    note = {
        "summary": f"{name} scores {_r(p, 'rts')} on the Repayment Truth Score and is classed {cls} [{g('rts_class').id}]. "
                   f"The rule-based recommendation is {dec} [{g('rule_decision').id}].",
        "repayment_capacity": f"Forensic-adjusted DSCR is {_r(p, 'fa_dscr_3y')} over 3 years against {_r(p, 'reported_dscr_3y')} "
                              f"on reported cash flow; after maintenance capex it is {_r(p, 'fa_dscr_maint_3y')}. "
                              f"The Minsky state is {g('minsky_state').display if g('minsky_state') else 'n/a'} "
                              f"[{g('minsky_state').id if g('minsky_state') else '-'}]"
                              + (f", {g('migration').display} [{g('migration').id}]." if g("migration") else "."),
        "cash_quality": _cash_quality(p),
        "refinancing_and_liquidity": f"New borrowing funded {_r(p, 'refi_3y')} of debt service over 3 years. Debt service in the "
                                     f"latest year was {_r(p, 'debt_service')} against new borrowing of {_r(p, 'borrowings_raised')}.",
        "covenant_outlook": (f"Interest cover is {_r(p, 'icr_now')} and Debt / EBITDA {_r(p, 'de_now')} against policy levels of "
                             f"{_r(p, 'policy_icr')} and {_r(p, 'policy_de')}. The modelled probability of a covenant breach "
                             f"is {_r(p, 'p_base')} in the baseline and {_r(p, 'p_stress')} under stress.")
        if g("p_base") else "The Breach Clock is not available for this borrower.",
        "peer_position": (f"On RTS the company has a sector percentile rank of {_r(p, 'sector_pct_rts')} and a universe "
                          f"percentile rank of {_r(p, 'universe_pct_rts')} (100 = best).") if g("sector_pct_rts") else
                         "Peer percentiles are not available.",
        "recommendation": f"{dec}: {rec.headline}. " + rec.pricing.replace("for 2 consecutive quarters",
                                                                          f"for {_r(p, 'stepdown_q')} in a row") + ".",
    }
    cov = []

    def why_level(key, now_key, higher_is_better, base):
        f, now = g(key), g(now_key)
        if not f or not now or now.value is None:
            return base
        breached = now.value < f.value if higher_is_better else now.value > f.value
        if breached:
            return (f"Already outside this level today ({_r(p, now_key)}): set it as a target with a cure period, "
                    "backed by the reserve and sweep below.")
        return base + f" Today: {_r(p, now_key)}."
    spec = [("cov_dscr_floor", "Minimum forensic-adjusted DSCR", "annual",
             why_level("cov_dscr_floor", "fa_dscr_3y", True, "Floor set below current forensic-adjusted repayment capacity, "
                       "so that a fall in adjusted cash flow is caught early.")),
            ("cov_icr_floor", "Minimum interest cover (TTM EBITDA / interest)", "quarterly",
             why_level("cov_icr_floor", "icr_now", True, "Tailored to current interest cover, never below policy.")),
            ("cov_de_cap", "Maximum Debt / TTM EBITDA", "quarterly",
             why_level("cov_de_cap", "de_now", False, "Tailored to current leverage, never above policy.")),
            ("cov_creditor_days_cap", "Creditor-days cap", "quarterly", "Stops cash flow being flattered by stretching suppliers."),
            ("cov_refi_cap", "Cap on refinancing of scheduled debt service", "annual", "Limits reliance on new borrowing to repay old."),
            ("cov_cash_sweep", "Excess cash-flow sweep", "annual", "Accelerates repayment from surplus cash."),
            ("cov_dsra_quarters", "Debt-service reserve account", "maintained continuously",
             "Buffer while repayment capacity is below the floor.")]
    for key, name_, freq, why in spec:
        if g(key):
            cov.append({"covenant": name_, "level": _r(p, key), "test_frequency": freq, "rationale": why})
    trig = []
    for key, name_, act in (("trig_icr_amber", "Interest cover (TTM)", "Call management; request monthly MIS."),
                            ("trig_de_amber", "Debt / EBITDA (TTM)", "No new limits until leverage is back inside the trigger."),
                            ("trig_p_breach_amber", "Modelled covenant-breach probability", "Move the account to the watch list."),
                            ("trig_q_ebitda_fall", "Quarterly EBITDA year-on-year", "Ask for a written explanation within {response_days} of results."),
                            ("trig_creditor_days_amber", "Creditor days", "Request creditor ageing and supplier-finance details.")):
        if g(key):
            trig.append({"trigger": name_, "threshold": _r(p, key), "action": _fill(act, p)})
    dd = []
    flag_facts = [f for f in p.facts if f.key.startswith("flag_")]
    seen = set()
    for f in flag_facts:
        code = f.key.split("_", 2)[2]
        pairs = list(DD_BANK.get(code, []))
        if code == "trigger":
            pairs += [(q, why) for frag, q, why in TRIGGER_DD if frag in f.display]
        for q, why in pairs:
            if q in seen:
                continue
            seen.add(q)
            dd.append({"question": _fill(q, p), "red_flag": f"{f.display} [{f.id}]", "why": _fill(why, p)})
    if len(dd) < 3:
        for q, why in [g for g in GENERIC if g[0] not in seen][: 3 - len(dd) + 1]:
            dd.append({"question": _fill(q, p), "red_flag": "general debt-service diligence", "why": _fill(why, p)})
    return {"credit_note": note, "covenants": cov, "monitoring_triggers": trig, "dd_questions": dd}
