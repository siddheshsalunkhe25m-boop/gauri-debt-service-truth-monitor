"""python -m dstm_rts run [--db data/dstm.db] [--out data/rts] [--config rts_config.json] [--demo]

Reads credit_lines from the data layer's SQLite cache, runs the RTS engine and writes:
  rts_scores.csv, rts_annual.csv, rts_breach.csv, rts_migration_*.csv, RTS_calculation.xlsx, rts_config.json
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from .config import RTSConfig
from .engine import run_rts
from .workbook import build_workbook


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dstm_rts")
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--db", default="data/dstm.db")
    ap.add_argument("--out", default="data/rts")
    ap.add_argument("--config", help="JSON file with RTSConfig overrides")
    ap.add_argument("--symbols", help="comma-separated subset")
    ap.add_argument("--demo", action="store_true", help="use the SYNTHETIC demo universe (tools/make_demo_credit_lines.py)")
    ap.add_argument("--no-workbook", action="store_true")
    a = ap.parse_args(argv)

    cfg = RTSConfig.from_json(a.config) if a.config else RTSConfig()
    if a.demo:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from make_demo_credit_lines import demo_credit_lines
        cl, note = demo_credit_lines(), "SYNTHETIC DEMO DATA - not real companies (symbols DEMO_*)"
    else:
        with sqlite3.connect(a.db) as con:
            cl = pd.read_sql_query("SELECT * FROM credit_lines", con)
        note = f"Source: Screener.in via dstm_data cache {a.db}"
    if a.symbols:
        cl = cl[cl.symbol.isin([s.strip() for s in a.symbols.split(",")])]
    res = run_rts(cl, cfg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res.scores.to_csv(out / "rts_scores.csv", index=False)
    res.annual.to_csv(out / "rts_annual.csv", index=False)
    res.breach.to_csv(out / "rts_breach.csv", index=False)
    for k, m in res.matrices.items():
        m.to_csv(out / f"rts_migration_{k}.csv")
    (out / "rts_config.json").write_text(cfg.to_json())
    if not a.no_workbook:
        build_workbook(res, cl, str(out / "RTS_calculation.xlsx"), note)
    cols = ["symbol", "rts", "rts_class", "fa_dscr_3y", "minsky_state", "migration", "refi_dependence_3y", "p_breach_base"]
    with pd.option_context("display.width", 200):
        print(res.scores[[c for c in cols if c in res.scores]].round(3).to_string(index=False))
    print("written to", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
