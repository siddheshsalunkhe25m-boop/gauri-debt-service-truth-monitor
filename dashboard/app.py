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


def _purge_stale_code():
    """Streamlit Cloud pulls new commits into a running server and re-runs app.py, but modules imported earlier
    (data, live, dstm_*) stay in memory at the old version. If any .py file in the project changed since they were
    loaded, drop them so the imports below load the new code."""
    import sys as _sys
    root = Path(__file__).resolve().parent.parent
    stamp = max((p.stat().st_mtime_ns for p in root.rglob("*.py") if ".git" not in p.parts), default=0)
    if getattr(_sys, "_dstm_code_stamp", None) != stamp:
        for name, mod in list(_sys.modules.items()):
            f = getattr(mod, "__file__", None) or ""
            if f and Path(f).resolve().is_relative_to(root) and Path(f).resolve() != Path(__file__).resolve():
                del _sys.modules[name]
        _sys._dstm_code_stamp = stamp


_purge_stale_code()
import charts  # noqa: E402
import data  # noqa: E402
import live  # noqa: E402
from ctx import CTX, PAGES  # noqa: E402
from dstm_rts.config import RTSConfig  # noqa: E402

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
QUICK_START = ["TATASTEEL", "JSWSTEEL", "TMPV", "ADANIPORTS", "NTPC", "LT", "BHARTIARTL", "SUNPHARMA",
               "VEDL", "INDIGO", "ZEEL", "COFFEEDAY"]


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


def live_status_panel(where):
    """Progress of the background live fetch. Re-draws itself every 2 s while a fetch runs; when the fetch ends it
    reloads the whole app once so every page shows the new figures."""
    job = live.JOB

    def body():
        s = job.snapshot()
        seen = st.session_state.get("live_seen_version", s.get("version", 0))
        if not s.get("running") and s.get("version", 0) > seen:
            st.session_state["live_seen_version"] = s["version"]
            st.session_state["live_result"] = {k: s.get(k) for k in ("ok", "message", "failures")}
            st.cache_data.clear()
            st.rerun(scope="app")
        st.session_state.setdefault("live_seen_version", s.get("version", 0))
        if s.get("running"):
            n, i = s["n"], s.get("i", 0)
            st.progress(min(i / max(n, 1), 1.0),
                        f"Live fetch: {i}/{n} companies · {live.fmt_secs(s['elapsed_s'])} elapsed · "
                        f"~{live.fmt_secs(s['eta_s'])} left")
            st.caption(f"{s.get('label', '')} — now: {str(s.get('current', ''))[:90]}")
            st.caption("Runs on the server: you can keep working, switch pages or close this tab; the dashboard "
                       "switches to the new figures when it finishes.")
            c1, c2 = st.columns(2)
            if c1.button("Show fetched so far", key=f"partial_{where}", width="stretch",
                         help="Re-score now with the companies already fetched; the fetch keeps running."):
                with job._lock:
                    job.state["frozen_token"] = data._raw_token()
                st.cache_data.clear()
                st.rerun(scope="app")
            if c2.button("Stop", key=f"stop_{where}", width="stretch"):
                job.stop()
        res = st.session_state.get("live_result")
        if res and not s.get("running"):
            (st.success if res.get("ok") else st.error)(res.get("message", ""))
            if res.get("failures"):
                st.dataframe(pd.DataFrame(res["failures"]), hide_index=True, height=150)
    st.fragment(body, run_every=2 if job.running else None)()


def start_live(symbols: list[str], label: str):
    ok, msg = live.JOB.start(symbols, label)
    if not ok:
        st.warning(msg)
    else:
        st.session_state.pop("live_result", None)
        st.rerun()


def sidebar_data(ld: dict, tok: str, scores: pd.DataFrame):
    sb = st.sidebar
    sb.markdown("### Debt-Service Truth Monitor")
    badge = {"live cache": "🟢 Live from Screener", "live + snapshot": "🟢 Live + 🟡 snapshot",
             "offline snapshot": "🟡 Offline snapshot", "synthetic demo": "🔴 SYNTHETIC demo"}[ld["source"]]
    extra = ""
    if ld["source"] == "live + snapshot":
        extra = (f"  \n**Fetched live:** {len(ld.get('live_symbols', []))} companies · rest from snapshot of "
                 f"{fmt_asof(ld.get('snapshot_as_of', ''))}")
    sb.markdown(f"**Data:** {badge}  \n**Latest fetch:** {fmt_asof(ld['as_of'])}  \n"
                f"**Companies:** {scores.symbol.nunique()}{extra}")
    for w in ld["warnings"]:
        sb.warning(w, icon="⚠️")

    with sb.expander("🔄 Live Screener data", expanded=ld["demo"] or live.JOB.running):
        live_status_panel("sidebar")
        if not live.JOB.running:
            st.caption("Fetches the latest published figures from Screener.in now (public pages, 1 request per "
                       "second, about 13 s per company) and re-scores everything.")
            uni = data.universe_choices()
            label = dict(zip(uni.symbol, uni.symbol + " · " + uni.company_name.fillna("")))
            mode = st.radio("Fetch", ["pick", "stale", "all"], key="lmode",
                            format_func={"pick": "Chosen companies", "stale": "Missing / older than 7 days",
                                         "all": "Entire universe"}.get)
            if mode == "pick":
                default = [x for x in st.session_state.get("lpick_default", []) if x in label]
                syms = st.multiselect("Companies", list(label), default=default, key="lpick",
                                      format_func=lambda x: label.get(x, x),
                                      placeholder="Type a name or NSE symbol")
            elif mode == "stale":
                syms = data.stale_symbols(ld)
            else:
                syms = list(uni.symbol)
            st.caption(f"{len(syms)} companies · about {live.fmt_secs(len(syms) * live.SECONDS_PER_COMPANY)}")
            if st.button("Fetch live from Screener", type="primary", width="stretch", disabled=not syms):
                start_live(syms, {"pick": "Chosen companies", "stale": "Missing/stale companies",
                                  "all": "Entire universe"}[mode])

    with sb.expander("Import browser capture", expanded=False):
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
                P=charts.pal(is_dark()), cached_workbook=cached_workbook, fmt_asof=fmt_asof,
                start_live=start_live, live_panel=live_status_panel))

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
             "number on this screen. Load real figures with **🔄 Live Screener data** in the sidebar.",
             icon="🛑")
    if not live.JOB.running:
        c1, c2, _ = st.columns([1.2, 1.2, 1.6])
        n_all = len(data.universe_choices())
        if c1.button(f"Fetch all {n_all} companies live (~{live.fmt_secs(n_all * live.SECONDS_PER_COMPANY)})",
                     type="primary", width="stretch"):
            start_live(list(data.universe_choices().symbol), "Entire universe")
        if c2.button("Quick start: 12 companies (~3 min)", width="stretch",
                     help="A few names per sector plus the stressed case studies, to see real output fast."):
            start_live(QUICK_START, "Quick start")
pg.run()
