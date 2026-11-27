"""python -m dstm_ai note SYMBOL [--db data/dstm.db] [--out data/ai]   credit pack for one company (Markdown)
   python -m dstm_ai appendix [--out data/ai]                          AI_Usage_Appendix.md + AI_Usage_Log.xlsx
Uses ANTHROPIC_API_KEY / DSTM_AI_MODEL from the environment; without a key the template is used."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from dstm_rts.config import RTSConfig
from dstm_rts.engine import run_rts
from dstm_rts.peers import benchmark

from .log import AILog
from .run import generate, to_markdown


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dstm_ai")
    ap.add_argument("command", choices=["note", "appendix"])
    ap.add_argument("symbol", nargs="?")
    ap.add_argument("--db", default="data/dstm.db")
    ap.add_argument("--universe", default="ind_nifty200list.csv")
    ap.add_argument("--out", default="data/ai")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.command == "appendix":
        log = AILog()
        (out / "AI_Usage_Appendix.md").write_text(log.appendix_markdown(), encoding="utf-8")
        log.appendix_xlsx(out / "AI_Usage_Log.xlsx")
        print("written", out / "AI_Usage_Appendix.md", out / "AI_Usage_Log.xlsx")
        return 0
    with sqlite3.connect(a.db) as con:
        cl = pd.read_sql_query("SELECT * FROM credit_lines", con)
    cfg = RTSConfig()
    res = run_rts(cl, cfg)
    u = pd.read_csv(a.universe).rename(columns={"Symbol": "symbol", "Company Name": "company_name", "Industry": "sector"})
    sc = res.scores.merge(u[["symbol", "company_name", "sector"]], on="symbol", how="left")
    sc["sector"] = sc["sector"].fillna("Case study (outside Nifty 200)")
    sc["company_name"] = sc["company_name"].fillna(sc["symbol"])
    s = sc[sc.symbol == a.symbol].iloc[0].to_dict()
    ann = res.annual[(res.annual.symbol == a.symbol) & res.annual.minsky_state.notna()]
    r = generate(s, ann.iloc[-1].to_dict() if len(ann) else {}, cfg, benchmark(sc, a.symbol))
    p = out / f"credit_note_{a.symbol}.md"
    p.write_text(to_markdown(r, s), encoding="utf-8")
    print(f"{r['mode']}: numbers verified {r['check']['n_verified']} of {r['check']['n_numbers']} -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
