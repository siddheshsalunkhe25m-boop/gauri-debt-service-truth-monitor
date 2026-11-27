"""System prompt and output schema (structured outputs: JSON in the response's text block)."""

SYSTEM = """You are a senior credit analyst at an Indian bank writing for the credit committee.
You receive a FACT PACK for one borrower: numbered facts [F1], [F2], ... computed by the bank's Debt-Service
Truth Monitor from Screener.in data. The facts are the ONLY information you may use.

Hard rules (an automatic checker enforces the number rules; violations are rejected):
1. Every number you write must be copied from a fact and followed by its citation, e.g. "1.31x [F12]".
   You may round a fact's number to fewer decimals, never change it.
2. Do not calculate anything: no differences, sums, ratios, growth rates or averages that are not facts.
3. Do not write quantities in words (no "half", "double", "a third", "twice").
4. No outside knowledge: no news, ratings, share prices, accounting standards, regulations or forecasts.
   Do not name events that are not in the facts.
5. Covenants: choose levels ONLY from the policy and tailored-level facts (their labels start with "Policy
   covenant", "Tailored", "Creditor-days cap", "Maximum share", "Excess cash-flow sweep" or "Debt-service
   reserve") and cite them. Explain why each fits THIS borrower's weaknesses.
6. Monitoring triggers: use the "Amber trigger" facts and any policy/tailored facts; say what the bank does
   when a trigger is hit (no new numbers).
7. Due-diligence questions: one or more per red flag, specific to the flagged item, phrased as a request to
   the borrower's management or auditor. Cite the flag fact.
8. If a fact is missing (for example no Breach Clock), say it is not available; do not guess.
9. The rule-based decision fact is a starting point; you may agree or explain a different emphasis, but
   the final recommendation must be one of: Enhance, Renew, Reprice, Watch, Hold.
Style: plain, specific, banker's English; short paragraphs; no bullet characters inside fields."""

SCHEMA = {
    "type": "object",
    "properties": {
        "credit_note": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "2-3 sentences: borrower, class, recommendation"},
                "repayment_capacity": {"type": "string", "description": "FA-DSCR vs reported DSCR, Minsky state and path"},
                "cash_quality": {"type": "string", "description": "forensic adjustments: payables, exceptional, non-core, accruals"},
                "refinancing_and_liquidity": {"type": "string"},
                "covenant_outlook": {"type": "string", "description": "Breach Clock, headroom, stress"},
                "peer_position": {"type": "string"},
                "recommendation": {"type": "string", "description": "starts with one of Enhance/Renew/Reprice/Watch/Hold"},
            },
            "required": ["summary", "repayment_capacity", "cash_quality", "refinancing_and_liquidity",
                         "covenant_outlook", "peer_position", "recommendation"],
            "additionalProperties": False,
        },
        "covenants": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"covenant": {"type": "string"}, "level": {"type": "string"},
                                     "test_frequency": {"type": "string"}, "rationale": {"type": "string"}},
                      "required": ["covenant", "level", "test_frequency", "rationale"], "additionalProperties": False},
        },
        "monitoring_triggers": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"trigger": {"type": "string"}, "threshold": {"type": "string"},
                                     "action": {"type": "string"}},
                      "required": ["trigger", "threshold", "action"], "additionalProperties": False},
        },
        "dd_questions": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"question": {"type": "string"}, "red_flag": {"type": "string"},
                                     "why": {"type": "string"}},
                      "required": ["question", "red_flag", "why"], "additionalProperties": False},
        },
    },
    "required": ["credit_note", "covenants", "monitoring_triggers", "dd_questions"],
    "additionalProperties": False,
}


def user_prompt(fact_text: str) -> str:
    return ("FACT PACK (the only data you may use)\n" + fact_text +
            "\n\nWrite the credit pack: a one-page credit note (about 350-450 words across its fields), "
            "3-6 covenants, 4-6 monitoring triggers, and due-diligence questions based on this borrower's own red "
            "flags (at least one per flag; if there are none, 3 questions on the weakest metrics). "
            "Cite a fact after every number.")


def correction_prompt(problems: list, structure: list) -> str:
    lines = ["The automatic checker rejected your draft. Fix ONLY these problems and return the full JSON again:"]
    for p in problems[:30]:
        lines.append(f"- {p['field']}: '{p['text']}' -> {p['matched']}. Context: {p['context']}")
    for s in structure:
        lines.append(f"- {s}")
    lines.append("Every number must be copied from a fact and cited; delete any number you cannot cite.")
    return "\n".join(lines)
