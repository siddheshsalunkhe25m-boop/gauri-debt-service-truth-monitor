"""Fan chart, reported DSCR, decision rules and peer percentiles (hand-worked)."""
import numpy as np
import pandas as pd
import pytest

from dstm_rts.breach import breach_clock, fan
from dstm_rts.config import RTSConfig
from dstm_rts.decision import headroom, recommend, red_flags
from dstm_rts.metrics import annual_metrics
from dstm_rts.peers import benchmark, better_pct
from tests.test_rts import declining, panel, q


def test_fan_matches_breach_clock_and_deterministic_path():
    """Deterministic decline (see test_rts): TTM EBITDA 740 - 20h, debt 2,800 -> Debt/EBITDA h1 3.89, h3 4.12.
    All quantiles equal; P(breach by q) from the fan equals breach_clock's probability."""
    cfg = RTSConfig(n_paths=300)
    f = fan("DEC", q(declining(), [50] * 13), 2800, cfg)
    assert f["base_de_q"][2][0] == pytest.approx(2800 / 720) and f["base_de_q"][2][2] == pytest.approx(2800 / 680)
    assert np.allclose(f["base_de_q"][0], f["base_de_q"][4])
    assert f["hist_de"][-1] == pytest.approx(2800 / 740) and len(f["hist_end"]) == 10
    r = breach_clock("DEC", q(declining(), [50] * 13), 2800, None, cfg)
    assert f["base_p_breach_by_q"][3] == r.p_breach_base and f["stress_p_breach_by_q"][3] == r.p_breach_stress
    assert f["fut_end"][0] == "2026-12-31"
    assert fan("NEW", q([100] * 6, [5] * 6), 100, cfg) is None


def test_reported_dscr_excludes_forensic_adjustments():
    """CFO 300, payables stretch 100 (see test_payables_stretch), interest 50, repayment 100, lease 30.
    Reported DSCR = 300 / (50+100) = 2.0 (no stretch, no lease). FA-DSCR = 200 / 180 = 1.11."""
    rows = [{"symbol": "P", "period_end": f"{y}-03-31", "cfo": 300, "operating_expenses": 1000, "trade_payables": 100,
             "interest_paid": 50, "principal_repaid": 100, "financial_liabilities_paid": 30} for y in (2023, 2024, 2025)]
    rows.append({**rows[-1], "period_end": "2026-03-31", "trade_payables": 200})
    a = annual_metrics(panel(rows), RTSConfig()).iloc[-1]
    assert a.reported_dscr == pytest.approx(2.0) and a.fa_dscr == pytest.approx(200 / 180)


def base_row(**kw):
    r = {"rts_class": "Safe", "rts": 85, "fa_dscr_3y": 2.0, "reported_dscr_3y": 2.2, "fa_dscr_maint_3y": 1.4,
         "refi_dependence_3y": 0.2, "p_breach_base": 0.0, "p_breach_stress": 0.01, "minsky_state": "Hedge",
         "migration": "stable", "triggers": "", "breach_icr_now": 8.0, "breach_debt_ebitda_now": 1.5, "breach_status": "ok"}
    r.update(kw)
    return r


def test_decision_ladder():
    cfg = RTSConfig()
    assert recommend(base_row(), cfg).decision == "Enhance"
    assert recommend(base_row(rts=75), cfg).decision == "Renew"
    assert recommend(base_row(refi_dependence_3y=0.6), cfg).decision == "Renew"
    w = recommend(base_row(rts_class="Watch", triggers="[Watch] x"), cfg)
    assert w.decision == "Reprice" and any("DSCR" in c[0] for c in w.covenants)
    e = recommend(base_row(rts_class="Escalate", minsky_state="Ponzi", p_breach_base=0.6), cfg)
    assert e.decision == "Watch" and any("Security" in c[0] for c in e.covenants) and any("Equity-cure" in c[0] for c in e.covenants)
    assert recommend({"rts_class": "Insufficient data"}, cfg).decision == "Hold"


def test_covenant_headroom():
    """ICR 8x vs 2x covenant: can fall 75% -> headroom 75%. Debt/EBITDA 1.5x vs 4x: can rise 167%.
    ICR 2.4x: headroom 1 - 2/2.4 = 16.7% -> tight. Debt/EBITDA 4.5x > 4x -> already breached."""
    assert headroom(8, 2, True) == pytest.approx(0.75) and headroom(1.5, 4, False) == pytest.approx(4 / 1.5 - 1)
    cov = recommend(base_row(breach_icr_now=2.4, breach_debt_ebitda_now=4.5), RTSConfig()).covenants
    assert "(tight)" in cov[0][2] and "ALREADY BREACHED" in cov[1][2]


def test_red_flags_and_covenant_addons():
    s = base_row(rts_class="Watch", triggers="[Watch] payables stretched Rs 100 Cr")
    a = {"payables_stretch": 100.0, "cfo": 300.0, "stretch_note": "payable days 73 vs own 3-yr norm 37",
         "interest_paid_flag": "fallback_pnl_interest", "interest_location": "inferred", "lease_payments": 50.0,
         "debt_service": 150.0, "sloan_ratio": 0.12, "cash_conversion": 0.4}
    fl = red_flags(s, a, RTSConfig())
    codes = [f["code"] for f in fl]
    assert {"trigger", "payables_stretch", "interest_location_inferred", "lease_heavy", "accruals", "cash_conversion"} <= set(codes)
    assert fl[0]["severity"] in ("high", "medium")
    cov = [c[0] for c in recommend(s, RTSConfig(), fl).covenants]
    assert any("creditor ageing" in c for c in cov) and any("lease" in c for c in cov)


def test_peer_percentiles():
    """Values 1,2,3,4: x=3 higher-better -> (2 below + 0.5)/4 = 62.5; lower-better -> (1 below + 0.5)/4 = 37.5."""
    v = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert better_pct(v, 3.0, True) == 62.5 and better_pct(v, 3.0, False) == 37.5
    sc = pd.DataFrame({"symbol": list("ABCDE"), "sector": ["X", "X", "X", "Y", "Y"], "rts": [90, 50, 70, 10, 30],
                       "p_breach_base": [0.0, 0.5, 0.1, 0.9, 0.2]})
    b = benchmark(sc, "C").set_index("metric")
    assert b.loc["rts", "sector_pct"] == pytest.approx(50.0) and b.loc["rts", "universe_pct"] == pytest.approx(70.0)
    assert b.loc["p_breach_base", "sector_pct"] == pytest.approx(50.0) and b.loc["rts", "n_sector"] == 3
