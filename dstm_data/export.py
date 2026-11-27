"""Write the tidy tables to parquet (if pyarrow is installed) and CSV, plus a data-quality report."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .cache import Cache
from .canonical import CFF_P, CFO_P, unmapped_cff_children


def _write(df: pd.DataFrame, path_stem: Path) -> list[str]:
    out = []
    df.to_csv(path_stem.with_suffix(".csv"), index=False)
    out.append(str(path_stem.with_suffix(".csv")))
    try:
        df.to_parquet(path_stem.with_suffix(".parquet"), index=False)
        out.append(str(path_stem.with_suffix(".parquet")))
    except (ImportError, ValueError):
        pass
    return out


def export_all(cache: Cache, export_dir: Path, symbols: Optional[list[str]] = None) -> list[str]:
    export_dir.mkdir(parents=True, exist_ok=True)
    files = []
    files += _write(cache.table("observations", symbols), export_dir / "observations")
    files += _write(cache.table("credit_lines", symbols), export_dir / "credit_lines")
    files += _write(cache.table("prices", symbols), export_dir / "prices")
    st = cache.all_status()
    if symbols:
        st = st[st.symbol.isin(symbols)]
    files += _write(st, export_dir / "company_status")
    audit = pd.read_sql_query("SELECT * FROM audit_log ORDER BY id", cache.con)
    if symbols:
        audit = audit[audit.symbol.isin(symbols)]
    files += _write(audit, export_dir / "audit_log")
    qa = quality_report(cache, symbols)
    files += _write(qa, export_dir / "data_quality")
    return files


def quality_report(cache: Cache, symbols: Optional[list[str]] = None) -> pd.DataFrame:
    """One row per company (primary basis): coverage and the flags a credit analyst must know about."""
    obs = cache.table("observations", symbols)
    cl = cache.table("credit_lines", symbols)
    st = cache.all_status()
    if symbols:
        st = st[st.symbol.isin(symbols)]
    out = []
    for s in st.itertuples(index=False):
        o = obs[(obs.symbol == s.symbol) & (obs.basis_role == "primary")]
        c = cl[(cl.symbol == s.symbol) & (cl.basis_role == "primary")]
        fy = c[c.frequency == "FY"]
        ip = fy[fy.field == "interest_paid"]
        cff_kids = set(o[(o.parent == CFF_P)].line_item)
        cfo_kids = set(o[(o.parent == CFO_P)].line_item)
        fy_pl = o[(o.statement == "profit-loss") & (o.period_type == "FY") & o.parent.isna()]
        partial = fy_pl[(fy_pl.period_months.notna()) & (fy_pl.period_months != 12)].period_label.unique()
        fills = o[o.is_standalone_fill == 1].period_label.unique()
        out.append({
            "symbol": s.symbol, "status": s.status, "primary_basis": s.primary_basis, "basis_note": s.basis_note,
            "layout": s.layout,
            "fy_first": fy_pl.period_end.min() if len(fy_pl) else None,
            "fy_last": fy_pl.period_end.max() if len(fy_pl) else None,
            "n_fy": fy_pl.period_end.nunique(),
            "n_quarters": o[(o.statement == "quarters") & o.parent.isna()].period_end.nunique(),
            "latest_interim_bs": o[(o.statement == "balance-sheet") & (o.period_type == "interim")].period_end.max(),
            "n_observations": len(o), "n_credit_lines": len(c),
            "interest_paid_sources": "; ".join(sorted(set(ip.flag.replace("", "cff")))),
            "fy_interest_from_pnl_fallback": int((ip.flag == "fallback_pnl_interest").sum()),
            "fy_interest_in_cfo": int((ip.flag == "interest_in_cfo").sum()),
            "cff_lines": "; ".join(sorted(cff_kids)),
            "cff_unmapped_lines": "; ".join(unmapped_cff_children(cff_kids)),
            "cfo_lines": "; ".join(sorted(cfo_kids)),
            "partial_year_columns": "; ".join(partial),
            "standalone_filled_columns": "; ".join(sorted(fills)),
            "n_requests_last_run": s.n_requests, "n_failed_last_run": s.n_failed, "message": s.message,
        })
    return pd.DataFrame(out)
