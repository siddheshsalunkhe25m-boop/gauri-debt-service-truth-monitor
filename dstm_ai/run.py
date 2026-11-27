"""Generate the AI credit pack for one company.

Flow: fact pack -> Claude (structured JSON output) -> automatic number check -> if it fails, ONE correction
round with the checker's findings -> if it still fails, or there is no API key, or the API errors: template
output from the same facts (also checked). Every step is logged (log.py).

Configuration (environment only; nothing is stored):
  ANTHROPIC_API_KEY   API key. Missing -> template mode.
  DSTM_AI_MODEL       model id, default claude-opus-5-5 (Anthropic's recommended default, Nov 2026);
                      cheaper / faster: claude-sonnet-5-5
  DSTM_AI_MAX_TOKENS  default 4000
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

from dstm_rts.config import RTSConfig

from .check import check_output
from .facts import build_pack
from .log import AILog, sha
from .prompts import SCHEMA, SYSTEM, correction_prompt, user_prompt
from .template import template_output

DEFAULT_MODEL = "claude-opus-5-5"


def model_name() -> str:
    return os.environ.get("DSTM_AI_MODEL", DEFAULT_MODEL)


def api_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def make_client():
    if not api_available():
        return None
    import anthropic
    return anthropic.Anthropic(max_retries=2, timeout=120)


def call_model(client, model: str, messages: list, max_tokens: int) -> dict:
    kw = dict(model=model, max_tokens=max_tokens, system=SYSTEM, messages=messages,
              output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    t0 = time.monotonic()
    try:
        r = client.messages.create(**kw)
    except TypeError:                                # older SDK without the output_config argument
        oc = kw.pop("output_config")
        r = client.messages.create(**kw, extra_body={"output_config": oc})
    text = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text")
    u = getattr(r, "usage", None)
    return {"text": text, "stop_reason": getattr(r, "stop_reason", None),
            "input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None),
            "latency_ms": int((time.monotonic() - t0) * 1000), "model": getattr(r, "model", model)}


def generate(s: dict, a: dict, cfg: RTSConfig, peers=None, client="auto", log: AILog | None = None,
             max_tokens: int | None = None) -> dict:
    log = log or AILog()
    pack, flags, rec = build_pack(s, a or {}, cfg, peers)
    uprompt = user_prompt(pack.as_prompt())
    model = model_name()
    max_tokens = max_tokens or int(os.environ.get("DSTM_AI_MAX_TOKENS", "4000"))
    rec_log = {"symbol": s.get("symbol"), "company": s.get("company_name"), "purpose": "credit pack (note, covenants, "
               "triggers, due-diligence questions)", "model": model, "system_prompt": SYSTEM, "system_sha256": sha(SYSTEM),
               "schema_sha256": sha(json.dumps(SCHEMA, sort_keys=True)), "user_prompt": uprompt,
               "facts": pack.to_records(), "settings": asdict(cfg), "attempts": []}
    if client == "auto":
        client = make_client()
    out, check, mode, rejected = None, None, "template", []
    if client is None:
        rec_log["fallback_reason"] = "no ANTHROPIC_API_KEY in the environment"
    else:
        messages = [{"role": "user", "content": uprompt}]
        for attempt in (1, 2):
            entry = {"attempt": attempt, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                     "request_last_message": messages[-1]["content"] if attempt > 1 else "(user prompt above)"}
            try:
                resp = call_model(client, model, messages, max_tokens)
            except Exception as e:                    # network, auth, rate limit, bad request
                entry["error"] = f"{type(e).__name__}: {str(e)[:500]}"
                rec_log["attempts"].append(entry)
                rec_log["fallback_reason"] = "API error"
                break
            entry.update({k: resp[k] for k in ("stop_reason", "input_tokens", "output_tokens", "latency_ms", "model")})
            entry["raw_text"] = resp["text"]
            try:
                parsed = json.loads(resp["text"])
            except json.JSONDecodeError as e:
                entry["error"] = f"invalid JSON: {e}"
                rec_log["attempts"].append(entry)
                rec_log["fallback_reason"] = "invalid JSON"
                break
            chk = check_output(parsed, pack)
            entry["check"] = {k: chk[k] for k in ("passed", "n_numbers", "n_verified", "n_uncited", "problems", "structure")}
            rec_log["attempts"].append(entry)
            if chk["passed"]:
                out, check, mode = parsed, chk, "claude"
                break
            rejected.append({"attempt": attempt, "output": parsed, "check": entry["check"]})
            messages = messages + [{"role": "assistant", "content": resp["text"]},
                                   {"role": "user", "content": correction_prompt(chk["problems"], chk["structure"])}]
        else:
            rec_log["fallback_reason"] = "draft failed the number check after one correction round"
    if out is None:
        out = template_output(pack, flags, rec)
        check = check_output(out, pack)
    rec_log.update({"final_mode": mode, "final_output": out,
                    "final_check": {k: check[k] for k in ("passed", "n_numbers", "n_verified", "n_uncited", "problems", "structure")},
                    "rejected_drafts": rejected})
    run_id = log.write(rec_log)
    return {"run_id": run_id, "mode": mode, "model": model if mode == "claude" else None, "output": out, "check": check,
            "pack": pack, "rejected": rejected, "fallback_reason": rec_log.get("fallback_reason"),
            "attempts": rec_log["attempts"], "rule_decision": rec}


def to_markdown(res: dict, s: dict) -> str:
    o = res["output"]
    n = o["credit_note"]
    who = "Claude (" + (res.get("model") or "") + ")" if res["mode"] == "claude" else "template (no AI)"
    chk = res["check"]
    lines = [f"# Credit note: {s.get('company_name')} ({s.get('symbol')})", "",
             f"*Written by {who}. Numbers verified {chk['n_verified']} of {chk['n_numbers']}. Run {res['run_id']}. "
             "Every number cites a fact [F#] from the Debt-Service Truth Monitor fact pack listed at the end.*", ""]
    for k, title in (("summary", "Summary"), ("repayment_capacity", "Repayment capacity"), ("cash_quality", "Cash quality"),
                     ("refinancing_and_liquidity", "Refinancing and liquidity"), ("covenant_outlook", "Covenant outlook"),
                     ("peer_position", "Peer position"), ("recommendation", "Recommendation")):
        lines += [f"## {title}", n.get(k, ""), ""]
    lines += ["## Covenant package", "| Covenant | Level | Test | Rationale |", "|---|---|---|---|"]
    lines += [f"| {c['covenant']} | {c['level']} | {c.get('test_frequency', '')} | {c['rationale']} |" for c in o["covenants"]]
    lines += ["", "## Monitoring triggers", "| Trigger | Threshold | Action |", "|---|---|---|"]
    lines += [f"| {t['trigger']} | {t['threshold']} | {t['action']} |" for t in o["monitoring_triggers"]]
    lines += ["", "## Due-diligence questions for the borrower"]
    lines += [f"{i}. {q['question']}  \n   *Red flag:* {q['red_flag']}. *Why:* {q['why']}" for i, q in enumerate(o["dd_questions"], 1)]
    lines += ["", "## Fact pack", "| Id | Fact | Value |", "|---|---|---|"]
    lines += [f"| {f.id} | {f.label} | {f.display} |" for f in res["pack"].facts]
    return "\n".join(lines)
