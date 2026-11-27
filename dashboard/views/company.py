"""Company drill-down."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import charts
from ctx import CTX
from dstm_rts.breach import fan
from dstm_rts.decision import recommend, red_flags
from dstm_rts.peers import METRICS, benchmark

CLASS_ICON = {"Safe": "✅", "Watch": "⚠️", "Escalate": "⛔", "Insufficient data": "▫️"}
SEV = {"high": ("⛔", "High"), "medium": ("⚠️", "Medium"), "low": ("🔹", "Low"), "info": ("ℹ️", "Info")}
DECISION_ICON = {"Enhance": "✅", "Renew": "✅", "Reprice": "⚠️", "Watch": "⛔", "Hold": "▫️"}


@st.cache_data(show_spinner="Simulating Breach Clock paths…")
def cached_fan(tok, cfg_json, sym, _q, _debt, _cfg):
    return fan(sym, _q, _debt, _cfg)


def _f(v, fmt, dash="–"):
    try:
        if v is None or pd.isna(v) or (isinstance(v, float) and np.isinf(v)):
            return dash
        return fmt.format(v)
    except (TypeError, ValueError):
        return dash


def render():
    res, cfg, P, ld = CTX["res"], CTX["cfg"], CTX["P"], CTX["ld"]
    sc = res.scores
    opts = sc.sort_values("company_name").symbol.tolist()
    qp = st.query_params.get("symbol")
    default = st.session_state.get("symbol") or (qp if qp in opts else None) or opts[0]
    label = dict(zip(sc.symbol, sc.company_name + " (" + sc.symbol + ")"))
    sym = st.selectbox("Company", opts, index=opts.index(default) if default in opts else 0,
                       format_func=lambda s: label.get(s, s))
    st.session_state["symbol"] = sym
    st.query_params["symbol"] = sym
    s = sc[sc.symbol == sym].iloc[0].to_dict()
    a = res.annual[res.annual.symbol == sym].sort_values("period_end")
    scored = a[a.minsky_state.notna()]
    last = scored.iloc[-1].to_dict() if len(scored) else {}
    flags = red_flags(s, last, cfg)
    rec = recommend(s, cfg, flags)

    # ---------------------------------------------------------------- header + decision
    st.title(s["company_name"])
    st.caption(f"{sym} · {s['sector']} · latest scored FY {str(s.get('latest_fy'))[:7]} · "
               f"Breach Clock debt as of {_f(s.get('breach_debt_date'), '{}')} · data {CTX['fmt_asof'](ld['as_of'])}")
    left, right = st.columns([1.05, 1.6])
    with left:
        cls = s.get("rts_class")
        st.markdown(f"#### {CLASS_ICON.get(cls, '')} {cls}")
        st.metric("Repayment Truth Score", _f(s.get("rts"), "{:.0f} / 100"),
                  help="Weighted sub-scores; Safe ≥ %.0f, Watch ≥ %.0f, then override rules." % (cfg.safe_min, cfg.watch_min))
        st.plotly_chart(charts.subscores(s, cfg.weights, P), width="stretch", config={"displayModeBar": False})
        if s.get("missing_components"):
            st.caption(f"Not scored: {s['missing_components']} (weights re-normalised).")
    with right:
        with st.container(border=True):
            st.markdown(f"#### {DECISION_ICON.get(rec.decision, '')} Recommended decision: {rec.decision}")
            st.markdown(f"**{rec.headline}**")
            for line in rec.rationale:
                st.markdown(f"- {line}")
            if rec.pricing:
                st.markdown(f"**Pricing:** {rec.pricing}  \n**Monitoring:** {rec.monitoring}")
            if rec.covenants:
                st.markdown("**Covenant package**")
                st.markdown("\n".join(f"- **{c}**" + (f" {lvl}" if lvl != "-" else "") + f"  \n  <span style='opacity:.7;"
                                       f"font-size:.9rem'>{why}</span>" for c, lvl, why in rec.covenants),
                            unsafe_allow_html=True)
            st.caption("Rule-based suggestion from the scores and flags below. The credit decision is the analyst's.")

    # ---------------------------------------------------------------- KPI row
    k = st.columns(5)
    k[0].metric("FA-DSCR (3-yr)", _f(s.get("fa_dscr_3y"), "{:.2f}x", "no debt service"),
                delta=None if pd.isna(s.get("fa_dscr_3y")) or pd.isna(s.get("reported_dscr_3y")) else
                f"{s['fa_dscr_3y'] - s['reported_dscr_3y']:+.2f}x vs reported", delta_color="normal",
                help="Cash available for debt service after forensic adjustments / (interest + repayments incl. leases), "
                     "pooled over 3 fiscal years. Delta = difference from the unadjusted reported-CFO DSCR.")
    k[1].metric("Minsky state", s.get("minsky_state") or "–")
    k[1].caption(f"Migration: {s.get('migration') if isinstance(s.get('migration'), str) else 'n/a'}")
    k[2].metric("Refinancing dependence", _f(s.get("refi_dependence_3y"), "{:.0%}"),
                help="New borrowing / (interest + repayments), 3-yr pooled.")
    k[3].metric(f"P(breach ≤ {cfg.breach_window_q}q), baseline", _f(s.get("p_breach_base"), "{:.0%}"))
    k[3].caption(f"Stress: {_f(s.get('p_breach_stress'), '{:.0%}')}")
    mq = s.get("median_q_base")
    k[4].metric("Median quarters to breach",
                "now" if s.get("breach_status") == "already_in_breach" else
                (f">{cfg.horizon_q}" if s.get("breach_status") == "ok" and pd.isna(mq) else _f(mq, "{:.0f}")),
                help=f"Median first breach quarter over {cfg.horizon_q} simulated quarters (baseline).")

    tabs = st.tabs(["Debt service", "Minsky history", "Breach Clock", f"Red flags ({len(flags)})", "Peers", "Source lines",
                    "AI credit note"])

    # ---------------------------------------------------------------- debt service
    with tabs[0]:
        fig = charts.dscr_history(a, P)
        if fig is None:
            st.write("No fiscal year with debt-service data.")
        else:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        if last:
            fig = charts.cfo_bridge(last, P)
            if fig is not None:
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption(f"Interest: {last.get('interest_location')}. Payables: {last.get('stretch_note')}. "
                       f"FA-DSCR after maintenance capex (depreciation proxy), 3-yr: {_f(s.get('fa_dscr_maint_3y'), '{:.2f}x')}.")
        cols = ["period_end", "cfo", "payables_stretch", "exceptional_gain_deducted", "noncore_income_deducted", "cfo_adj",
                "interest_addback", "cfads", "interest_paid", "principal_repaid", "lease_payments", "debt_service",
                "fa_dscr", "reported_dscr", "fa_dscr_after_maint", "borrowings_raised", "refi_dependence", "minsky_state"]
        st.dataframe(a[cols].rename(columns={"period_end": "FY end"}), hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%.2f") for c in
                                    ("fa_dscr", "reported_dscr", "fa_dscr_after_maint", "refi_dependence")} |
                                   {c: st.column_config.NumberColumn(format="%,.0f") for c in cols[1:12] + ["borrowings_raised"]})

    # ---------------------------------------------------------------- Minsky
    with tabs[1]:
        fig = charts.minsky_history(a, P)
        if fig is None:
            st.write("No Minsky states.")
        else:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption("Badges: H Hedge (cash ≥ interest + repayments), S Speculative (cash ≥ interest only), "
                       "P Ponzi (cash < interest). Cash = forensic-adjusted CFADS.")
            st.markdown(f"**3-year path:** {s.get('minsky_path', '')} · **Migration:** {s.get('migration') or 'n/a'} "
                        f"(latest vs mean of the previous {cfg.migration_years} years)")

    # ---------------------------------------------------------------- Breach Clock
    with tabs[2]:
        qd = res.quarters[res.quarters.symbol == sym]
        drow = res.debt[res.debt.symbol == sym]
        debt = np.nan
        if len(drow):
            debt = drow.iloc[0]["total_borrowings"]
            if cfg.debt_measure == "net":
                debt = debt - (drow.iloc[0].get("cash_and_equivalents") or 0)
        f = cached_fan(CTX["tok"], CTX["cfg_json"], sym, qd, debt, cfg) if len(qd) else None
        if s.get("breach_status") == "already_in_breach":
            st.error(f"Already outside covenant on the latest actual TTM figures: ICR {_f(s.get('breach_icr_now'), '{:.2f}x')}, "
                     f"Debt/EBITDA {_f(s.get('breach_debt_ebitda_now'), '{:.2f}x', 'n/a (EBITDA ≤ 0)')}.", icon="⛔")
        if f is None:
            st.info(f"Breach Clock not simulated ({s.get('breach_status')}): needs at least 8 quarters of EBITDA and interest.")
        else:
            scen = st.radio("Scenario", ["base", "stress"], horizontal=True,
                            format_func={"base": "Baseline", "stress": f"Stress (EBITDA −{cfg.stress_ebitda_haircut:.0%}, "
                                                                     f"interest +{cfg.stress_interest_uplift:.0%}, no growth drift)"}.get)
            c1, c2 = st.columns(2)
            c1.plotly_chart(charts.fan_chart(f, "icr", scen, cfg.icr_min, P, True), width="stretch",
                            config={"displayModeBar": False})
            c2.plotly_chart(charts.fan_chart(f, "de", scen, cfg.debt_ebitda_max, P, False), width="stretch",
                            config={"displayModeBar": False})
            st.plotly_chart(charts.breach_curve(f, P, cfg.breach_window_q), width="stretch",
                            config={"displayModeBar": False})
            st.caption(f"{cfg.n_paths:,} simulated paths: each future quarter = the same quarter a year earlier plus a "
                       f"year-on-year change drawn from the last 13 quarters (EBITDA and interest drawn together). Debt held at "
                       f"Rs {f['debt']:,.0f} Cr (latest balance sheet) because Screener has no quarterly debt. "
                       "Values beyond the chart range are drawn at the edge.")

    # ---------------------------------------------------------------- red flags
    with tabs[3]:
        if not flags:
            st.success("No red flags.", icon="✅")
        for fl in flags:
            icon, lbl = SEV[fl["severity"]]
            st.markdown(f"{icon} **{lbl}** — {fl['text']}  \n<span style='opacity:.65;font-size:.85rem'>"
                        f"Source: {fl['source']}</span>", unsafe_allow_html=True)

    # ---------------------------------------------------------------- peers
    with tabs[4]:
        uni = sc[sc.in_universe.fillna(True) | (sc.symbol == sym)]
        b = benchmark(uni, sym)
        n_sec = int((uni.sector == s["sector"]).sum())
        st.caption(f"Sector = NSE industry '{s['sector']}' ({n_sec} companies); universe = {len(uni)} companies.")
        if n_sec < 4:
            st.warning("Fewer than 4 companies in this sector: sector percentiles are not meaningful.", icon="⚠️")
        fig = charts.percentile_dots(b, P)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        if len(b):
            tb = pd.DataFrame({
                "Metric": b.label, "Better if": b.higher_is_better.map({True: "higher", False: "lower"}),
                "Company": [_f(v, f) for v, f in zip(b.value, b.fmt)],
                "Sector median": [_f(v, f) for v, f in zip(b.sector_median, b.fmt)],
                "Universe median": [_f(v, f) for v, f in zip(b.universe_median, b.fmt)],
                "Sector pct": b.sector_pct.round(0), "Universe pct": b.universe_pct.round(0)})
            st.dataframe(tb, hide_index=True, width="stretch")
        peers = uni[uni.sector == s["sector"]].sort_values("rts")
        st.markdown("**Sector peers**")
        st.dataframe(pd.DataFrame({"Company": peers.company_name, "Class": peers.rts_class, "RTS": peers.rts.round(0),
                                   "FA-DSCR 3y": peers.fa_dscr_3y.round(2), "Minsky": peers.minsky_state,
                                   "P breach 4q": (peers.p_breach_base * 100).round(0)}),
                     hide_index=True, width="stretch",
                     column_config={"P breach 4q": st.column_config.NumberColumn(format="%.0f%%")})

    # ---------------------------------------------------------------- source lines
    with tabs[5]:
        cl = ld["cl"]
        src = cl[(cl.symbol == sym) & (cl.basis_role == "primary")].sort_values(["frequency", "period_end", "field"])
        st.caption("Every number used, with the Screener line it came from, any flag, the request URL and fetch time.")
        fr = st.multiselect("Frequency", sorted(src.frequency.unique()), default=[x for x in ("FY",) if x in set(src.frequency)])
        st.dataframe(src[src.frequency.isin(fr)] if fr else src, hide_index=True, width="stretch",
                     column_config={"source_url": st.column_config.LinkColumn("source_url")})
        st.download_button(f"Calculation workbook for {sym} (.xlsx)",
                           CTX["cached_workbook"](CTX["tok"], CTX["cfg_json"], (sym,)),
                           f"RTS_calculation_{sym}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("Formulas calculate when the file is opened in Excel. The Breach Clock probabilities are Python "
                   "Monte Carlo values with the seed recorded.")

    # ---------------------------------------------------------------- AI
    with tabs[6]:
        from views.ai_tab import render_ai_tab
        uni_ai = sc[sc.in_universe.fillna(True) | (sc.symbol == sym)]
        render_ai_tab(s, last, cfg, benchmark(uni_ai, sym), CTX["cfg_json"])


render()
