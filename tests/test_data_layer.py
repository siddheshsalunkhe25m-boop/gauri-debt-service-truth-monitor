import json
import time
from pathlib import Path

import pandas as pd
import pytest
import requests

from dstm_data.cache import Cache
from dstm_data.config import Settings
from dstm_data.http import LiveTransport, ReplayTransport, normalize_url, page_url, schedule_url
from dstm_data.parse import CompanyPage, parse_number, parse_period, parse_schedule
from dstm_data.pipeline import Pipeline
from tests.fixtures import FakeTransport, company_responses, make_page, schedules


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, min_interval_s=0.0, max_retries=2, backoff_base_s=0.0)


def run(settings, responses, symbols=("TSTL",), **kw):
    t = FakeTransport(responses, **kw)
    p = Pipeline(settings, transport=t)
    uni = pd.DataFrame({"symbol": list(symbols), "company_name": "x", "industry": "Metals & Mining"})
    res = p.refresh(uni, force=True, progress=lambda *_: None)
    return p, t, res


def cl(p, symbol="TSTL", role="primary"):
    df = p.cache.table("credit_lines", [symbol])
    return df[df.basis_role == role]


def val(df, field, period_end, freq="FY"):
    r = df[(df.field == field) & (df.period_end == period_end) & (df.frequency == freq)]
    assert len(r) == 1, (field, period_end, r)
    return r.iloc[0]


# ------------------------------------------------------------------ parsing
def test_parse_number_and_period():
    assert parse_number("2,01,921") == 201921
    assert parse_number("-6,568") == -6568
    assert parse_number("+9%") == 9
    assert parse_number("−5") == -5
    assert parse_number("") is None and parse_number(" - ") is None
    p = parse_period("Mar 2025 10m")
    assert (p["period_end"], p["months"], p["is_s"]) == ("2025-03-31", 10, False)
    p = parse_period("Mar 2015 (S)")
    assert p["is_s"] and p["base"] == "Mar 2015"
    assert parse_period("TTM")["is_ttm"]
    assert parse_period("Dec 2010", "2010-12-31")["period_end"] == "2010-12-31"


def test_page_labels_periods_and_units():
    page = CompanyPage(make_page(s_cols=1, partial_first=10))
    assert page.company_id == "3373" and page.layout == "industrial"
    rows = pd.DataFrame(page.rows())
    labels = set(rows.line_item)
    assert {"Sales", "Other Income", "CFO/EBITDA", "Free Cash Flow"} <= labels
    assert not any("+" in l or "Share of operating" in l for l in labels)
    assert "Raw PDF" not in labels
    bs = rows[rows.statement == "balance-sheet"]
    assert set(bs[bs.period_end == "2026-09-30"].period_type) == {"interim"}
    pl = rows[(rows.statement == "profit-loss") & (rows.line_item == "Sales")]
    assert set(pl.period_type) == {"FY", "TTM"}
    first = pl[pl.period_end == "2024-03-31"].iloc[0]
    assert first.period_months == 10 and first.is_standalone_fill == 1
    assert rows[(rows.line_item == "OPM %")].unit.iloc[0] == "%"
    assert rows[(rows.line_item == "Debtor Days")].unit.iloc[0] == "days"
    sh = rows[rows.statement == "shareholding"]
    assert set(sh.period_end) == {"2026-06-30", "2026-09-30"}          # quarterly table, not the yearly one
    assert page.latest_annual() == "2026-03-31"
    assert page.latest_annual(own_only=True) == "2026-03-31"
    tr = {r["line_item"]: r["value"] for r in page.top_ratios()}
    assert tr == {"Market Cap": 201921, "High": 224, "Low": 160, "ROCE": 12.5}


