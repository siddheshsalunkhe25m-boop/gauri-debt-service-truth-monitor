"""Data access for the dashboard: where the numbers come from, caching, refresh and offline fallback.

Source order (first that works wins, and the sidebar always says which one is showing):
  1. Live cache   data/dstm.db (credit_lines written by dstm_data; updated by "Refresh live data")
  2. Snapshot     dashboard/snapshot/credit_lines.parquet (copy of the last good cache, written after
                  every successful load, so a corrupt or deleted DB still opens)
  3. Demo         SYNTHETIC companies (SYN###) - only when neither exists; shown with a red banner
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from dstm_data.config import USER_AGENT, Settings          # noqa: E402
from dstm_data.pipeline import Pipeline                     # noqa: E402
from dstm_data.universe import load_universe                # noqa: E402
from dstm_rts.config import RTSConfig                       # noqa: E402
from dstm_rts.engine import run_rts                         # noqa: E402

import os                                                    # noqa: E402

UNIVERSE_CSV = ROOT / "ind_nifty200list.csv"


def _sync():
    """Resolve folders from the environment on every call (DSTM_DATA_DIR / DSTM_SNAPSHOT_DIR override the defaults)."""
    global DATA_DIR, DB, SNAP_DIR, SNAP, SNAP_META, VALIDATION_DIR
    DATA_DIR = Path(os.environ.get("DSTM_DATA_DIR", ROOT / "data"))
    DB = DATA_DIR / "dstm.db"
    SNAP_DIR = Path(os.environ.get("DSTM_SNAPSHOT_DIR", ROOT / "dashboard" / "snapshot"))
    SNAP = SNAP_DIR / "credit_lines.parquet"
    SNAP_META = SNAP_DIR / "meta.json"
    VALIDATION_DIR = DATA_DIR / "validation"


_sync()
CASE_SYMBOLS = ["COFFEEDAY", "ZEEL", "RCOM", "JETAIRWAYS", "SUNTV"]
CASE_SECTOR = "Case study (outside Nifty 200)"
DEMO_SECTORS = ["Capital Goods", "Metals & Mining", "Power", "Automobile and Auto Components", "Healthcare",
                "Consumer Services", "Oil Gas & Consumable Fuels", "Information Technology"]


# ------------------------------------------------------------------ source detection
def token() -> str:
    """Changes whenever the underlying data changes: used as the cache key."""
    _sync()
    parts = []
    for p in (DB, SNAP):
        parts.append(f"{p.name}:{p.stat().st_mtime_ns if p.exists() else 0}")
    return "|".join(parts)


def _read_db() -> pd.DataFrame:
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
        return pd.read_sql_query("SELECT * FROM credit_lines", con)


def _write_snapshot(cl: pd.DataFrame, as_of: str):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SNAP.with_suffix(".tmp")
    try:
        cl.to_parquet(tmp, index=False)
    except (ImportError, ValueError):
        return
    tmp.replace(SNAP)
    SNAP_META.write_text(json.dumps({"as_of": as_of, "rows": len(cl), "symbols": int(cl.symbol.nunique()),
                                     "written": time.strftime("%Y-%m-%d %H:%M:%S")}))


def load_credit_lines() -> dict:
    _sync()
    warnings = []
    if DB.exists():
        try:
            cl = _read_db()
            if len(cl):
                as_of = str(cl["fetched_at"].dropna().max()) if "fetched_at" in cl else "unknown"
                snap_t = SNAP.stat().st_mtime if SNAP.exists() else 0
                if DB.stat().st_mtime > snap_t:
                    _write_snapshot(cl, as_of)
                return {"cl": cl, "source": "live cache", "as_of": as_of, "warnings": warnings, "demo": False}
            warnings.append("Local cache is empty.")
        except Exception as e:                                      # corrupt / locked / old schema
            warnings.append(f"Local cache could not be read ({type(e).__name__}); using the offline snapshot.")
    if SNAP.exists():
        try:
            cl = pd.read_parquet(SNAP)
            meta = json.loads(SNAP_META.read_text()) if SNAP_META.exists() else {}
            return {"cl": cl, "source": "offline snapshot", "as_of": meta.get("as_of", "unknown"),
                    "warnings": warnings, "demo": False}
        except Exception as e:
            warnings.append(f"Offline snapshot could not be read ({type(e).__name__}).")
    from make_synthetic_history import synthetic_history
    cl, _ = synthetic_history(n=40, seed=5)
    warnings.append("No Screener data found: showing SYNTHETIC demo companies. Use 'Refresh live data' or "
                    "'Import browser capture' in the sidebar.")
    return {"cl": cl, "source": "synthetic demo", "as_of": "n/a", "warnings": warnings, "demo": True}


def universe_meta(cl: pd.DataFrame, demo: bool) -> pd.DataFrame:
    syms = sorted(cl.symbol.unique())
    if demo:
        return pd.DataFrame({"symbol": syms, "company_name": [f"Synthetic Co {s[3:]}" for s in syms],
                             "sector": [DEMO_SECTORS[i % len(DEMO_SECTORS)] for i in range(len(syms))],
                             "in_universe": True})
    try:
        u = load_universe(UNIVERSE_CSV, non_financial_only=True)[["symbol", "company_name", "industry"]]
    except Exception:
        u = pd.DataFrame(columns=["symbol", "company_name", "industry"])
    u = u.rename(columns={"industry": "sector"})
    u["in_universe"] = True
    extra = [s for s in syms if s not in set(u.symbol)]
    u = pd.concat([u, pd.DataFrame({"symbol": extra, "company_name": extra, "sector": CASE_SECTOR,
                                    "in_universe": False})], ignore_index=True)
    return u[u.symbol.isin(syms)].reset_index(drop=True)


def compute(cl: pd.DataFrame, cfg: RTSConfig, meta: pd.DataFrame):
    res = run_rts(cl, cfg)
    sc = res.scores.merge(meta, on="symbol", how="left")
    sc["sector"] = sc["sector"].fillna("Unknown")
    sc["company_name"] = sc["company_name"].fillna(sc["symbol"])
    res.scores = sc
    return res


def review_priority(sc: pd.DataFrame) -> pd.DataFrame:
    """Ranking for 'review today': class (Escalate > Watch > Safe), already in breach, baseline breach probability,
    downward Minsky migration, then lowest RTS."""
    d = sc.copy()
    d["_cls"] = d.rts_class.map({"Escalate": 0, "Watch": 1, "Safe": 2}).fillna(3)
    d["_now"] = -(d.get("breach_status", pd.Series(index=d.index)) == "already_in_breach").astype(int)
    d["_pb"] = -d.p_breach_base.fillna(0)
    d["_mig"] = -(d.migration == "deteriorating").astype(int)
    d = d.sort_values(["_cls", "_now", "_pb", "_mig", "rts"]).drop(columns=["_cls", "_now", "_pb", "_mig"])

    def why(r):
        t = (r.triggers or "").split(" | ")[0] if isinstance(r.triggers, str) and r.triggers else ""
        return t.split("] ", 1)[-1] if t else (r.reasons.split(";")[0] if isinstance(r.reasons, str) else "")
    d["why"] = d.apply(why, axis=1)
    return d


def validation_status() -> dict:
    _sync()
    vdir = VALIDATION_DIR if (VALIDATION_DIR / "auc_table.csv").exists() else SNAP_DIR / "validation"
    f = vdir / "auc_table.csv"
    if not f.exists():
        return {"done": False}
    t = pd.read_csv(f)
    run = json.loads((vdir / "run_config.json").read_text()) if (vdir / "run_config.json").exists() else {}
    return {"done": True, "synthetic": run.get("synthetic", False), "auc": t}


# ------------------------------------------------------------------ refresh / import
def reachable(timeout=8) -> tuple[bool, str]:
    try:
        r = requests.get("https://www.screener.in/", headers={"User-Agent": USER_AGENT}, timeout=timeout)
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except requests.RequestException as e:
        return False, type(e).__name__


def _backup():
    if DB.exists():
        shutil.copy2(DB, DB.with_suffix(".db.bak"))


def _restore():
    bak = DB.with_suffix(".db.bak")
    if bak.exists():
        shutil.copy2(bak, DB)


def refresh_live(mode: str, symbol: str | None, include_cases: bool, progress=lambda i, n, msg: None) -> dict:
    """mode: 'stale' | 'one' | 'all'. Backs the DB up first and restores it if the run crashes."""
    _sync()
    ok, why = reachable()
    if not ok:
        return {"ok": False, "message": f"Screener.in not reachable ({why}). Nothing changed; cached data kept."}
    s = Settings(data_dir=DATA_DIR, universe_csv=UNIVERSE_CSV, basis="both")
    uni = load_universe(UNIVERSE_CSV)
    if include_cases:
        uni = pd.concat([uni, pd.DataFrame({"symbol": CASE_SYMBOLS, "company_name": CASE_SYMBOLS,
                                            "industry": CASE_SECTOR})], ignore_index=True)
    if mode == "one":
        uni = uni[uni.symbol == symbol] if symbol in set(uni.symbol) else pd.DataFrame(
            {"symbol": [symbol], "company_name": [symbol], "industry": [None]})
    _backup()
    n = len(uni)
    counter = {"i": 0}

    def prog(msg):
        counter["i"] += 1
        progress(counter["i"], n, msg)
    try:
        p = Pipeline(s)
        res = p.refresh(uni, force=(mode != "stale"), progress=prog)
        p.cache.close()
    except Exception as e:
        _restore()
        return {"ok": False, "message": f"Refresh failed ({type(e).__name__}: {e}); previous cache restored."}
    counts = res["status"].value_counts().to_dict() if len(res) else {}
    bad = res[~res.status.isin(["ok", "fresh_skipped", "excluded_lender"])] if len(res) else res
    return {"ok": True, "message": f"Refresh finished: {counts}", "failures": bad}


def import_capture(path: Path, progress=lambda i, n, msg: None) -> dict:
    """Replay a browser capture (tools/capture_screener.js output, .json or .json.gz) into the cache."""
    _sync()
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        cap = json.load(fh)
    items = cap.get("items", cap)
    syms = sorted({u.split("/company/")[1].split("/")[0] for u in items if "/company/" in u})
    syms = [requests.utils.unquote(x) for x in syms]
    if not syms:
        return {"ok": False, "message": "No company pages found in that file."}
    # full-universe capture fetched only the primary basis; the 10-company capture fetched both
    basis = "primary" if cap.get("meta", {}).get("mode") == "primary" else "both"
    s = Settings(data_dir=DATA_DIR, universe_csv=UNIVERSE_CSV, basis=basis)
    uni = load_universe(UNIVERSE_CSV, non_financial_only=False)
    uni = pd.concat([uni[uni.symbol.isin(syms)],
                     pd.DataFrame({"symbol": [x for x in syms if x not in set(uni.symbol)], "company_name": None,
                                   "industry": CASE_SECTOR})], ignore_index=True)
    _backup()
    n = len(uni)
    counter = {"i": 0}

    def prog(msg):
        counter["i"] += 1
        progress(counter["i"], n, msg)
    try:
        p = Pipeline(s, replay_files=[path])
        res = p.refresh(uni, force=True, progress=prog)
        p.cache.close()
    except Exception as e:
        _restore()
        return {"ok": False, "message": f"Import failed ({type(e).__name__}: {e}); previous cache restored."}
    return {"ok": True, "message": f"Imported {len(syms)} companies from the capture "
                                   f"(basis={basis}): {res['status'].value_counts().to_dict()}",
            "failures": res[~res.status.isin(["ok", "excluded_lender"])]}


def company_status() -> pd.DataFrame:
    _sync()
    if not DB.exists():
        snap = SNAP_DIR / "company_status.parquet"
        return pd.read_parquet(snap) if snap.exists() else pd.DataFrame()
    try:
        with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
            return pd.read_sql_query("SELECT * FROM company_status ORDER BY symbol", con)
    except Exception:
        return pd.DataFrame()


def audit_tail(n=300) -> pd.DataFrame:
    _sync()
    if not DB.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
            return pd.read_sql_query(f"SELECT * FROM audit_log ORDER BY id DESC LIMIT {int(n)}", con)
    except Exception:
        return pd.DataFrame()


def cfg_to_json(cfg: RTSConfig) -> str:
    return json.dumps(asdict(cfg), sort_keys=True)
