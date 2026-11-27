"""Repayment Truth Score (RTS) - every setting in one place.

All weights, thresholds and switches can be changed here or overridden from the CLI / a JSON file.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RTSConfig:
    # ---------------------------------------------------------------- RTS weights (re-normalised to sum to 1)
    w_dscr: float = 0.35
    w_minsky: float = 0.25
    w_refi: float = 0.20
    w_breach: float = 0.20

    # ---------------------------------------------------------------- forensic-adjusted CFO
    payables_norm_years: int = 3            # own norm = mean payable days of the previous N fiscal years
    payables_min_history: int = 2           # fewer prior years than this -> no stretch adjustment (flagged)
    deduct_exceptional_gains: bool = True   # deduct positive exceptional items (Screener "Exceptional items")
    noncore_mode: str = "ex_investing_receipts"
    #   "ex_investing_receipts": other income (normal) minus interest & dividends received (those are already
    #                            in investing cash flow under Ind AS 7, so only the remainder can sit inside CFO)
    #   "all_other_income":      all recurring other income (most conservative)
    #   "none":                  no non-core deduction

    # ---------------------------------------------------------------- debt service
    interest_addback: str = "auto"
    #   "auto":   add interest back to CFO only when it was paid INSIDE operating cash flow (avoids double count;
    #             most Indian companies report interest paid under financing, so CFO is already pre-interest)
    #   "always": add interest paid back every time (the textbook formula, CFO assumed after interest)
    #   "never":  never add back
    fallback_other_financing_share: float = 0.8  # P&L-interest fallback: if "Other financing items" outflow >= this
    #                                              share of P&L interest, interest is assumed paid in financing
    include_lease_payments: bool = True     # treat Screener "Financial liabilities" outflow (mostly lease principal,
    #                                         Ind AS 116) as repayment: EBITDA/CFO already exclude lease rent
    min_debt_service: float = 1.0           # Rs Cr; below this the company is treated as having no debt service

    # ---------------------------------------------------------------- Minsky / migration
    migration_years: int = 3                # compare current state with the mean state of the previous N years
    migration_threshold: float = 0.5        # ordinal change (Ponzi=0, Speculative=1, Hedge=2) needed to call a move

    # ---------------------------------------------------------------- refinancing dependence
    refi_years: int = 3                     # pooled over the last N fiscal years

    # ---------------------------------------------------------------- Breach Clock
    icr_min: float = 2.0                    # covenant: TTM EBITDA / TTM interest >= 2.0x
    debt_ebitda_max: float = 4.0            # covenant: Debt / TTM EBITDA <= 4.0x
    debt_measure: str = "gross"             # "gross" = total borrowings (incl. leases); "net" = minus cash & equivalents
    n_paths: int = 10000
    horizon_q: int = 12                     # simulate 12 quarters; P(breach) reported within `breach_window_q`
    breach_window_q: int = 4
    min_yoy_pairs: int = 4                  # need >= 4 year-on-year quarter pairs (i.e. >= 8 quarters) to simulate
    stress_ebitda_haircut: float = 0.25     # stress: simulated EBITDA cut by 25%
    stress_interest_uplift: float = 0.20    # stress: simulated interest up 20% (rate shock / refinancing at higher cost)
    stress_remove_drift: bool = True        # stress: de-mean the bootstrapped YoY changes (no growth tailwind)
    seed: int = 20261123

    # ---------------------------------------------------------------- sub-score mappings (piecewise linear)
    dscr_points: list = field(default_factory=lambda: [[0.8, 0], [1.0, 30], [1.25, 55], [1.5, 70], [2.0, 85], [3.0, 100]])
    minsky_state_score: dict = field(default_factory=lambda: {"Hedge": 100, "Speculative": 50, "Ponzi": 0})
    migration_score: dict = field(default_factory=lambda: {"improving": 100, "stable": 50, "deteriorating": 0})
    minsky_state_weight: float = 0.75       # Minsky component = 0.75 state + 0.25 migration
    breach_base_weight: float = 0.6         # Breach component = 100 x (1 - (0.6 P_base + 0.4 P_stress))

    # ---------------------------------------------------------------- classes
    safe_min: float = 70.0                  # RTS >= 70 Safe
    watch_min: float = 45.0                 # 45 <= RTS < 70 Watch; < 45 Escalate
    escalate_p_breach: float = 0.50         # override to Escalate if baseline P(breach in 4q) >= 50%
    watch_p_breach: float = 0.20            # override to at least Watch if baseline P(breach in 4q) >= 20%
    watch_stretch_share: float = 0.10       # payables stretch > 10% of reported CFO -> at least Watch
    watch_refi_dependence: float = 0.75     # > 75% of debt service funded by new borrowing (3-yr) -> at least Watch

    @property
    def weights(self) -> dict:
        w = {"dscr": self.w_dscr, "minsky": self.w_minsky, "refi": self.w_refi, "breach": self.w_breach}
        tot = sum(w.values())
        return {k: v / tot for k, v in w.items()}

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, path: Path) -> "RTSConfig":
        return cls(**json.loads(Path(path).read_text()))