def test_schedule_parse_skips_meta_and_blanks():
    page = CompanyPage(make_page())
    sch = schedules()
    rows = parse_schedule(json.dumps(sch[("Other Assets", "balance-sheet")]), "balance-sheet", "Other Assets", page)
    df = pd.DataFrame(rows)
    assert set(df.line_item) == {"Inventories", "Trade receivables", "Cash Equivalents"}
    assert "2026-09-30" in set(df.period_end)
    rows = parse_schedule(json.dumps(sch[("Cash from Operating Activity", "cash-flow")]), "cash-flow",
                          "Cash from Operating Activity", page)
    assert all(r["period_type"] == "FY" for r in rows)
    rows = parse_schedule(json.dumps(sch[("Other Liabilities", "balance-sheet")]), "balance-sheet", "Other Liabilities", page)
    assert "Advance from Customers" not in {r["line_item"] for r in rows}      # all blank -> unknown, not zero


# ------------------------------------------------------------------ URLs
def test_urls_consolidated_flag_is_presence_based():
    assert schedule_url("3373", "Borrowings", "balance-sheet", True).endswith("&consolidated=")
    assert "consolidated" not in schedule_url("3373", "Borrowings", "balance-sheet", False)
    assert page_url("GVT&D", True) == "https://www.screener.in/company/GVT%26D/consolidated/"
    assert normalize_url("https://www.screener.in/api/company/1/schedules/?section=cash-flow&parent=Cash from Operating Activity&consolidated=") == \
        normalize_url("https://www.screener.in/api/company/1/schedules/?parent=Cash%20from%20Operating%20Activity&section=cash-flow&consolidated=")


# ------------------------------------------------------------------ pipeline
def test_both_bases_and_credit_lines(settings):
    sch = schedules(cff={"Proceeds from shares": [0, 0, 0], "Proceeds from borrowings": [200, 300, 100],
                         "Repayment of borrowings": [-150, -180, -120], "Redemption of debentures": [0, -50, -25],
                         "Interest paid fin": [-95, -105, -118], "Dividends paid": [-9, -9, -10],
                         "Financial liabilities": [-5, -6, -7], "Other financing items": [19, 20, 35]})
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), sch, schedules(scale=0.8))
    p, t, res = run(settings, resp)
    assert res.iloc[0].status == "ok" and res.iloc[0].basis == "consolidated"
    cons_sched = [u for u in t.requested if "/schedules/" in u and u.endswith("&consolidated=")]
    stand_sched = [u for u in t.requested if "/schedules/" in u and "consolidated" not in u]
    px = p.cache.table("prices", ["TSTL"])
    assert list(px.close) == [100.0, 60.5, 45.0] and px.source_url.str.contains("/chart/").all()
    assert len(cons_sched) == len(stand_sched) == len(settings.schedules)
    d = cl(p)
    assert val(d, "principal_repaid", "2025-03-31").value == 230                   # 180 + 50 debentures
    assert "Redemption of debentures" in val(d, "principal_repaid", "2025-03-31").source
    assert val(d, "interest_paid", "2026-03-31").value == 118 and val(d, "interest_paid", "2026-03-31").flag == ""
    assert val(d, "capex", "2026-03-31").value == 90
    assert val(d, "dividends_paid", "2026-03-31").value == 10
    assert val(d, "borrowings_ex_leases", "2026-03-31").value == 1040
    assert val(d, "net_worth", "2026-09-30", "interim").value == 590
    assert val(d, "receivables_over_6m", "2025-03-31").value == 40
    assert val(d, "exceptional_items", "2026-03-31", "Q").value == -5
    ttm = d[(d.field == "interest_expense") & (d.frequency == "TTM")]
    assert list(ttm.value) == [125] and list(ttm.period_end) == ["2026-09-30"]
    assert list(d[d.field == "market_cap"].value) == [201921]
    # missing child in a fetched schedule = real zero; blank child = unknown
    assert val(d, "acquisitions", "2026-03-31").flag == "absent_line_zero"
    assert d[(d.field == "customer_advances")].empty
    sec = cl(p, role="secondary")
    assert val(sec, "capex", "2026-03-31").value == 72                              # standalone kept separately
    obs = p.cache.table("observations", ["TSTL"])
    assert obs.source_url.notna().all() and obs.fetched_at.notna().all()


