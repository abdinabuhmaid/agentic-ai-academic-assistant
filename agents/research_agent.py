"""
research_agent.py
-----------------
The Research Agent. Runs once per uploaded document: it takes raw PDF text and
produces an enriched, structured knowledge base (summary, key concepts,
glossary) which it saves to the database so the other agents can reuse it
without re-reading the raw PDF every time.
"""

from agents.base_agent import call_llm_json
from prompts.research_prompts import RESEARCH_SYSTEM_PROMPT, research_user_prompt
from database import save_knowledge


def ingest(week, raw_text):
    """
    Turn raw course text into a structured knowledge-base entry and store it.
    Returns the structured result so the UI can show it immediately.
    """
    result = call_llm_json(
        RESEARCH_SYSTEM_PROMPT,
        research_user_prompt(raw_text),
    )

    summary = result.get("summary", "")
    key_concepts = result.get("key_concepts", [])
    glossary = result.get("glossary", [])

    save_knowledge(week, summary, key_concepts, glossary)
    return result
