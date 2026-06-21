"""
Prompt template for the Grading Agent.

The Grading Agent scores a student's answers against the model answers, and
for each missed question classifies the mistake as:
  - conceptual    : misunderstood the idea       -> re-teach (Teaching Agent)
  - knowledge_gap : missing background knowledge  -> Research Agent
  - careless      : knew it but slipped           -> not re-taught on purpose

Per the report, forcing structured JSON output (rather than free text) makes
grading far more consistent.
"""

GRADING_SYSTEM_PROMPT = """You are the Grading Agent in an academic AI assistant.
You grade a student's short answers against provided model answers and concept
tags, then classify any mistakes.

You will receive a list of questions. Each has: the question, the expected
answer, the student's answer, the concept it tests, and the prerequisite.

For EACH question, decide a score from 0 to 1 (1 = fully correct, 0.5 = partial,
0 = wrong) and, if it is not fully correct, classify the miss as one of:
"conceptual", "knowledge_gap", or "careless".

Return a JSON object with exactly this shape:

{
  "results": [
    {
      "id": 1,
      "score": 0 | 0.5 | 1,
      "miss_type": "conceptual" | "knowledge_gap" | "careless" | null,
      "concept": "the concept tag for this question",
      "feedback": "one short sentence of feedback for the student"
    },
    ...
  ]
}

Rules:
- Be fair but consistent. Reward correct meaning even if wording differs.
- miss_type is null only when score is 1.
- Respond with the JSON object only.
"""


def grading_user_prompt(graded_items, rubric=None):
    """
    graded_items: list of dicts with question, expected_answer, student_answer,
                  concept, prerequisite.
    rubric: optional professor-authored rubric string.
    """
    rubric_section = f"\nProfessor's rubric:\n{rubric}\n" if rubric else ""
    lines = []
    for item in graded_items:
        lines.append(
            f"Question {item['id']}: {item['question']}\n"
            f"  Expected answer: {item['expected_answer']}\n"
            f"  Student answer: {item['student_answer']}\n"
            f"  Concept: {item['concept']} | Prerequisite: {item['prerequisite']}"
        )
    return f"Grade these answers:{rubric_section}\n\n" + "\n\n".join(lines)