def test_interest_paid_fallbacks(settings):
    no_int = {"Proceeds from borrowings": [200, 300, 100], "Repayment of borrowings": [-150, -180, -120],
              "Dividends paid": [-9, -9, -10]}
    resp = company_responses("TSTL", "3373", make_page(), None, schedules(cff=no_int), None)
    p, _, _ = run(Settings(**{**settings.__dict__, "basis": "primary"}), resp)
    r = val(cl(p), "interest_paid", "2026-03-31")
    assert r.value == 120 and r.flag == "fallback_pnl_interest"
    resp = company_responses("TSTL", "3373", make_page(), None,
                             schedules(cff=no_int, cfo_extra={"Interest paid": [-90, -100, -115]}), None)
    p, _, _ = run(Settings(**{**settings.__dict__, "basis": "primary", "data_dir": settings.data_dir / "b"}), resp)
    r = val(cl(p), "interest_paid", "2026-03-31")
    assert r.value == 115 and r.flag == "interest_in_cfo"


def test_stale_consolidated_falls_back_to_standalone(settings):
    old = make_page(fy=("Mar 2008", "Mar 2009", "Mar 2010"))
    resp = company_responses("CPAL", "685", old, make_page(consolidated=False, cid="685"), None, schedules())
    p, t, res = run(settings, resp, symbols=("CPAL",))
    r = res.iloc[0]
    assert r.status == "ok" and r.basis == "standalone" and "stale" in r.note
    assert not any(u.endswith("&consolidated=") for u in t.requested if "/schedules/" in u)
    assert set(p.cache.table("credit_lines", ["CPAL"]).basis) == {"standalone"}


def test_primary_mode_skips_standalone_page_when_consolidated_current(settings):
    s = Settings(**{**settings.__dict__, "basis": "primary"})
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    p, t, res = run(s, resp)
    assert page_url("TSTL", False) not in t.requested
    assert res.iloc[0].requests == 1 + len(s.schedules) + 1          # page + schedules + price history


def test_failure_then_offline_fallback_keeps_cached_data(settings):
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    p, _, _ = run(settings, resp)
    n_before = len(p.cache.table("observations", ["TSTL"]))
    # second run: one schedule fails, then everything fails
    bad = schedule_url("3373", "Borrowings", "balance-sheet", True)
    p2 = Pipeline(settings, cache=p.cache, transport=FakeTransport(resp, fail={bad}))
    r2 = p2.refresh_company("TSTL")
    assert r2["status"] == "partial" and r2["failed"] == 1
    assert len(p.cache.table("observations", ["TSTL"])) == n_before                 # cached Borrowings body reused
    p3 = Pipeline(settings, cache=p.cache, transport=FakeTransport(resp, fail=set(resp)))
    r3 = p3.refresh_company("TSTL")
    assert r3["status"] == "failed_served_cache"
    assert len(p.cache.table("observations", ["TSTL"])) == n_before
    st = p.cache.get_status("TSTL")
    assert st["last_success"] is not None                                              # from the first run
    audit = pd.read_sql_query("SELECT * FROM audit_log", p.cache.con)
    assert (audit.status == 0).sum() >= 1 and audit.url.notna().all() and audit.ts_utc.notna().all()


def test_only_stale_companies_refreshed(settings):
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    p, _, _ = run(settings, resp)
    t2 = FakeTransport(resp)
    p2 = Pipeline(settings, cache=p.cache, transport=t2)
    uni = pd.DataFrame({"symbol": ["TSTL"], "company_name": "x", "industry": "y"})
    res = p2.refresh(uni, progress=lambda *_: None)
    assert res.iloc[0].status == "fresh_skipped" and t2.requested == []
    p.cache.con.execute("UPDATE company_status SET last_success='2020-01-01T00:00:00+00:00'")
    res = p2.refresh(uni, progress=lambda *_: None)
    assert res.iloc[0].status == "ok" and t2.requested


