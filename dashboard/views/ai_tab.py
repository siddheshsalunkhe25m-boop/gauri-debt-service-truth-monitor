"""AI credit pack tab (company drill-down) and AI log section (method page)."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from dstm_ai.log import AILog
from dstm_ai.run import api_available, generate, model_name, to_markdown


def ai_status() -> str:
    return (f"Claude API key found · model `{model_name()}`" if api_available()
            else "No `ANTHROPIC_API_KEY` in the environment: template mode (same facts, no AI)")


def render_ai_tab(s: dict, a: dict, cfg, peers: pd.DataFrame, cfg_json: str):
    st.caption("Claude receives only the numbered facts below (computed by this tool), never statements or web content. "
               "Every number it writes is checked against those facts; a failing draft gets one correction round, "
               "then the rule-based template is used. Every run is logged for the AI-usage appendix.")
    st.markdown(f"**Status:** {ai_status()}")
    key = "ai_" + hashlib.sha1(f"{s['symbol']}|{cfg_json}".encode()).hexdigest()[:12]
    if st.button("Generate credit pack", type="primary", key="ai_go"):
        with st.spinner("Writing the credit pack and checking every number…"):
            st.session_state[key] = generate(s, a, cfg, peers)
    r = st.session_state.get(key)
    if not r:
        return
    chk = r["check"]
    who = f"✍️ Written by **Claude** (`{r['model']}`)" if r["mode"] == "claude" else "📄 Written by the **template** (no AI)"
    badge = "✅" if chk["passed"] else "⛔"
    st.markdown(f"{who} · {badge} **Numbers verified {chk['n_verified']} of {chk['n_numbers']}** · run `{r['run_id']}`")
    if r.get("fallback_reason") and r["mode"] == "template":
        st.info(f"Template used because: {r['fallback_reason']}.", icon="ℹ️")
    o = r["output"]
    n = o["credit_note"]
    with st.container(border=True):
        st.markdown(f"#### Credit note: {s['company_name']}")
        for k, title in (("summary", "Summary"), ("repayment_capacity", "Repayment capacity"), ("cash_quality", "Cash quality"),
                         ("refinancing_and_liquidity", "Refinancing and liquidity"), ("covenant_outlook", "Covenant outlook"),
                         ("peer_position", "Peer position"), ("recommendation", "Recommendation")):
            st.markdown(f"**{title}.** {n.get(k, '')}")
    st.markdown("##### Tailored covenant suggestions")
    st.dataframe(pd.DataFrame(o["covenants"]), hide_index=True, width="stretch")
    st.markdown("##### Monitoring triggers")
    st.dataframe(pd.DataFrame(o["monitoring_triggers"]), hide_index=True, width="stretch")
    st.markdown("##### Due-diligence questions for the borrower")
    for i, q in enumerate(o["dd_questions"], 1):
        st.markdown(f"{i}. {q['question']}  \n<span style='opacity:.7;font-size:.9rem'>Red flag: {q['red_flag']} · "
                    f"Why: {q['why']}</span>", unsafe_allow_html=True)
    st.download_button("Download credit pack (.md)", to_markdown(r, s).encode("utf-8"),
                       f"credit_note_{s['symbol']}.md", "text/markdown")
    with st.expander(f"Facts sent to the model ({len(r['pack'].facts)})"):
        st.dataframe(pd.DataFrame([{"id": f.id, "fact": f.label, "value": f.display, "source": f.source}
                                   for f in r["pack"].facts]), hide_index=True, width="stretch")
    with st.expander("Number check details"):
        st.dataframe(pd.DataFrame(chk["items"])[["field", "text", "cited", "status", "matched"]] if chk["items"] else
                     pd.DataFrame(), hide_index=True, width="stretch")
    if r["rejected"]:
        with st.expander(f"Rejected drafts ({len(r['rejected'])})"):
            for d in r["rejected"]:
                st.markdown(f"**Attempt {d['attempt']}** - problems:")
                st.dataframe(pd.DataFrame(d["check"]["problems"])[["field", "text", "matched"]], hide_index=True)
                st.json(d["output"], expanded=False)


def render_ai_log():
    log = AILog()
    s = log.summary()
    st.markdown(f"**Status:** {ai_status()} · log file `{log.path}`")
    if s.empty:
        st.write("No AI runs logged yet.")
        return
    st.dataframe(s, hide_index=True, width="stretch")
    c1, c2, c3 = st.columns(3)
    c1.download_button("AI_Usage_Appendix.md", log.appendix_markdown().encode("utf-8"), "AI_Usage_Appendix.md",
                       "text/markdown", width="stretch")
    with tempfile.TemporaryDirectory() as d:
        x = Path(log.appendix_xlsx(Path(d) / "AI_Usage_Log.xlsx")).read_bytes()
    c2.download_button("AI_Usage_Log.xlsx", x, "AI_Usage_Log.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    c3.download_button("ai_log.jsonl (raw)", log.path.read_bytes(), "ai_log.jsonl", "application/json", width="stretch")
