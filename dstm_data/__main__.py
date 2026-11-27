"""Command line.

  python -m dstm_data refresh                      # all stale non-financial Nifty 200 companies, live
  python -m dstm_data refresh --symbols TCS,LT     # just these
  python -m dstm_data refresh --force              # ignore freshness
  python -m dstm_data refresh --offline            # no network: rebuild tidy tables from the cache
  python -m dstm_data refresh --replay cap.json    # replay responses captured in a browser
  python -m dstm_data export                       # parquet/CSV into data/exports/
  python -m dstm_data status                       # what is cached and how fresh
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .cache import Cache
from .config import Settings
from .export import export_all
from .pipeline import Pipeline
from .universe import load_universe


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dstm_data", description="Debt-Service Truth Monitor - data layer")
    ap.add_argument("command", choices=["refresh", "export", "status"])
    ap.add_argument("--universe", default="ind_nifty200list.csv", help="NSE Nifty 200 CSV")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--symbols", help="comma-separated symbols (default: whole non-financial universe)")
    ap.add_argument("--extra", help="comma-separated symbols ADDED to the universe (e.g. case studies outside the Nifty 200)")
    ap.add_argument("--limit", type=int, help="only the first N companies")
    ap.add_argument("--force", action="store_true", help="refresh even if fresh")
    ap.add_argument("--offline", action="store_true", help="no network; rebuild from cache")
    ap.add_argument("--replay", nargs="+", help="capture JSON file(s) to replay instead of live HTTP")
    ap.add_argument("--basis", choices=["both", "primary"], default="both")
    ap.add_argument("--max-age-days", type=float, default=7.0)
    ap.add_argument("--min-interval", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--include-financials", action="store_true", help="do not drop NSE 'Financial Services'")
    a = ap.parse_args(argv)

    s = Settings(data_dir=Path(a.data_dir), universe_csv=Path(a.universe), basis=a.basis,
                 max_age_days=a.max_age_days, min_interval_s=a.min_interval)
    cache = Cache(s.db_path)

    if a.command == "status":
        st = cache.all_status()
        with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 60):
            print(st[["symbol", "status", "primary_basis", "last_success", "n_requests", "n_failed"]].to_string(index=False)
                  if len(st) else "cache is empty")
        return 0

    uni = load_universe(s.universe_csv, non_financial_only=not a.include_financials)
    if a.symbols:
        want = [x.strip() for x in a.symbols.split(",") if x.strip()]
        missing = [w for w in want if w not in set(uni.symbol)]
        extra = pd.DataFrame({"symbol": missing, "company_name": None, "industry": None})
        uni = pd.concat([uni[uni.symbol.isin(want)], extra], ignore_index=True)
        if missing:
            print(f"note: not in the non-financial universe, fetched anyway: {', '.join(missing)}")
    if a.extra:
        add = [x.strip() for x in a.extra.split(",") if x.strip() and x.strip() not in set(uni.symbol)]
        uni = pd.concat([uni, pd.DataFrame({"symbol": add, "company_name": None, "industry": "case study (outside universe)"})],
                        ignore_index=True)
    if a.limit:
        uni = uni.head(a.limit)

    if a.command == "refresh":
        p = Pipeline(s, cache=cache, replay_files=a.replay, offline=a.offline)
        res = p.refresh(uni, force=a.force)
        print("\nrun", p.run_id, "->", res["status"].value_counts().to_dict())
        bad = res[~res["status"].isin(["ok", "fresh_skipped"])]
        for r in bad.itertuples(index=False):
            print(f"  {r.symbol}: {r.status}")
    files = export_all(cache, s.export_dir, list(uni.symbol))
    print("exported:", *files, sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
