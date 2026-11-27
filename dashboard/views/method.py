"""Method, data status and evidence."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data
from ctx import CTX


def render():
    ld, cfg = CTX["ld"], CTX["cfg"]
    st.title("Method & data")

    st.subheader("Data")
    st.markdown(f"- **Source showing:** {ld['source']} · as of {CTX['fmt_asof'](ld['as_of'])}\n"
                f"- **Order of fallback:** live cache (`data/dstm.db`) → offline snapshot "
                f"(`dashboard/snapshot/credit_lines.parquet`, rewritten after each good load) → synthetic demo\n"
                f"- **Universe:** NSE Nifty 200 minus NSE 'Financial Services'; Screener's bank/NBFC layout excluded as a "
                f"safety net. Case studies (outside the index) are scored but hidden unless switched on.")
    cs = data.company_status()
    if len(cs):
        st.markdown("**Per-company fetch status (last run)**")
        st.dataframe(cs[["symbol", "status", "primary_basis", "basis_note", "last_success", "n_requests", "n_failed",
                         "message"]], hide_index=True, width="stretch", height=260)
        with st.expander("Audit log (latest 300 requests)"):
            st.dataframe(data.audit_tail(), hide_index=True, width="stretch")

    st.subheader("Validation status")
    v = data.validation_status()
    if not v["done"]:
        st.warning("Not yet back-tested on real data. Run `python -m dstm_validate` after loading Screener data; "
                   "results appear here.", icon="⚠️")
    elif v.get("synthetic"):
        st.warning("Only the synthetic machinery check has been run (planted signal). It proves the code works, "
                   "not that RTS works.", icon="⚠️")
    else:
        t = v["auc"]
        st.dataframe(t[t.outcome == "any_new_event"], hide_index=True, width="stretch")
        st.caption("AUC: 0.5 = coin flip. Intervals from a company-cluster bootstrap. See validation report for biases.")

    st.subheader("AI usage log (for the appendix)")
    from views.ai_tab import render_ai_log
    render_ai_log()

    st.subheader("How the score is built")
    st.markdown(f"""
| Step | Definition |
|---|---|
| Forensic-adjusted CFO | CFO − payables stretch beyond the company's own 3-yr norm − positive exceptional items − non-core other income |
| CFADS | CFO_adj + interest add-back (**{cfg.interest_addback}**: only interest paid *inside* CFO is added back by default) |
| FA-DSCR | CFADS ÷ (interest paid + repayments{' + lease payments' if cfg.include_lease_payments else ''}); variant after maintenance capex (depreciation proxy) |
| Minsky state | Hedge: CFADS ≥ interest + repayments · Speculative: ≥ interest · Ponzi: < interest; migration vs mean of prior {cfg.migration_years} years |
| Refinancing dependence | new borrowing ÷ (interest + repayments), 3-yr pooled |
| Breach Clock | {cfg.n_paths:,}-path seasonal bootstrap of 13 quarters; covenants ICR ≥ {cfg.icr_min:.2f}x, Debt/EBITDA ≤ {cfg.debt_ebitda_max:.2f}x; P(breach ≤ {cfg.breach_window_q}q), baseline & stress |
| RTS | {cfg.weights['dscr']:.0%} FA-DSCR + {cfg.weights['minsky']:.0%} Minsky + {cfg.weights['refi']:.0%} refinancing + {cfg.weights['breach']:.0%} Breach Clock; Safe ≥ {cfg.safe_min:.0f}, Watch ≥ {cfg.watch_min:.0f}, plus override rules |
""")
    st.subheader("Proxies and limits (stated honestly)")
    st.markdown("""
- **Payable days use operating expenses** (Sales − Operating Profit); cost of goods sold is not available for every company.
- **Repayments are gross** and include roll-over of short-term debt; scheduled principal is not on Screener.
- **Lease principal** = Screener "Financial liabilities" outflow. **Maintenance capex** = depreciation.
- **Breach Clock debt is held** at the latest reported balance sheet (no quarterly debt); interest cover is EBITDA-based.
- **No interest line in the cash flow** → P&L interest used and its location (CFO or financing) inferred.
- **Breach Clock cannot be back-tested** across years: Screener's public pages carry only 13 quarters.
- **Restatements:** Screener shows the latest figures for past years, not those first published.
- **Recommended decision** is a rule-based suggestion; it does not replace credit judgement, site visits or bank statements.
""")


render()
