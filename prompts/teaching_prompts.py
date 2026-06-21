"""
Prompt templates for the Teaching Agent.

The Teaching Agent has separate modes, each with its own prompt:
  - tutoring        : conversational help for the student
  - quiz generation : creates a tagged quiz from the week's material
  - re-teach        : (feedback loop) re-explains a missed concept — see TODO

Design note from the report: the Teaching Agent must NOT see the grading
rubric during quiz generation, to prevent question/answer leakage.
"""

# --- Tutoring mode ----------------------------------------------------------

TUTOR_SYSTEM_PROMPT = """You are the Teaching Agent, a friendly tutor.
You help a student understand the course material for the current week.

You are given the week's structured knowledge base (summary, key concepts,
glossary). Answer the student's questions using that material. Explain clearly,
use short examples, and if something is outside the provided material say so
rather than guessing.
"""


def tutor_user_prompt(knowledge, student_message):
    return (
        f"Week summary:\n{knowledge.get('summary', '')}\n\n"
        f"Key concepts: {', '.join(knowledge.get('key_concepts', []))}\n\n"
        f"Student question: {student_message}"
    )


# --- Quiz generation mode ---------------------------------------------------

QUIZ_SYSTEM_PROMPT = """You are the Teaching Agent in quiz-generation mode.
Create a short quiz from the week's material.

Every question MUST be tagged with the concept it tests and any prerequisite
knowledge. These tags are used later to classify mistakes cheaply, so they are
required.

Return a JSON object with exactly this shape:

{
  "questions": [
    {
      "id": 1,
      "question": "the question text",
      "expected_answer": "a concise model answer",
      "concept": "the concept area this tests",
      "prerequisite": "prerequisite knowledge, or 'none'"
    },
    ...
  ]
}

Rules:
- Base questions ONLY on the provided material.
- Make questions short-answer (not multiple choice) for this version.
- Respond with the JSON object only.
"""


def quiz_user_prompt(knowledge, num_questions=4, weak_topics=None):
    base = (
        f"Generate {num_questions} short-answer questions.\n\n"
        f"Week summary:\n{knowledge.get('summary', '')}\n\n"
        f"Key concepts: {', '.join(knowledge.get('key_concepts', []))}"
    )
    if weak_topics:
        base += f"\n\nThe student has previously struggled with: {', '.join(weak_topics)}. Include at least one question on those topics."
    return base


# --- MCQ Quiz generation mode -----------------------------------------------

MCQ_QUIZ_SYSTEM_PROMPT = """You are the Teaching Agent in quiz-generation mode.
Create a multiple-choice quiz from the week's material.

Every question MUST have exactly 4 options (A, B, C, D), one correct answer,
and be tagged with the concept it tests and any prerequisite knowledge.

Return a JSON object with exactly this shape:

{
  "questions": [
    {
      "id": 1,
      "question": "the question text",
      "options": {
        "A": "first option text",
        "B": "second option text",
        "C": "third option text",
        "D": "fourth option text"
      },
      "correct": "B",
      "concept": "the concept area this tests",
      "prerequisite": "prerequisite knowledge, or 'none'"
    }
  ]
}

Rules:
- Base questions ONLY on the provided material.
- Exactly one option must be correct; the other three must be plausible but wrong.
- Vary which letter (A/B/C/D) is correct across questions.
- Respond with the JSON object only.
"""


def mcq_quiz_user_prompt(knowledge, num_questions=4, weak_topics=None):
    base = (
        f"Generate {num_questions} multiple-choice questions.\n\n"
        f"Week summary:\n{knowledge.get('summary', '')}\n\n"
        f"Key concepts: {', '.join(knowledge.get('key_concepts', []))}"
    )
    if weak_topics:
        base += f"\n\nThe student has previously struggled with: {', '.join(weak_topics)}. Include at least one question on those topics."
    return base


# --- MCQ option regeneration (after professor edits question text) -----------

REGEN_OPTIONS_SYSTEM_PROMPT = """You are an exam author. You are given a list of multiple-choice questions whose text may have been edited.
For EACH question, generate exactly 4 answer options (A, B, C, D) that fit the question as written, plus identify the correct letter.

Return a JSON object with exactly this shape:
{
  "questions": [
    {
      "id": <same id as input>,
      "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
      "correct": "B"
    }
  ]
}

Rules:
- Do NOT alter any question text — only supply options.
- Exactly one option must be correct; the other three must be plausible but wrong.
- Vary which letter (A/B/C/D) is correct across questions.
- Base answers on the provided course material summary.
- Respond with the JSON object only.
"""


def regen_options_user_prompt(questions, knowledge):
    q_lines = "\n".join(
        f'{i + 1}. (id={q["id"]}) {q["question"]}'
        for i, q in enumerate(questions)
    )
    return (
        f"Course material summary:\n{knowledge.get('summary', '')}\n\n"
        f"Key concepts: {', '.join(knowledge.get('key_concepts', []))}\n\n"
        f"Questions to generate options for:\n{q_lines}"
    )


# --- Re-teach mode (feedback loop) ------------------------------------------

RETEACH_SYSTEM_PROMPT = """You are the Teaching Agent in re-teach mode.
A student missed a quiz question on a specific concept.

Re-explain the concept from a FRESH angle using a simple, concrete example.
Keep the explanation to 3-5 sentences.

Then, on its own line starting with exactly "CHECK:", write ONE short
comprehension-check question to verify the student now understands.

Format:
[explanation]
CHECK: [one question]
"""


def reteach_user_prompt(concept, question, wrong_answer, knowledge):
    summary = knowledge.get("summary", "") if knowledge else ""
    terms = [g["term"] for g in (knowledge.get("glossary") or [])]
    glossary_line = f"Key terms: {', '.join(terms)}" if terms else ""
    return (
        f"Concept to re-teach: {concept}\n\n"
        f"Original question: {question}\n"
        f"Student's answer:  {wrong_answer}\n\n"
        f"Week context:\n{summary}\n"
        f"{glossary_line}"
    )


# --- Knowledge-gap background (Research Agent re-teach) ---------------------

KNOWLEDGE_GAP_SYSTEM_PROMPT = """You are the Research Agent providing background study material.
A student is missing prerequisite knowledge on a concept.

Supply a concise but complete explanation (4-6 sentences) that fills the gap,
drawing only from the provided material.

Then, on its own line starting with exactly "CHECK:", write ONE question to
confirm the student has absorbed the background.

Format:
[background explanation]
CHECK: [one question]
"""


def knowledge_gap_user_prompt(concept, knowledge):
    glossary = knowledge.get("glossary") or [] if knowledge else []
    related = [g for g in glossary if concept.lower() in g.get("term", "").lower()]
    summary = knowledge.get("summary", "") if knowledge else ""
    definition_block = ""
    if related:
        definition_block = "\n".join(
            f"- {g['term']}: {g['definition']}" for g in related
        )
    return (
        f"Concept with knowledge gap: {concept}\n\n"
        f"Relevant definitions from material:\n{definition_block}\n\n"
        f"Week summary:\n{summary}"
    )


# --- Comprehension-check evaluation -----------------------------------------

COMP_CHECK_SYSTEM_PROMPT = """You are a tutor evaluating a student's answer to a comprehension-check question.
Give brief, encouraging feedback in 1-2 sentences.
Tell them clearly whether they got it right and what to keep in mind.
"""


def comp_check_user_prompt(check_question, student_answer):
    return f"Check question: {check_question}\nStudent's answer: {student_answer}"
