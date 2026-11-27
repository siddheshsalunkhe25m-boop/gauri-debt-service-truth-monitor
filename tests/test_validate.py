"""Validation-machinery tests. The synthetic history has a PLANTED pattern: these tests prove the code works
(point-in-time cut, outcomes, leakage, statistics), not that RTS works on real companies."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from dstm_rts.config import RTSConfig
from dstm_validate.backtest import auc, calibration, breach_clock_test, leakage_check, run_backtest
from dstm_validate.outcomes import max_drawdown, outcomes
from dstm_validate.pit import truncate


def cl_rows(rows):
    return pd.DataFrame([{"symbol": s, "basis": "consolidated", "basis_role": "primary", "frequency": f, "period_end": p,
                          "period_label": p, "period_months": 12, "field": fld, "value": v, "unit": "Rs Cr", "source": "t",
                          "flag": "", "source_url": "t", "fetched_at": "t"} for s, f, p, fld, v in rows])


def test_truncate_point_in_time_rules():
    """As of 30 Jun 2025: FY Mar-2025 in (results due within 60 days); quarter Mar-2025 in, Jun-2025 out;
    half-year Sep-2026 balance sheet out; TTM/snapshot rows always out."""
    cl = cl_rows([("A", "FY", "2025-03-31", "cfo", 1), ("A", "FY", "2026-03-31", "cfo", 2),
                  ("A", "Q", "2025-03-31", "ebitda", 1), ("A", "Q", "2025-06-30", "ebitda", 2),
                  ("A", "interim", "2026-09-30", "total_borrowings", 5), ("A", "TTM", "2026-09-30", "revenue", 9),
                  ("A", "snapshot", None, "market_cap", 9), ("A", "FY", "2024-12-31", "cfo", 3)])
    t = truncate(cl, "2025-06-30")
    assert set(zip(t.frequency, t.period_end)) == {("FY", "2025-03-31"), ("Q", "2025-03-31"), ("FY", "2024-12-31")}


def test_max_drawdown_hand_cases():
    """[100, 120, 60, 80]: peak 120, trough 60 -> 50% (not > 50%). [100, 40]: 60%. Coverage below 75% -> NaN."""
    weeks = pd.date_range("2020-07-03", periods=104, freq="7D").strftime("%Y-%m-%d")
    p = np.r_[[100, 120, 60, 80], np.full(100, 80)]
    mdd, n = max_drawdown(pd.DataFrame({"date": weeks, "close": p}), "2020-06-30")
    assert mdd == pytest.approx(0.5) and n == 104
    p2 = np.r_[[100], np.full(103, 40)]
    assert max_drawdown(pd.DataFrame({"date": weeks, "close": p2}), "2020-06-30")[0] == pytest.approx(0.6)
    assert np.isnan(max_drawdown(pd.DataFrame({"date": weeks[:50], "close": p2[:50]}), "2020-06-30")[0])


def test_outcome_definitions_hand_case():
    """FY2020 ICR = 100/20 = 5.0x, profit 30. FY2021 ICR 60/20 = 3.0x (60% of 5.0 = 3.0 -> NOT below), FY2022
    ICR 50/20 = 2.5x < 3.0 -> icr_fall = 1; ICR stays >= 2 -> icr_below_2 = 0. FY2022 loss -> loss = new_loss = 1."""
    rows = []
    for p, e, i, n in (("2020-03-31", 100, 20, 30), ("2021-03-31", 60, 20, 5), ("2022-03-31", 50, 20, -4)):
        rows += [("A", "FY", p, "ebitda", e), ("A", "FY", p, "interest_expense", i), ("A", "FY", p, "net_profit", n)]
    o = outcomes(cl_rows(rows), pd.DataFrame(columns=["symbol", "date", "close"]),
                 pd.DataFrame({"symbol": ["A"], "latest_fy": ["2020-03-31"]}), "2020-06-30").iloc[0]
    assert o.icr_asof == 5.0 and o.icr_fall == 1 and o.icr_below_2 == 0 and o.loss == 1 and o.new_loss == 1
    assert o.any_new_event == 1 and np.isnan(o.drawdown50)


def test_auc_hand_case():
    """Events scored 3 and 2, non-events 1 and 2 -> pairs (3>1, 3>2, 2>1, 2=2 half) = 3.5/4 = 0.875."""
    assert auc([1, 1, 0, 0], [3, 2, 1, 2]) == pytest.approx(0.875)


@pytest.fixture(scope="module")
def synth():
    from make_synthetic_history import synthetic_history
    return synthetic_history(n=40, seed=3)


def test_leakage_check_passes_and_detects(synth):
    """Scrambling every value after the cut-off must not change any cohort score."""
    cl, _ = synth
    for y in (2018, 2021, 2024):
        r = leakage_check(cl, y, RTSConfig(n_paths=100))
        assert r["passed"] and r["n_future_values_scrambled"] > 0


def test_backtest_recovers_planted_signal(synth):
    cl, px = synth
    panel = run_backtest(cl, px, range(2017, 2025), RTSConfig(n_paths=100))
    assert set(panel.cohort) == set(range(2017, 2025))
    assert (panel["asof"].str.endswith("-06-30")).all() and (panel["latest_fy"] < panel["asof"]).all()
    assert auc(panel.any_new_event, panel.risk_rts) > 0.7
    bt = breach_clock_test(cl, RTSConfig(n_paths=200))
    cal = calibration(bt)
    assert cal["n_simulated"] + cal["n_already_in_breach"] + cal["insufficient"] == len(bt)
