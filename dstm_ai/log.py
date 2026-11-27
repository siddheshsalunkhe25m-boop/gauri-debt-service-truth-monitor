"""Prompt / output log for the AI-usage appendix.

ai_logs/ai_log.jsonl - one JSON line per generation: system prompt (+ SHA-256), full user prompt (fact pack),
every API attempt (raw output, number-check result, tokens, latency, errors), rejected drafts, final mode and
output. The API key is never logged. Folder override: DSTM_AI_LOG_DIR.
Exports: AI_Usage_Appendix.md (summary table + full prompts/outputs) and AI_Usage_Log.xlsx (one row per run).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AILog:
    def __init__(self, folder: str | Path | None = None):
        self.folder = Path(folder or os.environ.get("DSTM_AI_LOG_DIR", ROOT / "ai_logs"))
        self.path = self.folder / "ai_log.jsonl"

    def write(self, rec: dict) -> str:
        self.folder.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        rec = {"run_id": run_id, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **rec}
        blob = json.dumps(rec, default=str)
        assert "sk-ant-" not in blob, "refusing to log something that looks like an API key"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(blob + "\n")
        return run_id

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def summary(self) -> pd.DataFrame:
        rows = []
        for r in self.read():
            att = r.get("attempts", [])
            fc = r.get("final_check", {})
            rows.append({"run_id": r["run_id"], "time": r["ts"], "symbol": r.get("symbol"), "company": r.get("company"),
                         "purpose": r.get("purpose"), "model": r.get("model"), "final_mode": r.get("final_mode"),
                         "api_attempts": len(att), "fallback_reason": r.get("fallback_reason", ""),
                         "input_tokens": sum(a.get("input_tokens") or 0 for a in att),
                         "output_tokens": sum(a.get("output_tokens") or 0 for a in att),
                         "latency_ms": sum(a.get("latency_ms") or 0 for a in att),
                         "numbers_in_output": fc.get("n_numbers"), "numbers_verified": fc.get("n_verified"),
                         "check_passed": fc.get("passed"), "rejected_drafts": len(r.get("rejected_drafts", [])),
                         "system_sha256": r.get("system_sha256", "")[:12], "n_facts": len(r.get("facts", []))})
        return pd.DataFrame(rows)

    def appendix_markdown(self) -> str:
        runs = self.read()
        s = self.summary()
        lines = ["# Appendix: use of generative AI", "",
                 "Tool: Anthropic Claude via the Anthropic API, called from the Debt-Service Truth Monitor (`dstm_ai`). "
                 "The model received only a numbered fact pack of numbers computed by the project's Python code; it did "
                 "not receive financial statements, filings or web content. Every number in every output was checked "
                 "automatically against the fact pack; drafts that failed were corrected once and otherwise replaced "
                 "by a rule-based template. Covenant and trigger levels were computed by fixed rules in Python and only "
                 "selected and explained by the model.", "",
                 f"Runs logged: {len(s)}; Claude outputs accepted: {int((s.final_mode == 'claude').sum()) if len(s) else 0}; "
                 f"template outputs: {int((s.final_mode == 'template').sum()) if len(s) else 0}; rejected drafts: "
                 f"{int(s.rejected_drafts.sum()) if len(s) else 0}.", "", "## Run summary", ""]
        if len(s):
            lines.append(s.drop(columns=["purpose"]).to_markdown(index=False))
        prompts = {r.get("system_sha256"): r.get("system_prompt") for r in runs}
        lines += ["", "## System prompts used"]
        for h, p in prompts.items():
            lines += ["", f"### SHA-256 {h}", "```", p or "", "```"]
        lines += ["", "## Runs in full"]
        for r in runs:
            lines += ["", f"### {r['run_id']} - {r.get('company')} ({r.get('symbol')}) - {r.get('final_mode')}",
                      f"Model: {r.get('model')}. Fallback reason: {r.get('fallback_reason') or 'none'}.", "",
                      "**User prompt (fact pack)**", "```", r.get("user_prompt", ""), "```"]
            for a in r.get("attempts", []):
                lines += [f"**Attempt {a.get('attempt')}** - tokens in {a.get('input_tokens')}, out {a.get('output_tokens')}, "
                          f"{a.get('latency_ms')} ms; check passed: {(a.get('check') or {}).get('passed')}"
                          + (f"; error: {a['error']}" if a.get("error") else "")]
                if a.get("attempt", 1) > 1:
                    lines += ["Correction request:", "```", a.get("request_last_message", ""), "```"]
                if a.get("raw_text"):
                    lines += ["```json", a["raw_text"], "```"]
                for p in (a.get("check") or {}).get("problems", [])[:20]:
                    lines.append(f"- rejected number: {p['field']} '{p['text']}' ({p['matched']})")
            lines += ["**Final output**", "```json", json.dumps(r.get("final_output"), indent=1), "```"]
        return "\n".join(lines)

    def appendix_xlsx(self, path: str | Path) -> str:
        with pd.ExcelWriter(path) as xw:
            self.summary().to_excel(xw, sheet_name="Runs", index=False)
            rows = []
            for r in self.read():
                for a in r.get("attempts", []):
                    rows.append({"run_id": r["run_id"], "attempt": a.get("attempt"), "error": a.get("error"),
                                 "passed": (a.get("check") or {}).get("passed"),
                                 "problems": json.dumps((a.get("check") or {}).get("problems", []))[:30000],
                                 "raw_text": (a.get("raw_text") or "")[:30000]})
            pd.DataFrame(rows).to_excel(xw, sheet_name="Attempts", index=False)
            pd.DataFrame([{"run_id": r["run_id"], "system_prompt": r.get("system_prompt"),
                           "user_prompt": (r.get("user_prompt") or "")[:30000],
                           "final_output": json.dumps(r.get("final_output"))[:30000]} for r in self.read()]
                         ).to_excel(xw, sheet_name="Prompts", index=False)
        return str(path)
