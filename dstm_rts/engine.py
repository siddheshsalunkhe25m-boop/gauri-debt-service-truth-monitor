"""Run the whole RTS engine from the data layer's credit_lines."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .breach import run_breach_clock
from .config import RTSConfig
from .inputs import annual_panel, latest_debt, quarter_panel
from .metrics import annual_metrics, migration_matrices
from .score import company_scores


@dataclass
class RTSResult:
    annual: pd.DataFrame
    quarters: pd.DataFrame
    debt: pd.DataFrame
    breach: pd.DataFrame
    scores: pd.DataFrame
    matrices: dict
    config: RTSConfig


def run_rts(credit_lines: pd.DataFrame, cfg: RTSConfig | None = None) -> RTSResult:
    cfg = cfg or RTSConfig()
    panel = annual_panel(credit_lines)
    annual = annual_metrics(panel, cfg)
    q = quarter_panel(credit_lines)
    debt = latest_debt(credit_lines)
    breach = run_breach_clock(q, debt, cfg)
    scores = company_scores(annual, breach, cfg) if len(annual) else pd.DataFrame()
    mats = migration_matrices(annual, cfg.migration_years) if len(annual) else {}
    return RTSResult(annual, q, debt, breach, scores, mats, cfg)
