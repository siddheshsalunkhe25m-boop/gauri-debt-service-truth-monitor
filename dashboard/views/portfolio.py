"""Landing page: portfolio view."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import charts
import data
from ctx import CTX, PAGES
from dstm_rts.metrics import migration_matrices

CLASS_ICON = {"Safe": "✅", "Watch": "⚠️", "Escalate": "⛔", "Insufficient data": "▫️"}


def open_company(sym: str):
    st.session_state["symbol"] = sym
    st.switch_page(PAGES["company"])


def tile(col, label, n, total, status, icon):
    color = charts.STATUS.get(status, "#898781")
    share = f"{n / total:.0%} of companies" if total else ""
    col.markdown(
        f"""<div style="border:1px solid rgba(137,135,129,.35);border-radius:8px;padding:12px 14px">
        <div style="font-size:.85rem;opacity:.8"><span style="display:inline-block;width:10px;height:10px;
        border-radius:50%;background:{color};margin-right:6px"></span>{icon} {label}</div>
        <div style="font-size:2rem;font-weight:600;line-height:1.2">{n}</div>
        <div style="font-size:.8rem;opacity:.7">{share}</div></div>""", unsafe_allow_html=True)


def render():
    res, cfg, P = CTX["res"], CTX["cfg"], CTX["P"]
    sc = res.scores.copy()
    st.title("Portfolio")
    st.caption(f"Repayment Truth Score for non-financial Nifty 200 borrowers · covenants ICR ≥ {cfg.icr_min:.2f}x, "
               f"Debt/EBITDA ≤ {cfg.debt_ebitda_max:.2f}x · weights FA-DSCR {cfg.weights['dscr']:.0%}, Minsky "
               f"{cfg.weights['minsky']:.0%}, refinancing {cfg.weights['refi']:.0%}, Breach Clock {cfg.weights['breach']:.0%}")
    v = data.validation_status()
    if not v["done"] or v.get("synthetic"):
        st.info("RTS has **not yet been back-tested on real data** (see Method & data). Treat classes as a structured "
                "first read for the analyst, not as a validated prediction.", icon="ℹ️")

    # ---------------------------------------------------------------- filters
    f1, f2, f3 = st.columns([2, 2, 1])
    sectors = sorted(sc.sector.dropna().unique())
    pick_sec = f1.multiselect("Sector", sectors, placeholder="All sectors")
    pick_cls = f2.multiselect("Class", ["Escalate", "Watch", "Safe", "Insufficient data"], placeholder="All classes")
    cases = f3.toggle("Include case studies", False, help="Stressed names outside the Nifty 200 (Coffee Day, ZEEL, ...)")
    d = sc if cases else sc[sc.in_universe.fillna(True)]
    if pick_sec:
        d = d[d.sector.isin(pick_sec)]
    if pick_cls:
        d = d[d.rts_class.isin(pick_cls)]

    # ---------------------------------------------------------------- class counts
    cnt = d.rts_class.value_counts()
    cols = st.columns(4)
    for c, (lbl, status) in zip(cols, [("Safe", "good"), ("Watch", "warning"), ("Escalate", "critical"),
                                       ("Insufficient data", None)]):
        tile(c, lbl, int(cnt.get(lbl, 0)), len(d), status, CLASS_ICON[lbl])
    st.write("")

    # ---------------------------------------------------------------- top 10 to review today
    st.subheader("Top 10 to review today")
    st.caption("Order: Escalate before Watch before Safe; then already in breach, highest baseline breach probability, "
               "downward Minsky migration, lowest RTS.")
    top = data.review_priority(d).head(10)
    if top.empty:
        st.write("No companies match the filters.")
    for i, r in enumerate(top.itertuples(index=False), 1):
        c = st.columns([0.35, 2.2, 1.1, 0.8, 1.0, 4.2, 0.9])
        c[0].markdown(f"**{i}**")
        c[1].markdown(f"**{r.company_name}**  \n<span style='opacity:.7'>{r.symbol} · {r.sector}</span>",
                      unsafe_allow_html=True)
        c[2].markdown(f"{CLASS_ICON.get(r.rts_class, '')} **{r.rts_class}**")
        c[3].markdown(f"RTS **{r.rts:.0f}**" if pd.notna(r.rts) else "RTS –")
        c[4].markdown(f"P(breach 4q) **{r.p_breach_base:.0%}**" if pd.notna(r.p_breach_base) else "P(breach) –")
        c[5].markdown(f"<span style='font-size:.9rem'>{r.why}</span>", unsafe_allow_html=True)
        if c[6].button("Open →", key=f"open_{r.symbol}"):
            open_company(r.symbol)

    st.divider()
    # ---------------------------------------------------------------- portfolio table sorted by Breach Clock
    st.subheader("Portfolio sorted by Breach Clock")
    st.caption("Sorted by: already in breach, then probability of a covenant breach within 4 quarters (baseline, then "
               "stress), then median quarters to breach. Click a row to open the company.")
    t = d.copy()
    t["_now"] = (t.breach_status == "already_in_breach").astype(int)
    t = t.sort_values(["_now", "p_breach_base", "p_breach_stress", "median_q_base", "rts"],
                      ascending=[False, False, False, True, True], na_position="last")
    show = pd.DataFrame({
        "Company": t.company_name, "Symbol": t.symbol, "Sector": t.sector,
        "Class": t.rts_class.map(lambda c: f"{CLASS_ICON.get(c, '')} {c}"),
        "RTS": t.rts.round(0),
        "P breach 4q (base)": (t.p_breach_base * 100).round(0),
        "P breach 4q (stress)": (t.p_breach_stress * 100).round(0),
        "Median qtrs to breach": t.apply(lambda r: "now" if r._now else (
            f">{cfg.horizon_q}" if r.breach_status == "ok" and pd.isna(r.median_q_base) else
            ("" if pd.isna(r.median_q_base) else f"{r.median_q_base:.0f}")), axis=1),
        "ICR now": t.breach_icr_now.replace([np.inf], np.nan).round(1),
        "Debt/EBITDA now": t.breach_debt_ebitda_now.replace([np.inf], np.nan).round(1),
        "Minsky": t.minsky_state.fillna("") + t.migration.map(lambda m: f" ({m})" if isinstance(m, str) else ""),
        "FA-DSCR 3y": t.fa_dscr_3y.round(2), "Reported DSCR 3y": t.reported_dscr_3y.round(2),
        "Refinancing": (t.refi_dependence_3y * 100).round(0),
        "Clock status": t.breach_status,
    })
    ev = st.dataframe(
        show, hide_index=True, width="stretch", height=420, on_select="rerun", selection_mode="single-row",
        key="pf_table",
        column_config={
            "RTS": st.column_config.ProgressColumn("RTS", min_value=0, max_value=100, format="%.0f"),
            "P breach 4q (base)": st.column_config.ProgressColumn("P breach 4q (base)", min_value=0, max_value=100,
                                                                  format="%.0f%%"),
            "P breach 4q (stress)": st.column_config.NumberColumn(format="%.0f%%"),
            "Refinancing": st.column_config.NumberColumn("Refinancing dep.", format="%.0f%%"),
            "ICR now": st.column_config.NumberColumn(format="%.1fx"),
            "Debt/EBITDA now": st.column_config.NumberColumn(format="%.1fx"),
            "FA-DSCR 3y": st.column_config.NumberColumn(format="%.2fx"),
            "Reported DSCR 3y": st.column_config.NumberColumn(format="%.2fx"),
        })
    if ev and ev.selection and ev.selection.rows:
        open_company(show.iloc[ev.selection.rows[0]]["Symbol"])

    st.divider()
    # ---------------------------------------------------------------- Minsky migration
    st.subheader("Minsky migration")
    syms = list(d.symbol)
    ann = res.annual[res.annual.symbol.isin(syms)]
    if ann.empty or ann.minsky_state.isna().all():
        st.write("No Minsky states for the selected companies.")
        return
    mats = migration_matrices(ann, cfg.migration_years)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.transition_heatmap(mats["one_year_counts"], P,
                                              "Year-to-year transitions (all company-years)"),
                    width="stretch", config={"displayModeBar": False})
    c2.plotly_chart(charts.transition_heatmap(mats[f"{cfg.migration_years}_year_counts"], P,
                                              f"Latest year vs {cfg.migration_years} years earlier"),
                    width="stretch", config={"displayModeBar": False})
    st.caption("Rows: state at the start; columns: state at the end. Cells: number of companies and row share. "
               "Hedge = adjusted cash covers interest + repayments; Speculative = covers interest only; "
               "Ponzi = does not cover interest.")
    with st.expander("State history by company (H / S / P)", expanded=False):
        order = d.assign(_o=d.minsky_state.map({"Ponzi": 0, "Speculative": 1, "Hedge": 2})).sort_values(["_o", "rts"]).symbol
        fig = charts.state_grid(res.annual, list(order), P, max_rows=60)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            st.caption("Green H = Hedge, amber S = Speculative, red P = Ponzi. Worst latest state first; up to 60 companies.")


render()
