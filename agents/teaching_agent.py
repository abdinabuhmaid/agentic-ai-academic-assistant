"""
teaching_agent.py
-----------------
The Teaching Agent: tutoring, quiz generation, and re-teaching.
"""

from agents.base_agent import call_llm, call_llm_json
from prompts.teaching_prompts import (
    TUTOR_SYSTEM_PROMPT, tutor_user_prompt,
    QUIZ_SYSTEM_PROMPT, quiz_user_prompt,
    MCQ_QUIZ_SYSTEM_PROMPT, mcq_quiz_user_prompt,
    REGEN_OPTIONS_SYSTEM_PROMPT, regen_options_user_prompt,
    RETEACH_SYSTEM_PROMPT, reteach_user_prompt,
    KNOWLEDGE_GAP_SYSTEM_PROMPT, knowledge_gap_user_prompt,
    COMP_CHECK_SYSTEM_PROMPT, comp_check_user_prompt,
)
from database import save_quiz
from context_bus import bus
from config import FAST_MODEL


def tutor(student_message):
    """Answer a student question using the current week's knowledge base."""
    knowledge = bus.knowledge_for_current_week()
    if knowledge is None:
        return (
            f"No material has been ingested for Week {bus.current_week} yet. "
            "Ask your professor to upload the course PDF first."
        )
    reply = call_llm(
        TUTOR_SYSTEM_PROMPT,
        tutor_user_prompt(knowledge, student_message),
        model=FAST_MODEL,
        temperature=0.4,
    )
    bus.add_message("student", student_message)
    bus.add_message("teacher", reply)
    return reply


def generate_quiz(num_questions=4, weak_topics=None):
    """
    Generate a tagged quiz for the current week and save it.
    If weak_topics is provided, the prompt hints the model to include related questions.
    Returns (quiz_id, list_of_questions).
    """
    knowledge = bus.knowledge_for_current_week()
    if knowledge is None:
        raise ValueError(
            f"No material ingested for Week {bus.current_week}. Upload a PDF first."
        )

    user_prompt = quiz_user_prompt(knowledge, num_questions, weak_topics=weak_topics)
    result = call_llm_json(QUIZ_SYSTEM_PROMPT, user_prompt)
    questions = result.get("questions", [])
    quiz_id = save_quiz(bus.current_week, questions)
    bus.last_quiz_id = quiz_id
    return quiz_id, questions


def generate_mcq_quiz(num_questions=4, weak_topics=None):
    """
    Generate a multiple-choice quiz for the current week and save it.
    Returns (quiz_id, list_of_questions).
    """
    knowledge = bus.knowledge_for_current_week()
    if knowledge is None:
        raise ValueError(
            f"No material ingested for Week {bus.current_week}. Upload a PDF first."
        )
    user_prompt = mcq_quiz_user_prompt(knowledge, num_questions, weak_topics=weak_topics)
    result = call_llm_json(MCQ_QUIZ_SYSTEM_PROMPT, user_prompt)
    questions = result.get("questions", [])
    quiz_id = save_quiz(bus.current_week, questions)
    bus.last_quiz_id = quiz_id
    return quiz_id, questions


def regenerate_mcq_options(questions):
    """Re-generate options + correct letter for a list of MCQ questions.

    Called at confirm time so that professor-edited question text gets
    matching options instead of keeping the stale original ones.
    """
    knowledge = bus.knowledge_for_current_week()
    if knowledge is None:
        return questions
    result = call_llm_json(
        REGEN_OPTIONS_SYSTEM_PROMPT,
        regen_options_user_prompt(questions, knowledge),
    )
    id_map = {u["id"]: u for u in result.get("questions", [])}
    for q in questions:
        regen = id_map.get(q["id"])
        if regen:
            q["options"] = regen.get("options", q.get("options", {}))
            q["correct"]  = regen.get("correct",  q.get("correct",  "A"))
    return questions


def reteach(concept, question, wrong_answer):
    """
    Re-explain a missed concept from a new angle.
    Returns {"explanation": str, "check_question": str}.
    """
    knowledge = bus.knowledge_for_current_week()
    reply = call_llm(
        RETEACH_SYSTEM_PROMPT,
        reteach_user_prompt(concept, question, wrong_answer, knowledge),
        model=FAST_MODEL,
        temperature=0.5,
    )
    if "CHECK:" in reply:
        explanation, _, check_q = reply.partition("CHECK:")
        return {"explanation": explanation.strip(), "check_question": check_q.strip()}
    return {"explanation": reply.strip(), "check_question": f"Explain '{concept}' in your own words."}


def reteach_knowledge_gap(concept):
    """
    Provide deeper background on a concept from the knowledge base.
    Returns {"explanation": str, "check_question": str}.
    """
    knowledge = bus.knowledge_for_current_week()
    reply = call_llm(
        KNOWLEDGE_GAP_SYSTEM_PROMPT,
        knowledge_gap_user_prompt(concept, knowledge),
        model=FAST_MODEL,
        temperature=0.4,
    )
    if "CHECK:" in reply:
        explanation, _, check_q = reply.partition("CHECK:")
        return {"explanation": explanation.strip(), "check_question": check_q.strip()}
    return {"explanation": reply.strip(), "check_question": f"What does '{concept}' mean?"}


def evaluate_comp_check(check_question, student_answer):
    """Give brief feedback on the student's answer to a comprehension-check question."""
    return call_llm(
        COMP_CHECK_SYSTEM_PROMPT,
        comp_check_user_prompt(check_question, student_answer),
        model=FAST_MODEL,
        temperature=0.3,
    )
