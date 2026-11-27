"""Headless dashboard tests (Streamlit AppTest) on the synthetic demo data and on a real-format cache."""
import shutil
from pathlib import Path

import pytest

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Never read or write the real data/ or snapshot folders from tests."""
    monkeypatch.setenv("DSTM_DATA_DIR", str(tmp_path / "iso_data"))
    monkeypatch.setenv("DSTM_SNAPSHOT_DIR", str(tmp_path / "iso_snap"))
    monkeypatch.setenv("DSTM_AI_LOG_DIR", str(tmp_path / "iso_ai"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def fresh():
    at = AppTest.from_file(APP, default_timeout=240)
    at.run()
    return at


def no_exc(at):
    assert not at.exception, [e.value for e in at.exception][:2]


def test_portfolio_page_demo():
    at = fresh()
    no_exc(at)
    assert at.title[0].value == "Portfolio"
    assert "SYNTHETIC" in at.error[0].value                         # demo banner always shown
    assert len([b for b in at.button if (b.key or "").startswith("open_")]) == 10
    assert any("Breach Clock" in s.value for s in at.subheader)


def test_open_company_from_top10_and_all_tabs():
    at = fresh()
    btn = [b for b in at.button if (b.key or "").startswith("open_")][0]
    sym = btn.key[5:]
    btn.click().run()
    no_exc(at)
    assert at.session_state["symbol"] == sym
    assert any("Recommended decision" in m.value for m in at.markdown)
    assert len(at.tabs) == 7
    at.radio[0].set_value("stress").run()                            # Breach Clock scenario switch
    no_exc(at)


def test_every_company_renders():
    at = fresh()
    at.switch_page("views/company.py").run()
    no_exc(at)
    syms = at.selectbox[0].options
    for s in syms[:40]:
        at.selectbox[0].set_value(s.split("(")[-1].rstrip(")") if "(" in s else s).run()
        no_exc(at)


def test_settings_change_rescored_and_method_page():
    at = fresh()
    at.number_input(key="icr").set_value(3.0).run()
    no_exc(at)
    assert "ICR ≥ 3.00x" in at.caption[0].value
    at.slider(key="w4").set_value(0).run()
    no_exc(at)
    at.switch_page("views/method.py").run()
    no_exc(at)
    assert at.title[0].value == "Method & data"


def test_refresh_unreachable_keeps_cache(monkeypatch):
    """In a sandbox without access to screener.in the refresh must fail gracefully and change nothing."""
    import sys
    sys.path.insert(0, str(Path(APP).parent))
    import data
    monkeypatch.setattr(data, "reachable", lambda timeout=8: (False, "ConnectionError"))
    out = data.refresh_live("stale", None, False)
    assert not out["ok"] and "cached data kept" in out["message"]


def test_live_cache_then_corrupt_db_falls_back_to_snapshot(tmp_path, monkeypatch):
    """Real-format cache built by the actual pipeline (fixture pages) -> 'live cache' and a snapshot is written;
    then the DB is corrupted -> the dashboard opens from the snapshot with a warning."""
    import pandas as pd
    from dstm_data.config import Settings
    from dstm_data.pipeline import Pipeline
    from tests.fixtures import FakeTransport, company_responses, make_page, schedules
    data_dir, snap = tmp_path / "data", tmp_path / "snap"
    resp = {}
    for sym, cid in (("TATASTEEL", "3373"), ("JSWSTEEL", "3374"), ("TCS", "3375")):
        resp.update(company_responses(sym, cid, make_page(cid=cid), make_page(cid=cid, consolidated=False),
                                      schedules(), schedules()))
    p = Pipeline(Settings(data_dir=data_dir, min_interval_s=0), transport=FakeTransport(resp))
    p.refresh(pd.DataFrame({"symbol": ["TATASTEEL", "JSWSTEEL", "TCS"], "company_name": "x", "industry": "y"}),
              force=True, progress=lambda *_: None)
    p.cache.close()
    monkeypatch.setenv("DSTM_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DSTM_SNAPSHOT_DIR", str(snap))
    at = fresh()
    no_exc(at)
    assert not any("SYNTHETIC" in e.value for e in at.error)
    assert any("Live from Screener" in m.value for m in at.sidebar.markdown)
    assert (snap / "credit_lines.parquet").exists()
    (data_dir / "dstm.db").write_bytes(b"this is not a sqlite file" * 100)
    at = fresh()
    no_exc(at)
    assert any("Offline snapshot" in m.value for m in at.sidebar.markdown)
    assert any("could not be read" in w.value for w in at.sidebar.warning)


def test_import_browser_capture(tmp_path, monkeypatch):
    """A capture file in the browser script's format (gzipped, meta.mode=primary) is replayed into a new cache."""
    import gzip
    import importlib
    import json
    import sys
    from tests.fixtures import company_responses, make_page, schedules
    resp = company_responses("TATASTEEL", "3373", make_page(), None, schedules(), None)
    cap = {"meta": {"mode": "primary"}, "items": {u: {"status": 200, "body": b, "fetched_at": "2026-11-23T08:00:00Z"}
                                                  for u, b in resp.items()}}
    f = tmp_path / "dstm_capture_full.json.gz"
    with gzip.open(f, "wt", encoding="utf-8") as fh:
        json.dump(cap, fh)
    monkeypatch.setenv("DSTM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DSTM_SNAPSHOT_DIR", str(tmp_path / "snap"))
    sys.path.insert(0, str(Path(APP).parent))
    import data
    data = importlib.reload(data)
    out = data.import_capture(f)
    assert out["ok"] and "basis=primary" in out["message"]
    ld = data.load_credit_lines()
    assert ld["source"] == "live cache" and set(ld["cl"].symbol) == {"TATASTEEL"}
    assert ld["cl"].source_url.str.startswith("https://www.screener.in").all()


