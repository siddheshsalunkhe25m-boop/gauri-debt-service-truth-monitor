"""Copy the latest good data into dashboard/snapshot/ so the hosted app (Streamlit Community Cloud) opens on
real data. Run by the GitHub Action after a refresh; safe to run locally too.

  python tools/write_snapshot.py [--db data/dstm.db] [--validation data/validation]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "dstm.db"))
    ap.add_argument("--validation", default=str(ROOT / "data" / "validation"))
    ap.add_argument("--out", default=str(ROOT / "dashboard" / "snapshot"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(a.db) as con:
        cl = pd.read_sql_query("SELECT * FROM credit_lines", con)
        st = pd.read_sql_query("SELECT * FROM company_status ORDER BY symbol", con)
    if cl.empty:
        print("credit_lines is empty: snapshot NOT written (previous snapshot kept)")
        return 1
    ok = st.status.isin(["ok", "partial", "excluded_lender", "failed_served_cache"]).sum()
    if ok < 0.8 * len(st):
        print(f"only {ok} of {len(st)} companies usable: snapshot NOT written (previous snapshot kept)")
        return 1
    cl.to_parquet(out / "credit_lines.parquet", index=False)
    st.to_parquet(out / "company_status.parquet", index=False)
    as_of = str(cl["fetched_at"].dropna().max())
    (out / "meta.json").write_text(json.dumps({"as_of": as_of, "rows": len(cl), "symbols": int(cl.symbol.nunique()),
                                               "written": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                                               "status_counts": st.status.value_counts().to_dict()}, indent=1))
    v = Path(a.validation)
    if (v / "auc_table.csv").exists():
        dst = out / "validation"
        dst.mkdir(exist_ok=True)
        for f in list(v.glob("*.csv")) + list(v.glob("*.png")) + list(v.glob("*.md")) + list(v.glob("*.json")):
            shutil.copy2(f, dst / f.name)
    print(f"snapshot written: {cl.symbol.nunique()} companies, {len(cl):,} rows, data as of {as_of}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