def test_offline_mode_makes_no_requests(settings):
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    p, _, _ = run(settings, resp)
    t2 = FakeTransport({})
    p2 = Pipeline(settings, cache=p.cache, transport=t2, offline=True)
    r = p2.refresh_company("TSTL")
    assert t2.requested == [] and r["observations"] > 0


def test_lender_layout_excluded_and_unknown_symbol(settings):
    resp = company_responses("BANKX", "9", make_page(lender=True), make_page(lender=True, consolidated=False))
    p, t, res = run(settings, resp, symbols=("BANKX", "NOSUCH"))
    st = res.set_index("symbol").status
    assert st["BANKX"] == "excluded_lender" and st["NOSUCH"] == "not_found"
    assert not any("/api/company/9/" in u for u in t.requested)


def test_schedule_403_is_not_available_not_failure(settings):
    resp = company_responses("TSTL", "3373", make_page(), make_page(consolidated=False), schedules(), schedules())
    tr = schedule_url("3373", "Trade receivables", "balance-sheet", True)
    resp.pop(normalize_url(tr), None)
    p, _, res = run(settings, resp, status_override={tr: 403})
    assert res.iloc[0].status == "ok" and res.iloc[0].not_available == 1


# ------------------------------------------------------------------ live transport (mocked HTTP)
class _Resp:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers, self.content = status, text, headers or {}, text.encode()


class _Session:
    def __init__(self, seq):
        self.seq, self.headers, self.calls = list(seq), {}, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((time.monotonic(), headers))
        x = self.seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


def test_live_transport_retries_backoff_and_audit():
    log, sleeps = [], []
    s = Settings(min_interval_s=0.0, max_retries=3, backoff_base_s=2.0)
    sess = _Session([_Resp(503), requests.ConnectionError("reset"), _Resp(429, headers={"Retry-After": "5"}), _Resp(200, "ok")])
    t = LiveTransport(s, on_attempt=log.append, session=sess, sleep=sleeps.append)
    r = t.get("https://www.screener.in/company/TCS/")
    assert r.ok and r.attempts == 4 and len(log) == 4
    assert sleeps == [2.0, 4.0, 8.0]                                               # Retry-After 5 < backoff 8
    assert [x["status"] for x in log] == [503, 0, 429, 200]
    assert "Mozilla/5.0" in sess.headers["User-Agent"] and "text/html" in sess.calls[0][1]["Accept"]


def test_live_transport_no_retry_on_404_and_rate_limit():
    s = Settings(min_interval_s=0.2, max_retries=3)
    sess = _Session([_Resp(404), _Resp(200, "{}"), _Resp(200, "{}")])
    t = LiveTransport(s, session=sess, sleep=lambda x: None)
    assert t.get("https://www.screener.in/company/NOPE/").status == 404 and len(sess.calls) == 1
    t.get("https://www.screener.in/api/company/1/schedules/?parent=Borrowings&section=balance-sheet")
    t.get("https://www.screener.in/api/company/1/schedules/?parent=Borrowings&section=balance-sheet")
    gaps = [b[0] - a[0] for a, b in zip(sess.calls, sess.calls[1:])]
    assert min(gaps) >= 0.19
    assert "application/json" in sess.calls[1][1]["Accept"]


def test_replay_transport_reads_browser_capture(tmp_path):
    cap = {"items": {"https://www.screener.in/company/GVT%26D/consolidated/": {"status": 200, "body": "x", "fetched_at": "2026-11-23T07:20:00Z"},
                     "https://www.screener.in/api/company/1/schedules/?parent=Cash%20from%20Investing%20Activity&section=cash-flow": {"status": 0, "body": ""}}}
    f = tmp_path / "cap.json"
    f.write_text(json.dumps(cap))
    t = ReplayTransport([f])
    r = t.get(page_url("GVT&D", True))
    assert r.ok and r.fetched_at == "2026-11-23T07:20:00Z"
    assert not t.get(schedule_url("1", "Cash from Investing Activity", "cash-flow", False)).ok
    assert "not in capture" in t.get(page_url("TCS", True)).error
