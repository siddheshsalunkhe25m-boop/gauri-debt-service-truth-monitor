"""Live Screener fetch that runs on the server in a background thread.

Why a thread: a full refresh is ~12 requests per company at 1 request/second (about 40 minutes for the universe).
Inside a normal Streamlit button the fetch would stop the moment the browser tab closed or the phone locked.
Here it keeps going on the server; any visitor sees the same progress, and the dashboard switches to the new
figures when the job ends (or earlier, on request).

One job at a time per server process. Figures are written company by company into data/dstm.db, so stopping
or a crash never loses what was already fetched.
"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

SECONDS_PER_COMPANY = 13          # 1 page + 10 schedules + 1 price series at 1 req/s, plus parsing


class LiveJob:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = {"running": False, "version": 0}

    # -------------------------------------------------------------- read
    def snapshot(self) -> dict:
        with self._lock:
            d = dict(self.state)
        if d.get("running"):
            el = time.time() - d["t0"]
            d["elapsed_s"] = el
            done = max(d.get("i", 0), 0)
            left = d["n"] - done
            per = el / done if done else SECONDS_PER_COMPANY
            d["eta_s"] = max(left, 0) * per
        return d

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self.state.get("running"))

    def _set(self, **kw):
        with self._lock:
            self.state.update(kw)

    # -------------------------------------------------------------- control
    def start(self, symbols: list[str], label: str, force: bool = True) -> tuple[bool, str]:
        import data                                       # late import: data imports nothing from here at load
        frozen = data._raw_token()                        # outside the lock: data.token() itself reads the job state
        with self._lock:
            if self.state.get("running"):
                return False, "A live fetch is already running; wait for it or stop it first."
            self._stop.clear()
            self.state.update(running=True, label=label, n=len(symbols), i=0, current="checking Screener.in…",
                              t0=time.time(), log=[], ok=None, message="", failures=[], frozen_token=frozen,
                              started=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.thread = threading.Thread(target=self._run, args=(symbols, force), daemon=True, name="dstm-live")
        self.thread.start()
        return True, "started"

    def stop(self):
        self._stop.set()
        self._set(current="stopping after the current company…")

    def _run(self, symbols, force):
        import data
        try:
            def prog(i, n, msg):
                with self._lock:
                    self.state["i"] = i
                    self.state["current"] = msg
                    self.state["log"] = (self.state.get("log", []) + [msg])[-30:]
            out = data.refresh_symbols(symbols, force=force, progress=prog, stop=self._stop.is_set)
        except Exception as e:                            # never leave the job stuck in "running"
            out = {"ok": False, "message": f"Live fetch crashed ({type(e).__name__}: {e})",
                   "trace": traceback.format_exc()[-2000:]}
        fails = out.get("failures")
        fails = fails[["symbol", "status"]].to_dict("records") if isinstance(fails, pd.DataFrame) and len(fails) else []
        with self._lock:
            self.state.update(running=False, ok=out.get("ok"), message=out.get("message", ""), failures=fails,
                              finished=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              stopped=self._stop.is_set(), version=self.state.get("version", 0) + 1,
                              fetched=out.get("fetched", 0))


JOB = LiveJob()          # module-level: Streamlit re-runs app.py but keeps imported modules, so this survives reruns


def fmt_secs(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600}h {s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m {s % 60:02d}s"
