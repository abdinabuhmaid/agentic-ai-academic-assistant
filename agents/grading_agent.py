"""
grading_agent.py
----------------
Grades student answers using the Grading LLM (JSON mode), classifies each
miss (conceptual / knowledge_gap / careless), and persists results to the DB.
"""

from agents.base_agent import call_llm_json
from prompts.grading_prompts import GRADING_SYSTEM_PROMPT, grading_user_prompt
from database import save_attempt, save_weak_topic
from context_bus import bus
from config import MODEL

ROUTING = {
    "conceptual":    "Teaching Agent (re-teach from a new angle)",
    "knowledge_gap": "Research Agent (supply deeper background)",
    "careless":      "No re-teach (student already knows this)",
}


def grade(quiz_id, questions, student_answers, student_username="", rubric=None):
    """
    questions       : list of question dicts from teaching_agent.generate_quiz()
    student_answers : dict mapping question id (int) -> student's typed answer
    student_username: stored on the attempt so it appears on the dashboard
    rubric          : optional professor rubric string; injected into the prompt

    Returns a dict: {"final_score": float /10, "results": [...per-question dicts...]}
    """
    graded_items = [
        {
            "id":              q["id"],
            "question":        q["question"],
            "expected_answer": q.get("expected_answer", ""),
            "student_answer":  student_answers.get(q["id"], ""),
            "concept":         q.get("concept", "unknown"),
            "prerequisite":    q.get("prerequisite", "none"),
        }
        for q in questions
    ]

    result = call_llm_json(
        GRADING_SYSTEM_PROMPT,
        grading_user_prompt(graded_items, rubric=rubric),
        model=MODEL,
    )
    results = result.get("results", [])

    # Enrich each result with original Q/A text so the professor review panel can
    # display full per-question detail without re-querying the quiz.
    id_to_item = {item["id"]: item for item in graded_items}
    for r in results:
        src = id_to_item.get(r.get("id"), {})
        r["question_text"]   = src.get("question", "")
        r["expected_answer"] = src.get("expected_answer", "")
        r["student_answer"]  = src.get("student_answer", "")

    avg = sum(r.get("score", 0) for r in results) / len(results) if results else 0
    final_score = round(avg * 10, 1)

    for r in results:
        miss = r.get("miss_type")
        if miss:
            concept = r.get("concept", "")
            bus.add_weak_topic(concept)
            if student_username and concept:
                # Infer week from the quiz; bus.current_week is the best proxy.
                try:
                    save_weak_topic(student_username, concept, bus.current_week)
                except Exception:
                    pass
            r["routing"] = ROUTING.get(miss, "Review needed")

    payload = {"final_score": final_score, "results": results}
    save_attempt(quiz_id, payload, final_score, student_username=student_username)
    return payload