def test_ai_tab_template_mode_and_log_on_method_page():
    at = fresh()
    [b for b in at.button if (b.key or "").startswith("open_")][0].click().run()
    at.button(key="ai_go").click().run()
    no_exc(at)
    assert any("Numbers verified" in m.value and "template" in m.value for m in at.markdown)
    assert any("Due-diligence questions" in m.value for m in at.markdown)
    at.switch_page("views/method.py").run()
    no_exc(at)
    assert any(d.label == "AI_Usage_Appendix.md" for d in at.get("download_button"))


def _fake_screener(symbols):
    from tests.fixtures import FakeTransport, company_responses, make_page, schedules
    resp = {}
    for k, sym in enumerate(symbols):
        cid = str(4000 + k)
        resp.update(company_responses(sym, cid, make_page(cid=cid), make_page(cid=cid, consolidated=False),
                                      schedules(), schedules()))
    return FakeTransport(resp)


def test_live_fetch_merges_over_snapshot_and_runs_in_background(tmp_path, monkeypatch):
    """Snapshot has 3 companies; a background live fetch of 1 company replaces only that company's rows, the other
    two stay (the portfolio never shrinks), and the sidebar says 'Live + snapshot'."""
    import importlib
    import sys
    import time
    import pandas as pd
    from dstm_data.config import Settings
    from dstm_data.pipeline import Pipeline
    sys.path.insert(0, str(Path(APP).parent))
    # build a snapshot from a first (fake) fetch in another folder
    p = Pipeline(Settings(data_dir=tmp_path / "old", min_interval_s=0),
                 transport=_fake_screener(["TATASTEEL", "JSWSTEEL", "NTPC"]))
    p.refresh(pd.DataFrame({"symbol": ["TATASTEEL", "JSWSTEEL", "NTPC"], "company_name": "x", "industry": "y"}),
              force=True, progress=lambda *_: None)
    p.cache.close()
    import sqlite3
    with sqlite3.connect(tmp_path / "old" / "dstm.db") as con:
        old = pd.read_sql_query("SELECT * FROM credit_lines", con)
    old["fetched_at"] = "2026-01-01T00:00:00+00:00"
    (tmp_path / "snap").mkdir()
    old.to_parquet(tmp_path / "snap" / "credit_lines.parquet", index=False)
    monkeypatch.setenv("DSTM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DSTM_SNAPSHOT_DIR", str(tmp_path / "snap"))
    import data
    import live
    data = importlib.reload(data)
    live = importlib.reload(live)
    ld = data.load_credit_lines()
    assert ld["source"] == "offline snapshot" and ld["cl"].symbol.nunique() == 3
    assert set(data.stale_symbols(ld)) >= {"TATASTEEL", "JSWSTEEL", "NTPC"}      # fetched in January -> stale
    monkeypatch.setattr(data, "reachable", lambda timeout=8: (True, "HTTP 200"))
    monkeypatch.setattr(data, "TEST_TRANSPORT", _fake_screener(["NTPC"]))
    ok, _ = live.JOB.start(["NTPC"], "test")
    assert ok and live.JOB.running
    assert data.token() == live.JOB.snapshot()["frozen_token"]                   # frozen while running
    live.JOB.thread.join(30)
    s = live.JOB.snapshot()
    assert not s["running"] and s["ok"] and s["fetched"] == 1 and s["version"] == 1, s
    ld = data.load_credit_lines()
    assert ld["source"] == "live + snapshot" and ld["live_symbols"] == ["NTPC"]
    assert ld["cl"].symbol.nunique() == 3
    fa = data.fetched_at_by_symbol(ld["cl"])
    assert fa["NTPC"] > "2026-06-01" and fa["JSWSTEEL"].startswith("2026-01-01")
    assert "NTPC" not in data.stale_symbols(ld) and "JSWSTEEL" in data.stale_symbols(ld)
    # the app opens on the merged data
    at = fresh()
    no_exc(at)
    assert any("Live + " in m.value for m in at.sidebar.markdown)


def test_live_fetch_unreachable_and_stop(tmp_path, monkeypatch):
    import importlib
    import sys
    sys.path.insert(0, str(Path(APP).parent))
    monkeypatch.setenv("DSTM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DSTM_SNAPSHOT_DIR", str(tmp_path / "snap"))
    import data
    import live
    data = importlib.reload(data)
    live = importlib.reload(live)
    monkeypatch.setattr(data, "reachable", lambda timeout=8: (False, "HTTP 403"))
    live.JOB.start(["NTPC"], "t")
    live.JOB.thread.join(10)
    s = live.JOB.snapshot()
    assert s["ok"] is False and "HTTP 403" in s["message"] and not s["running"]
    # stop before the first company: nothing fetched, clean finish
    monkeypatch.setattr(data, "reachable", lambda timeout=8: (True, "HTTP 200"))
    monkeypatch.setattr(data, "TEST_TRANSPORT", _fake_screener(["NTPC", "LT"]))
    live.JOB._stop.set()
    out = data.refresh_symbols(["NTPC", "LT"], stop=lambda: True)
    assert out["fetched"] == 0
