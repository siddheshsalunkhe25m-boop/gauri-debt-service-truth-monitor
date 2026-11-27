"""Settings for the Debt-Service Truth Monitor data layer.

Everything a user may want to change lives here or can be overridden from the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

BASE_URL = "https://www.screener.in"

# A normal desktop-browser User-Agent. Screener's public pages need no login.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Schedules (the "+" breakdowns on Screener) fetched for every company and basis.
# (parent row, section). Each is one request.
SCHEDULES: list[tuple[str, str]] = [
    ("Cash from Operating Activity", "cash-flow"),   # Receivables, Inventory, Payables, Direct taxes (+ interest paid for some firms)
    ("Cash from Investing Activity", "cash-flow"),   # Fixed assets purchased (capex), asset sales, interest/dividends received
    ("Cash from Financing Activity", "cash-flow"),   # Proceeds/repayment of borrowings, Interest paid fin, Dividends paid, ...
    ("Borrowings", "balance-sheet"),                  # Long/short term, lease liabilities, preference capital
    ("Other Liabilities", "balance-sheet"),           # Trade payables, advance from customers, minority interest
    ("Other Assets", "balance-sheet"),                # Inventories, trade receivables, cash equivalents
    ("Trade receivables", "balance-sheet"),           # Receivables over/under 6 months, provision for doubtful
    ("Other Income", "profit-loss"),                  # Exceptional items vs normal other income
    ("Net Profit", "profit-loss"),                    # Minority share, exceptional items after tax
    ("Other Income", "quarters"),                     # Quarterly exceptional items
]

# Sections parsed from the company page.
PAGE_SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"]

# NSE industry label treated as financial (banks, NBFCs, insurers, AMCs, exchanges, fintech).
FINANCIAL_INDUSTRY = "Financial Services"


@dataclass
class Settings:
    data_dir: Path = Path("data")
    db_name: str = "dstm.db"
    universe_csv: Path = Path("ind_nifty200list.csv")
    min_interval_s: float = 1.0          # at most one request per second
    timeout_s: float = 30.0
    max_retries: int = 3                 # retries after the first attempt (429 / 5xx / network errors)
    backoff_base_s: float = 2.0          # 2, 4, 8 seconds ...
    max_age_days: float = 7.0            # a company older than this is "stale" and refreshed
    basis: str = "both"                  # "both" = consolidated + standalone; "primary" = consolidated, standalone only as fallback
    stale_consolidated_months: int = 24  # in primary-only mode: consolidated older than this vs today is treated as stale
    schedules: list = field(default_factory=lambda: list(SCHEDULES))
    fetch_prices: bool = True            # weekly price history (Screener chart API), one request per company

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"
