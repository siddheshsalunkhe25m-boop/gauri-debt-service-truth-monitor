"""AI layer tests: no network. A fake client and a local mock Messages API stand in for Anthropic."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from dstm_ai.check import check_output, check_text
from dstm_ai.facts import Pack, build_pack, tailored_levels
from dstm_ai.log import AILog
from dstm_ai.run import generate, to_markdown
from dstm_ai.template import template_output
from dstm_rts.config import RTSConfig

S = {"symbol": "TSTL", "company_name": "Test Steel 360 Ltd", "sector": "Metals & Mining", "latest_fy": "2026-03-31",
     "rts": 58.4, "rts_class": "Watch", "s_dscr": 40.0, "s_minsky": 37.5, "s_refi": 30.0, "s_breach": 80.0,
     "fa_dscr_3y": 1.12, "reported_dscr_3y": 1.47, "fa_dscr_maint_3y": 0.81, "fa_dscr_latest": 0.95,
     "minsky_state": "Speculative", "migration": "deteriorating", "minsky_path": "2024:H > 2025:S > 2026:S",
     "refi_dependence_3y": 0.70, "p_breach_base": 0.22, "p_breach_stress": 0.41, "median_q_base": None,
     "breach_icr_now": 3.2, "breach_debt_ebitda_now": 2.9, "breach_debt": 4200.0, "breach_status": "ok",
     "triggers": "[Watch] 22% probability of covenant breach within 4 quarters (baseline) | [Watch] Speculative and "
                 "deteriorating: covers interest but not principal, worse than its 3-yr history | [Watch] payables "
                 "stretched Rs 180 Cr beyond own norm = 14% of reported CFO"}
A = {"cfo": 1250.0, "payables_stretch": 180.0, "exceptional_gain_deducted": 40.0, "noncore_income_deducted": 25.0,
     "cfo_adj": 1005.0, "cfads": 1005.0, "interest_paid": 300.0, "principal_repaid": 700.0, "lease_payments": 60.0,
     "debt_service": 1060.0, "borrowings_raised": 650.0, "payable_days": 74.0, "payable_days_norm": 58.0,
     "stretch_note": "payable days 74 vs own 3-yr norm 58", "sloan_ratio": 0.06, "cash_conversion": 0.62,
     "interest_paid_flag": "", "interest_location": "interest paid in financing (cash-flow line)"}
CFG = RTSConfig()


def good_json():
    p, flags, rec = build_pack(S, A, CFG)
    return json.dumps(template_output(p, flags, rec))


def bad_json():
    out = json.loads(good_json())
    out["credit_note"]["repayment_capacity"] = out["credit_note"]["repayment_capacity"].replace("1.12x", "1.45x")
    out["credit_note"]["covenant_outlook"] += " Leverage should fall to 2.1x next year."
    return json.dumps(out)


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)], stop_reason="end_turn", model=kw["model"],
                               usage=SimpleNamespace(input_tokens=1500, output_tokens=900))


@pytest.fixture
def log(tmp_path):
    return AILog(tmp_path / "logs")


# ------------------------------------------------------------------ tailored levels (hand-worked)
def test_tailored_levels_hand_worked():
    """DSCR floor: 0.8 x 1.12 = 0.896 -> 0.85 -> min 1.00x. ICR floor: 0.7 x 3.2 = 2.24 -> 2.00 (policy).
    D/EBITDA cap: 1.3 x 2.9 = 3.77 -> up to 3.75? no: rounded UP to 0.25 -> 4.00, within policy 4.00.
    Amber ICR = 2.00 x 1.25 = 2.50; amber D/E = 4.00 x 0.85 = 3.40 -> 3.50 (nearest 0.25)."""
    t = tailored_levels(S, A, CFG)
    assert t["cov_dscr_floor"][0] == 1.00 and t["cov_icr_floor"][0] == 2.00 and t["cov_de_cap"][0] == 4.00
    assert t["trig_icr_amber"][0] == 2.50 and t["trig_de_amber"][0] == 3.50
    assert t["cov_creditor_days_cap"][0] == 73 and t["cov_refi_cap"][0] == 0.5
    assert "cov_dsra_quarters" not in t                          # floor 1.00x is below FA-DSCR 1.12x, class Watch
    assert tailored_levels({**S, "rts_class": "Escalate"}, A, CFG)["cov_dsra_quarters"][0] == 2
    """Strong borrower: FA-DSCR 2.0 -> 1.6 -> capped 1.30x; ICR 8 -> 5.6 -> 5.5 -> capped 2 x policy = 4.00x;
    D/E 1.0 -> 1.3 -> 1.50 -> floor 2.00x."""
    t = tailored_levels({**S, "fa_dscr_3y": 2.0, "breach_icr_now": 8.0, "breach_debt_ebitda_now": 1.0,
                         "refi_dependence_3y": 0.2, "rts_class": "Safe"}, {}, CFG)
    assert t["cov_dscr_floor"][0] == 1.30 and t["cov_icr_floor"][0] == 4.00 and t["cov_de_cap"][0] == 2.00
    assert "cov_refi_cap" not in t and "cov_dsra_quarters" not in t and "cov_creditor_days_cap" not in t
    assert tailored_levels({**S, "breach_debt_ebitda_now": 4.5}, {}, CFG)["cov_de_cap"][0] == 4.00


# ------------------------------------------------------------------ checker
def test_checker_rules():
    p = Pack()
    p.add("fa", "FA-DSCR 3-yr", 1.3116, "x")
    p.add("pb", "Probability of breach within 4 quarters", 0.42, "pct")
    p.add("company", "Company", "360 ONE Ltd", "text")
    st = lambda t: [c.status for c in check_text(t, "f", p)]
    assert st("DSCR 1.31x [F1], breach 42% [F2] within 4 quarters [F2].") == ["ok", "ok", "ok"]
    assert st("DSCR 1.3x [F1].") == ["ok"]                      # coarser rounding allowed
    assert st("DSCR 1.35x [F1].") == ["mismatch"]
    assert st("DSCR 42x [F2].") == ["mismatch"]                 # right number, wrong unit
    assert st("Leverage 3.5x.") == ["unmatched"]
    assert st("DSCR 1.31x.") == ["ok_uncited"]
    assert st("In FY2026 360 ONE Ltd paid.") == ["structural"]  # year allowed; digits in the name ignored


def test_template_passes_its_own_check_and_covers_flags():
    p, flags, rec = build_pack(S, A, CFG)
    out = template_output(p, flags, rec)
    chk = check_output(out, p)
    assert chk["passed"], chk["problems"]
    assert chk["n_numbers"] > 30 and chk["n_uncited"] == 0
    qs = " ".join(q["question"] for q in out["dd_questions"])
    assert "creditor ageing" in qs and "projections" in qs and "decline in operating cash flow" in qs
    assert any("DSCR" in c["covenant"] for c in out["covenants"])


def test_prompt_contains_only_fact_lines():
    p, _, _ = build_pack(S, A, CFG)
    for line in p.as_prompt().splitlines():
        assert re.match(r"^\[F\d+\] [^:]+: .+$", line), line


# ------------------------------------------------------------------ orchestration
def test_no_key_uses_template(log, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = generate(S, A, CFG, log=log)
    assert r["mode"] == "template" and r["check"]["passed"] and "no ANTHROPIC_API_KEY" in r["fallback_reason"]
    assert log.read()[0]["final_mode"] == "template"


def test_claude_accepted_first_time(log):
    c = FakeClient([good_json()])
    r = generate(S, A, CFG, client=c, log=log)
    assert r["mode"] == "claude" and len(r["attempts"]) == 1
    kw = c.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["model"] == "claude-opus-5-5"
    assert kw["messages"][0]["content"].startswith("FACT PACK") and "Hard rules" in kw["system"]


def test_correction_round_then_accept(log):
    c = FakeClient([bad_json(), good_json()])
    r = generate(S, A, CFG, client=c, log=log)
    assert r["mode"] == "claude" and len(r["attempts"]) == 2 and len(r["rejected"]) == 1
    fix = c.calls[1]["messages"][-1]["content"]
    assert "1.45x" in fix and "2.1x" in fix
    assert c.calls[1]["messages"][1]["role"] == "assistant"


def test_rejected_twice_falls_back_and_keeps_drafts(log):
    r = generate(S, A, CFG, client=FakeClient([bad_json(), bad_json()]), log=log)
    assert r["mode"] == "template" and len(r["rejected"]) == 2 and "failed the number check" in r["fallback_reason"]
    rec = log.read()[0]
    assert len(rec["rejected_drafts"]) == 2 and rec["final_check"]["passed"]


def test_api_error_and_bad_json(log):
    r = generate(S, A, CFG, client=FakeClient([RuntimeError("overloaded")]), log=log)
    assert r["mode"] == "template" and r["fallback_reason"] == "API error"
    r = generate(S, A, CFG, client=FakeClient(["not json"]), log=log)
    assert r["mode"] == "template" and r["fallback_reason"] == "invalid JSON"


def test_log_appendix_exports(log, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-be-logged")
    generate(S, A, CFG, client=FakeClient([bad_json(), good_json()]), log=log)
    generate(S, A, CFG, client=None, log=log)
    raw = log.path.read_text()
    assert "sk-ant-" not in raw
    s = log.summary()
    assert list(s.final_mode) == ["claude", "template"] and s.input_tokens.iloc[0] == 3000 and s.rejected_drafts.iloc[0] == 1
    md = log.appendix_markdown()
    assert "Appendix: use of generative AI" in md and "Correction request" in md and "rejected number" in md
    x = log.appendix_xlsx(tmp_path / "AI_Usage_Log.xlsx")
    import pandas as pd
    assert set(pd.read_excel(x, sheet_name=None)) == {"Runs", "Attempts", "Prompts"}
    r = generate(S, A, CFG, client=FakeClient([good_json()]), log=log)
    md = to_markdown(r, S)
    assert "Numbers verified" in md and "## Fact pack" in md and "Claude (claude-opus-5-5)" in md


# ------------------------------------------------------------------ the real SDK against a local mock API
def test_real_sdk_against_mock_messages_api(log):
    anthropic = pytest.importorskip("anthropic")
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["path"], seen["body"], seen["headers"] = self.path, body, dict(self.headers)
            resp = {"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
                    "content": [{"type": "text", "text": good_json()}], "stop_reason": "end_turn",
                    "stop_sequence": None, "usage": {"input_tokens": 1234, "output_tokens": 567}}
            data = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = anthropic.Anthropic(api_key="test-key", base_url=f"http://127.0.0.1:{srv.server_port}", max_retries=0)
        r = generate(S, A, CFG, client=client, log=log)
    finally:
        srv.shutdown()
    assert r["mode"] == "claude" and seen["path"] == "/v1/messages" and "test-key" in json.dumps(seen["headers"])
    assert seen["body"]["output_config"]["format"]["type"] == "json_schema"
    assert seen["body"]["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert r["attempts"][0]["input_tokens"] == 1234


def test_template_passes_check_for_every_demo_company(tmp_path):
    """Regression: the template must pass the number check for every company (a percentile once read as %)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_synthetic_history import synthetic_history
    from dstm_rts.engine import run_rts
    from dstm_rts.peers import benchmark
    cl, _ = synthetic_history(n=40, seed=5)
    res = run_rts(cl, RTSConfig(n_paths=500))
    sc = res.scores.assign(sector=["A", "B", "C", "D"] * 10, company_name=[f"Synthetic Co {i:03d}" for i in range(40)])
    for s in sc.to_dict("records"):
        a = res.annual[(res.annual.symbol == s["symbol"]) & res.annual.minsky_state.notna()]
        p, flags, rec = build_pack(s, a.iloc[-1].to_dict() if len(a) else {}, RTSConfig(), benchmark(sc, s["symbol"]))
        chk = check_output(template_output(p, flags, rec), p)
        assert chk["passed"], (s["symbol"], chk["problems"][:2])
        assert chk["n_uncited"] == 0, s["symbol"]


def test_percentile_is_not_percent():
    p = Pack()
    p.add("sector_pct_rts", "Sector percentile, RTS (100 = best)", 30.0, "score")
    assert [c.status for c in check_text("It ranks at the 30 [F1] percentile.", "f", p)] == ["ok"]


def test_covenant_rationale_reflects_breach():
    """FA-DSCR 0.07x below the 1.00x floor and ICR 0.99x below 2.00x: rationale must say 'already outside'."""
    s = {**S, "fa_dscr_3y": 0.07, "breach_icr_now": 0.99, "breach_debt_ebitda_now": 10.67, "rts_class": "Escalate"}
    p, flags, rec = build_pack(s, A, CFG)
    out = template_output(p, flags, rec)
    rat = {c["covenant"]: c["rationale"] for c in out["covenants"]}
    assert all("Already outside" in rat[k] for k in ("Minimum forensic-adjusted DSCR",
                                                     "Minimum interest cover (TTM EBITDA / interest)", "Maximum Debt / TTM EBITDA"))
    assert check_output(out, p)["passed"]
    ok = template_output(*build_pack(S, A, CFG))
    assert "Today: 1.12x" in {c["covenant"]: c["rationale"] for c in ok["covenants"]}["Minimum forensic-adjusted DSCR"]
