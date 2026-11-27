"""Universe: Nifty 200 constituents from the NSE list, non-financial companies only."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import FINANCIAL_INDUSTRY


def load_universe(csv_path: Path, non_financial_only: bool = True) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"Company Name": "company_name", "Industry": "industry", "Symbol": "symbol",
                            "Series": "series", "ISIN Code": "isin"})
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["is_financial"] = df["industry"].str.strip().eq(FINANCIAL_INDUSTRY)
    if non_financial_only:
        df = df[~df["is_financial"]]
    return df.reset_index(drop=True)
