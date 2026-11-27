"""SQLite cache: raw responses, audit log, per-company status and the tidy outputs.

Raw responses are only overwritten by a successful (HTTP 200) fetch, so a failed refresh
never destroys good data: the last good copy is served instead (offline fallback).
"""
from __future__ import annotations

import sqlite3
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from .http import normalize_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_responses (
    url_key     TEXT PRIMARY KEY,      -- normalised URL
    url         TEXT NOT NULL,
    status      INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,         -- UTC time the stored body was fetched
    mode        TEXT NOT NULL,         -- live | replay
    body_z      BLOB                   -- zlib-compressed body
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    symbol      TEXT,
    ts_utc      TEXT NOT NULL,
    url         TEXT NOT NULL,
    status      INTEGER,
    bytes       INTEGER,
    elapsed_ms  INTEGER,
    attempt     INTEGER,
    mode        TEXT,
    error       TEXT
);
CREATE TABLE IF NOT EXISTS company_status (
    symbol          TEXT PRIMARY KEY,
    company_name    TEXT,
    industry        TEXT,
    company_id      TEXT,
    primary_basis   TEXT,              -- consolidated | standalone
    basis_note      TEXT,              -- why that basis was chosen
    layout          TEXT,              -- industrial | lender
    last_attempt    TEXT,
    last_success    TEXT,              -- last time ALL planned requests succeeded
    status          TEXT,              -- ok | partial | failed_served_cache | failed_no_data | excluded_lender | not_found
    message         TEXT,
    n_requests      INTEGER,
    n_failed        INTEGER
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, started TEXT, finished TEXT, mode TEXT, args TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    symbol TEXT, basis TEXT, basis_role TEXT, statement TEXT, parent TEXT, line_item TEXT,
    period_label TEXT, period_end TEXT, period_type TEXT, period_months INTEGER,
    value REAL, unit TEXT, is_standalone_fill INTEGER, source_url TEXT, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_obs_sym ON observations(symbol);
CREATE TABLE IF NOT EXISTS credit_lines (
    symbol TEXT, basis TEXT, basis_role TEXT, frequency TEXT, period_end TEXT, period_label TEXT,
    period_months INTEGER, field TEXT, value REAL, unit TEXT, source TEXT, flag TEXT,
    source_url TEXT, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_cl_sym ON credit_lines(symbol);
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT, date TEXT, close REAL, source_url TEXT, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_px_sym ON prices(symbol);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Cache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    def close(self):
        self.con.close()

    @contextmanager
    def tx(self):
        try:
            yield self.con
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    # ------------------------------------------------------------ raw responses
    def put_response(self, url: str, status: int, body: Optional[str], fetched_at: str, mode: str):
        """Store a response. Non-200 responses never replace a stored good body."""
        key = normalize_url(url)
        if status == 200 and body is not None:
            self.con.execute(
                "INSERT OR REPLACE INTO raw_responses VALUES (?,?,?,?,?,?)",
                (key, url, status, fetched_at, mode, zlib.compress(body.encode("utf-8"), 6)))

    def get_response(self, url: str) -> Optional[dict]:
        row = self.con.execute("SELECT * FROM raw_responses WHERE url_key=?", (normalize_url(url),)).fetchone()
        if row is None:
            return None
        return {"url": row["url"], "status": row["status"], "fetched_at": row["fetched_at"],
                "mode": row["mode"], "body": zlib.decompress(row["body_z"]).decode("utf-8")}

    # ------------------------------------------------------------ audit
    def log_attempt(self, run_id: str, symbol: Optional[str], rec: dict):
        self.con.execute(
            "INSERT INTO audit_log (run_id,symbol,ts_utc,url,status,bytes,elapsed_ms,attempt,mode,error)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, symbol, rec["ts_utc"], rec["url"], rec["status"], rec["bytes"], rec["elapsed_ms"],
             rec["attempt"], rec["mode"], rec["error"]))
        self.con.commit()

    # ------------------------------------------------------------ status
    def get_status(self, symbol: str) -> Optional[dict]:
        row = self.con.execute("SELECT * FROM company_status WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None

    def set_status(self, **kw):
        cols = ["symbol", "company_name", "industry", "company_id", "primary_basis", "basis_note", "layout",
                "last_attempt", "last_success", "status", "message", "n_requests", "n_failed"]
        old = self.get_status(kw["symbol"]) or {}
        merged = {c: kw.get(c, old.get(c)) for c in cols}
        self.con.execute(f"INSERT OR REPLACE INTO company_status ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
                         [merged[c] for c in cols])
        self.con.commit()

    def all_status(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM company_status ORDER BY symbol", self.con)

    # ------------------------------------------------------------ runs
    def start_run(self, run_id: str, mode: str, args: str):
        self.con.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)", (run_id, _now(), None, mode, args, None))
        self.con.commit()

    def finish_run(self, run_id: str, summary: str):
        self.con.execute("UPDATE runs SET finished=?, summary=? WHERE run_id=?", (_now(), summary, run_id))
        self.con.commit()

    # ------------------------------------------------------------ tidy outputs
    def replace_rows(self, table: str, symbol: str, rows: Iterable[dict], columns: list[str]):
        rows = list(rows)
        with self.tx() as con:
            con.execute(f"DELETE FROM {table} WHERE symbol=?", (symbol,))
            con.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?'*len(columns))})",
                            [[r.get(c) for c in columns] for r in rows])

    def table(self, name: str, symbols: Optional[list[str]] = None) -> pd.DataFrame:
        if symbols:
            q = f"SELECT * FROM {name} WHERE symbol IN ({','.join('?'*len(symbols))})"
            return pd.read_sql_query(q, self.con, params=symbols)
        return pd.read_sql_query(f"SELECT * FROM {name}", self.con)
