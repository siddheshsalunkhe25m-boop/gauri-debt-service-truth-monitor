"""Debt-Service Truth Monitor - credit analyst dashboard.

Run from the project folder:   streamlit run dashboard/app.py      (Windows: double-click run_dashboard.bat)
"""
from __future__ import annotations

import io
import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

import charts
import data
from ctx import CTX, PAGES
from dstm_rts.config import RTSConfig

st.set_page_config(page_title="Gauri · Debt-Service Truth Monitor", page_icon="📉", layout="wide")

# Hosted on Streamlit Community Cloud: secrets (App settings > Secrets) become environment variables, so the AI
# layer reads ANTHROPIC_API_KEY / DSTM_AI_MODEL exactly as it does locally. Nothing is written to disk.
try:
    import os
    for _k in ("ANTHROPIC_API_KEY", "DSTM_AI_MODEL"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:          # no secrets file locally
    pass


# ------------------------------------------------------------------ cached computations
@st.cache_data(show_spinner=False)
def cached_load(tok: str) -> dict:
    return data.load_credit_lines()


@st.cache_data(show_spinner="Scoring companies…")
def cached_compute(tok: str, cfg_json: str):
    ld = cached_load(tok)
    meta = data.universe_meta(ld["cl"], ld["demo"])
    return data.compute(ld["cl"], RTSConfig(**json.loads(cfg_json)), meta), meta


@st.cache_data(show_spinner="Building calculation workbook…")
def cached_workbook(tok: str, cfg_json: str, symbols: tuple | None) -> bytes:
    from dstm_rts.engine import run_rts
    from dstm_rts.workbook import build_workbook
    ld = cached_load(tok)
    cl = ld["cl"] if symbols is None else ld["cl"][ld["cl"].symbol.isin(symbols)]
    res = run_rts(cl, RTSConfig(**json.loads(cfg_json)))
    note = ("SYNTHETIC DEMO DATA - not real companies" if ld["demo"] else
            f"Source: Screener.in ({ld['source']}, data as of {ld['as_of']})")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "RTS_calculation.xlsx"
        build_workbook(res, cl, str(p), note)
        return p.read_bytes()


def is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


# ------------------------------------------------------------------ settings -> config
DEFAULT = RTSConfig()


def sidebar_settings() -> RTSConfig:
    with st.sidebar.expander("Model settings", expanded=False):
        st.caption("Covenants (tested quarterly on trailing-twelve-month figures)")
        c1, c2 = st.columns(2)
        icr = c1.number_input("Min interest cover", 1.0, 6.0, DEFAULT.icr_min, 0.25, format="%.2f", key="icr")
        de = c2.number_input("Max Debt/EBITDA", 1.0, 8.0, DEFAULT.debt_ebitda_max, 0.25, format="%.2f", key="de")
        st.caption("RTS weights (re-normalised to 100%)")
        w = [st.slider(lbl, 0, 100, int(v * 100), 5, key=k) for lbl, v, k in (
            ("FA-DSCR", DEFAULT.w_dscr, "w1"), ("Minsky state / migration", DEFAULT.w_minsky, "w2"),
            ("Refinancing dependence", DEFAULT.w_refi, "w3"), ("Breach Clock", DEFAULT.w_breach, "w4"))]
        if sum(w) == 0:
            st.error("All weights are zero: using the defaults.")
            w = [35, 25, 20, 20]
        c1, c2 = st.columns(2)
        safe = c1.number_input("Safe if RTS ≥", 50.0, 95.0, DEFAULT.safe_min, 5.0, key="safe")
        watch = c2.number_input("Watch if RTS ≥", 20.0, 80.0, DEFAULT.watch_min, 5.0, key="watch")
        if watch >= safe:
            st.error("Watch cut-off must be below the Safe cut-off; using defaults.")
            safe, watch = DEFAULT.safe_min, DEFAULT.watch_min
        st.caption("Judgement calls (see Method page)")
        addback = st.selectbox("Interest add-back", ["auto", "always", "never"], key="addback",
                               help="auto: add back only interest paid inside CFO (avoids double counting). "
                                    "always: the literal textbook formula.")
        lease = st.checkbox("Lease payments count as repayments", True, key="lease")
        debt = st.selectbox("Debt measure for the Breach Clock", ["gross", "net"], key="debtm")
        paths = st.select_slider("Monte Carlo paths", [2000, 5000, 10000], value=10000, key="paths")
        if st.button("Reset to defaults"):
            for k in ("icr", "de", "w1", "w2", "w3", "w4", "safe", "watch", "addback", "lease", "debtm", "paths"):
                st.session_state.pop(k, None)
            st.rerun()
    return replace(DEFAULT, icr_min=icr, debt_ebitda_max=de, w_dscr=w[0] / 100, w_minsky=w[1] / 100,
                   w_refi=w[2] / 100, w_breach=w[3] / 100, safe_min=safe, watch_min=watch, interest_addback=addback,
                   include_lease_payments=lease, debt_measure=debt, n_paths=paths)


def fmt_asof(s: str) -> str:
    try:
        return pd.Timestamp(s).tz_convert("Asia/Kolkata").strftime("%d %b %Y, %H:%M IST")
    except Exception:
        try:
            return pd.Timestamp(s).strftime("%d %b %Y")
        except Exception:
            return str(s)


def sidebar_data(ld: dict, tok: str, scores: pd.DataFrame):
    sb = st.sidebar
    sb.markdown("### Debt-Service Truth Monitor")
    badge = {"live cache": "🟢 Live cache", "offline snapshot": "🟡 Offline snapshot",
             "synthetic demo": "🔴 SYNTHETIC demo"}[ld["source"]]
    sb.markdown(f"**Data:** {badge}  \n**As of:** {fmt_asof(ld['as_of'])}  \n**Companies:** {scores.symbol.nunique()}")
    for w in ld["warnings"]:
        sb.warning(w, icon="⚠️")

    with sb.expander("Refresh live data", expanded=False):
        st.caption("Fetches Screener.in (public pages, 1 request/second). If the site cannot be reached, "
                   "nothing changes and the cached data stays on screen.")
        mode = st.radio("What to refresh", ["stale", "one", "all"], key="rmode", horizontal=True,
                        format_func={"stale": "Stale only (>7 days)", "one": "One company", "all": "Everything"}.get)
        sym = None
        if mode == "one":
            sym = st.selectbox("Company", sorted(scores.symbol), key="rsym")
        cases = st.checkbox("Include case-study companies", True, key="rcases")
        if mode == "all":
            st.info("A full refresh is ~20 requests per company: roughly an hour for the universe.")
        if st.button("Refresh live data", type="primary", width="stretch"):
            bar = st.progress(0.0, "Checking Screener.in…")
            out = data.refresh_live(mode, sym, cases,
                                    progress=lambda i, n, m: bar.progress(min(i / max(n, 1), 1.0), m[:80]))
            bar.empty()
            (st.success if out["ok"] else st.error)(out["message"])
            if out.get("failures") is not None and len(out["failures"]):
                st.dataframe(out["failures"][["symbol", "status"]], hide_index=True)
            if out["ok"]:
                st.cache_data.clear()
                st.session_state["refreshed"] = out["message"]
                st.rerun()

    with sb.expander("Import browser capture", expanded=ld["demo"]):
        st.caption("Use when Python cannot reach Screener.in: load the file saved by tools/capture_screener.js "
                   "(e.g. dstm_capture_full.json.gz). It is replayed through the same pipeline.")
        up = st.file_uploader("Capture file", type=["json", "gz"], key="cap")
        if up is not None and st.button("Import", width="stretch"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json.gz" if up.name.endswith(".gz") else ".json") as f:
                f.write(up.getbuffer())
                path = Path(f.name)
            bar = st.progress(0.0, "Importing…")
            out = data.import_capture(path, progress=lambda i, n, m: bar.progress(min(i / max(n, 1), 1.0), m[:80]))
            bar.empty()
            (st.success if out["ok"] else st.error)(out["message"])
            if out["ok"]:
                st.cache_data.clear()
                st.session_state["refreshed"] = out["message"]
                st.rerun()


def sidebar_downloads(tok, cfg_json, scores):
    with st.sidebar.expander("Downloads", expanded=False):
        st.download_button("Scores (CSV)", scores.to_csv(index=False).encode(), "rts_scores.csv", "text/csv",
                           width="stretch")
        st.caption("Calculation workbook: every input links to its Screener source line; every step is a live formula.")
        if st.button("Prepare full calculation workbook", width="stretch"):
            st.session_state["wb_ready"] = True
        if st.session_state.get("wb_ready"):
            st.download_button("Download RTS_calculation.xlsx", cached_workbook(tok, cfg_json, None),
                               "RTS_calculation.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               width="stretch")
        st.download_button("Model settings (JSON)", cfg_json.encode(), "rts_config.json", "application/json",
                           width="stretch")


# ------------------------------------------------------------------ main
tok = data.token()
ld = cached_load(tok)
cfg = sidebar_settings()
cfg_json = data.cfg_to_json(cfg)
res, meta = cached_compute(tok, cfg_json)
sidebar_data(ld, tok, res.scores)
sidebar_downloads(tok, cfg_json, res.scores)

CTX.update(dict(ld=ld, tok=tok, cfg=cfg, cfg_json=cfg_json, res=res, meta=meta, dark=is_dark(),
                P=charts.pal(is_dark()), cached_workbook=cached_workbook, fmt_asof=fmt_asof))

HERE = Path(__file__).parent
PAGES["portfolio"] = st.Page(str(HERE / "views" / "portfolio.py"), title="Portfolio", icon="📋", url_path="portfolio",
                             default=True)
PAGES["company"] = st.Page(str(HERE / "views" / "company.py"), title="Company drill-down", icon="🔎", url_path="company")
PAGES["method"] = st.Page(str(HERE / "views" / "method.py"), title="Method & data", icon="📐", url_path="method")
pg = st.navigation(list(PAGES.values()))
if st.session_state.get("refreshed"):
    st.toast(st.session_state.pop("refreshed"))
if ld["demo"]:
    st.error("**SYNTHETIC DEMO DATA.** These are generated companies (SYN###), not Screener data. Do not use any "
             "number on this screen. Load real data with *Refresh live data* or *Import browser capture* (sidebar).",
             icon="🛑")
pg.run()
