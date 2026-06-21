"""
app.py — Phases 3-7: full backend wiring.
Run:  python app.py
"""

import os
import tempfile
from datetime import datetime

import gradio as gr
import openpyxl
import openpyxl.styles

from config import ROLLING_WINDOW, AT_RISK_THRESHOLD
from database import (
    init_db, seed_users, verify_login,
    get_dashboard_rows, get_available_weeks, get_latest_week,
    get_rubric, save_rubric, save_resource, get_weak_topics,
    get_resources_list, get_students,
    get_attempts_for_student, get_attempt_by_id,
    approve_attempt as db_approve_attempt,
    get_approved_grades, get_knowledge, get_quiz_questions,
    get_num_questions, get_quiz_type, get_rubric_settings, save_attempt,
    get_resources_with_ids, delete_resource,
    get_rubric_settings_by_resource, get_num_questions_by_resource, get_quiz_type_by_resource,
    get_resource_week, save_confirmed_quiz, get_confirmed_quiz_for_resource, get_confirmed_quiz_for_week,
)
from ingestion import extract_text_from_pdf
from agents.research_agent import ingest
from agents.teaching_agent import tutor, generate_quiz, generate_mcq_quiz, regenerate_mcq_options, reteach, reteach_knowledge_gap, evaluate_comp_check
from agents.grading_agent import grade as grade_quiz
from context_bus import bus

init_db()
seed_users()

MAX_Q = 10  # must match the maximum quiz questions the professor can configure


# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');

:root {
    --coral:    #E07340;
    --coral-h:  #C85F2C;
    --success:  #4DB880;
    --warning:  #D08030;
    --bg:       #0F0F0F;
    --card:     #1A1A1A;
    --card2:    #222222;
    --text:     #F0EDE8;
    --text-sm:  #9A9590;
    --border:   #2E2E2E;
    --shadow:   0 2px 6px rgba(0,0,0,0.6), 0 1px 2px rgba(0,0,0,0.5);
}

body, .gradio-container {
    background: var(--bg) !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text) !important;
}
footer { display: none !important; }

/* Login */
#login-view { background: transparent !important; border: none !important; box-shadow: none !important; padding: 64px 16px !important; }
#login-card {
    background: var(--card);
    border-radius: 12px;
    padding: 48px 44px 40px;
    box-shadow: var(--shadow);
    border: 1px solid var(--border);
}
#login-card label { color: var(--text-sm) !important; }

/* Topbar */
.topbar {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 24px;
    color: var(--text);
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: var(--shadow);
}
.topbar .t-brand {
    font-family: 'Source Serif 4', serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
}
.topbar .t-role  { font-size: 0.85rem; color: var(--text-sm); }
.topbar .t-user  { margin-left: auto; font-size: 0.82rem; color: var(--text-sm); }

/* KPI stat cards */
.stat-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }
.stat-card {
    flex: 1; min-width: 120px; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 20px 16px; text-align: center;
    box-shadow: var(--shadow);
}
.stat-card .num {
    font-family: 'Source Serif 4', serif;
    font-size: 2rem; font-weight: 700;
    color: var(--coral); line-height: 1;
}
.stat-card .num.success { color: var(--success); }
.stat-card .num.warning { color: var(--warning); }
.stat-card .lbl {
    font-size: 0.72rem; color: var(--text-sm);
    margin-top: 6px; text-transform: uppercase;
    letter-spacing: 0.07em; font-weight: 500;
}

/* Section headings */
.sh {
    font-family: 'Source Serif 4', serif;
    font-size: 0.95rem; font-weight: 600; color: var(--text);
    border-left: 3px solid var(--coral); padding-left: 10px;
    margin: 4px 0 16px;
    letter-spacing: 0.01em;
}

/* Quiz question cards */
.quiz-q { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 4px; box-shadow: var(--shadow); }
.quiz-q-num  { font-size: 0.72rem; font-weight: 700; color: var(--coral); text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 5px; }
.quiz-q-text { font-size: 0.94rem; color: var(--text); line-height: 1.55; }

/* Result hero */
.result-hero {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text);
    text-align: center;
    padding: 36px 24px;
    margin-bottom: 20px;
    box-shadow: var(--shadow);
}
.result-hero .score     { font-family: 'Source Serif 4', serif; font-size: 3.6rem; font-weight: 700; line-height: 1; color: var(--coral); }
.result-hero .score sub { font-size: 1.6rem; opacity: 0.55; }
.result-hero .grade-lbl { font-size: 0.88rem; color: var(--text-sm); margin-top: 8px; }

/* Missed cards */
.missed-card { background: #1F1500; border: 1px solid #3A2800; border-left: 4px solid var(--warning); border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }
.missed-card .tag  { font-size: 0.72rem; font-weight: 700; color: var(--warning); text-transform: uppercase; letter-spacing: 0.07em; }
.missed-card .note { font-size: 0.89rem; color: var(--text-sm); margin-top: 4px; line-height: 1.5; }

.correct-line { color: var(--success); font-size: 0.89rem; margin: 0 0 14px; }
.login-err p  { color: #FF6B6B !important; font-size: 0.88rem !important; margin: 0 !important; }

/* Upload drop zone */
.upload-dz label { border: 2px dashed var(--border) !important; border-radius: 12px !important; background: var(--card2) !important; }

/* Tables — Inter, generous padding, no monospace */
table { font-family: 'Inter', sans-serif !important; }
.gr-dataframe table, table.svelte-1889pmt {
    font-family: 'Inter', sans-serif !important;
    border-collapse: collapse;
}
.gr-dataframe table thead th, table.svelte-1889pmt thead th {
    background: #222222 !important;
    color: var(--text-sm) !important;
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-weight: 600 !important;
    padding: 12px 10px !important;
    border-bottom: 1px solid var(--border) !important;
    font-family: 'Inter', sans-serif !important;
}
.gr-dataframe table tbody td, table.svelte-1889pmt tbody td {
    border-bottom: 1px solid var(--border) !important;
    font-family: 'Inter', sans-serif !important;
    padding: 12px 10px !important;
    font-size: 0.88rem !important;
    color: var(--text) !important;
    background: var(--card) !important;
}
.gr-dataframe table tbody tr:hover td, table.svelte-1889pmt tbody tr:hover td {
    background: #252525 !important;
}

/* Tabs — minimal underline style */
.tabs > .tab-nav {
    border-bottom: 1px solid var(--border) !important;
    background: transparent !important;
    padding: 0 !important;
}
.tabs > .tab-nav > button {
    background: transparent !important;
    color: var(--text-sm) !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    font-weight: 500 !important;
    padding: 10px 16px !important;
    margin: 0 !important;
    font-family: 'Inter', sans-serif !important;
}
.tabs > .tab-nav > button.selected {
    color: var(--coral) !important;
    border-bottom-color: var(--coral) !important;
}

/* Inputs & textareas */
input, textarea, select {
    background: var(--card2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text) !important;
}
input:focus, textarea:focus {
    border-color: var(--coral) !important;
    box-shadow: 0 0 0 2px rgba(224,115,64,0.2) !important;
    outline: none !important;
}
label { color: var(--text-sm) !important; }

/* Primary buttons */
button.primary, .gr-button-primary {
    background: var(--coral) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
}
button.primary:hover, .gr-button-primary:hover {
    background: var(--coral-h) !important;
}

/* Secondary buttons */
button.secondary, .gr-button-secondary {
    background: var(--card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
}
button.secondary:hover, .gr-button-secondary:hover {
    background: var(--card2) !important;
}

/* Accordion / Group panels */
.gr-group, .gr-accordion {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

/* Chatbot bubbles */
.message.bot { background: var(--card2) !important; color: var(--text) !important; border: 1px solid var(--border) !important; }
.message.user { background: var(--coral) !important; color: #fff !important; }

/* MCQ quiz radio buttons — each option is a styled pill */
.quiz-mcq-radio .wrap { gap: 8px !important; }
.quiz-mcq-radio label {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    padding: 10px 16px !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    background: var(--card2) !important;
    color: var(--text) !important;
    cursor: pointer !important;
    transition: background 0.15s, border-color 0.15s, color 0.15s !important;
    margin-bottom: 4px !important;
    font-size: 0.92rem !important;
}
.quiz-mcq-radio label:hover {
    border-color: var(--coral) !important;
    background: rgba(224,115,64,0.08) !important;
}
/* selected state — Gradio adds .selected class to the checked label */
.quiz-mcq-radio label.selected {
    background: rgba(224,115,64,0.22) !important;
    border-color: var(--coral) !important;
    color: var(--coral) !important;
    font-weight: 600 !important;
}
/* also cover browsers that support :has() */
.quiz-mcq-radio label:has(input[type='radio']:checked) {
    background: rgba(224,115,64,0.22) !important;
    border-color: var(--coral) !important;
    color: var(--coral) !important;
    font-weight: 600 !important;
}
/* hide the native radio circle — the label itself is the indicator */
.quiz-mcq-radio input[type='radio'] { display: none !important; }
"""


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _topbar(role_label: str, display_name: str = "") -> str:
    user_span = f'<span class="t-user">&#128100; {display_name}</span>' if display_name else ""
    return (
        f'<div class="topbar">'
        f'<span class="t-brand">'
        f'<span style="width:8px;height:8px;background:#E07340;border-radius:50%;display:inline-block;flex-shrink:0;"></span>'
        f'Academic AI'
        f'</span>'
        f'<span class="t-role">/ {role_label}</span>'
        f'{user_span}'
        f'</div>'
    )


def _stat_cards_html(rows: list) -> str:
    total = len(rows)
    at_risk = sum(1 for r in rows if "At Risk" in str(r[4]))
    avg_scores = [r[2] for r in rows if isinstance(r[2], (int, float))]
    class_avg = round(sum(avg_scores) / len(avg_scores), 1) if avg_scores else "—"
    quiz_max = max((r[1] for r in rows if isinstance(r[1], int)), default=0)
    attn_cls = ' warning' if at_risk > 0 else ' success'
    return (
        f'<div class="stat-row">'
        f'<div class="stat-card"><div class="num">{total}</div><div class="lbl">Total Students</div></div>'
        f'<div class="stat-card"><div class="num">{class_avg}</div><div class="lbl">Class Average</div></div>'
        f'<div class="stat-card"><div class="num{attn_cls}">{at_risk}</div><div class="lbl">Need Attention</div></div>'
        f'<div class="stat-card"><div class="num">{quiz_max}</div><div class="lbl">Max Quizzes Taken</div></div>'
        f'</div>'
    )


_EMPTY_STAT_CARDS = (
    '<div class="stat-row">'
    '<div class="stat-card"><div class="num">—</div><div class="lbl">Total Students</div></div>'
    '<div class="stat-card"><div class="num">—</div><div class="lbl">Class Average</div></div>'
    '<div class="stat-card"><div class="num">—</div><div class="lbl">Need Attention</div></div>'
    '<div class="stat-card"><div class="num">—</div><div class="lbl">Max Quizzes Taken</div></div>'
    '</div>'
)


def _question_html(idx: int, q: dict) -> str:
    options = q.get("options", {})
    opts_html = ""
    if options:
        opts_html = "".join(
            f'<div style="padding:3px 0;font-size:0.88rem;">'
            f'<span style="color:#E07340;font-weight:700;">{k}.</span> '
            f'<span style="color:#F0EDE8;">{v}</span></div>'
            for k, v in sorted(options.items())
        )
        opts_html = f'<div style="margin-top:10px;padding-left:4px;">{opts_html}</div>'
    return (
        f'<div class="quiz-q">'
        f'<div class="quiz-q-num">Question {idx + 1}</div>'
        f'<div class="quiz-q-text">{q["question"]}</div>'
        f'{opts_html}'
        f'</div>'
    )


def _results_html(grading: dict) -> str:
    score = grading.get("final_score", 0)
    results = grading.get("results", [])

    correct = [r for r in results if r.get("score", 0) >= 1]
    missed  = [r for r in results if r.get("score", 0) < 1]

    correct_html = ""
    if correct:
        nums = ", ".join(f"Q{r['id']}" for r in correct)
        correct_html = f'<p class="correct-line">✓ {nums} answered correctly.</p>'

    missed_html = ""
    for r in missed:
        s = r.get("score", 0)
        label = "Partial" if s == 0.5 else "Incorrect"
        missed_html += (
            f'<div class="missed-card">'
            f'<div class="tag">Q{r["id"]} · {r.get("concept", "")} · {label}</div>'
            f'<div class="note">{r.get("feedback", "")}</div>'
            f'</div>'
        )

    grade_label = (
        "Excellent! 🎉" if score >= 8.5 else
        "Good effort!" if score >= 6 else
        "Keep practising — you'll get there!"
    )
    return (
        f'<div class="result-hero">'
        f'<div class="score">{score}<sub>/10</sub></div>'
        f'<div class="grade-lbl">{grade_label}</div>'
        f'</div>'
        f'<div class="sh">Review</div>'
        f'{correct_html}'
        f'{missed_html}'
    )


def _reteach_html(items: list) -> str:
    if not items:
        return ""
    parts = ['<div class="sh" style="margin-top:24px;">Personalised Feedback</div>']
    for item in items:
        concept  = item.get("concept", "")
        t        = item.get("type", "")
        expl     = item.get("explanation", "")
        if t == "careless":
            parts.append(
                f'<div style="background:#0F1A14;border:1px solid #1A3026;border-left:4px solid #4DB880;'
                f'border-radius:10px;padding:14px 16px;margin-bottom:10px;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#4DB880;text-transform:uppercase;letter-spacing:0.07em;">'
                f'{concept} — minor slip</div>'
                f'<div style="font-size:0.88rem;color:#9A9590;margin-top:4px;">'
                f'You likely know this material — just a small slip. Revisit it briefly before the next quiz.</div>'
                f'</div>'
            )
        else:
            icon  = "📖" if t == "knowledge_gap" else "🔄"
            label = "Background material" if t == "knowledge_gap" else "Re-explanation"
            parts.append(
                f'<div style="background:#1E1200;border:1px solid #3A2800;border-left:4px solid #E07340;'
                f'border-radius:10px;padding:14px 16px;margin-bottom:10px;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#E07340;text-transform:uppercase;letter-spacing:0.07em;">'
                f'{icon} {concept} — {label}</div>'
                f'<div style="font-size:0.88rem;color:#F0EDE8;margin-top:6px;line-height:1.6;">{expl}</div>'
                f'</div>'
            )
    return "".join(parts)


def _comp_check_html(question: str) -> str:
    return (
        f'<div style="background:#1E1200;border:1px solid #3A2800;border-left:4px solid #E07340;'
        f'border-radius:10px;padding:14px 16px;margin-top:16px;">'
        f'<div style="font-size:0.72rem;font-weight:700;color:#E07340;text-transform:uppercase;letter-spacing:0.07em;">'
        f'✏ Comprehension check</div>'
        f'<div style="font-size:0.94rem;color:#F0EDE8;margin-top:6px;">{question}</div>'
        f'</div>'
    )


def _pdf_sidebar_html(resources: list) -> str:
    n = len(resources)
    header = f'<div class="sh">Uploaded materials ({n})</div>'
    if not resources:
        return header + '<p style="color:#9A9590;font-size:0.85rem;">No PDFs uploaded yet.</p>'
    lines = "".join(
        f'<div style="display:flex;gap:8px;padding:8px 0;border-bottom:1px solid #2E2E2E;">'
        f'<span style="background:#2A2A2A;color:#E07340;border-radius:6px;'
        f'padding:2px 7px;font-size:0.75rem;font-weight:600;white-space:nowrap;border:1px solid #2E2E2E;">W{week}</span>'
        f'<span style="font-size:0.84rem;color:#F0EDE8;word-break:break-all;">{fn}</span>'
        f'</div>'
        for week, fn in resources
    )
    return header + lines


def _review_detail_html(attempt: dict) -> str:
    payload = attempt.get("results", {})
    items   = payload.get("results", []) if isinstance(payload, dict) else []
    if not items:
        return '<p style="color:#9A9590;">No per-question data available for this attempt.</p>'

    state = attempt.get("approval_state", "pending")
    if state == "approved":
        banner = (
            f'<p style="color:#4DB880;font-weight:600;margin-bottom:10px;">'
            f'✓ Approved — professor score: {attempt.get("approved_score")}/10</p>'
        )
    else:
        banner = '<p style="color:#D08030;font-weight:600;margin-bottom:10px;">⏳ Pending review</p>'

    rows = ""
    for r in items:
        q_num = r.get("id", "?")
        q_text = r.get("question_text") or r.get("question", "—")
        exp    = r.get("expected_answer", "—")
        stu    = r.get("student_answer",  "—")
        ai_sc  = r.get("score", "?")
        cls    = r.get("miss_type") or ("correct" if float(r.get("score", 0)) >= 1 else "—")
        td = 'style="padding:10px 12px;border-bottom:1px solid #2E2E2E;vertical-align:top;font-family:Inter,sans-serif;font-size:0.85rem;color:#F0EDE8;background:#1A1A1A;"'
        rows += (
            f'<tr>'
            f'<td {td}>Q{q_num}</td>'
            f'<td {td}>{q_text}</td>'
            f'<td {td}>{exp}</td>'
            f'<td {td}>{stu}</td>'
            f'<td {td} style="text-align:center;padding:10px 12px;border-bottom:1px solid #2E2E2E;font-family:Inter,sans-serif;font-size:0.85rem;color:#F0EDE8;background:#1A1A1A;">{ai_sc}</td>'
            f'<td {td}>{cls}</td>'
            f'</tr>'
        )
    th = 'style="padding:10px 12px;border-bottom:1px solid #2E2E2E;text-align:left;background:#222222;color:#9A9590;font-size:0.78rem;text-transform:uppercase;font-family:Inter,sans-serif;font-weight:600;"'
    table = (
        f'<table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;">'
        f'<thead><tr>'
        f'<th {th}>#</th>'
        f'<th {th}>Question</th>'
        f'<th {th}>Expected Answer</th>'
        f'<th {th}>Student Answer</th>'
        f'<th {th}>AI Score</th>'
        f'<th {th}>Classification</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )
    return banner + table


def _final_grades_html(grades: list) -> str:
    if not grades:
        return '<p style="color:#9A9590;font-size:0.9rem;">No quiz attempts yet.</p>'
    rows = ""
    for g in grades:
        td_base = 'style="padding:10px 12px;border-bottom:1px solid #2E2E2E;color:#F0EDE8;background:#1A1A1A;font-family:Inter,sans-serif;font-size:0.88rem;"'
        if g["approval_state"] == "approved":
            score_cell = (
                f'<td {td_base}>'
                f'<span style="color:#4DB880;font-weight:600;">'
                f'{g["approved_score"]}/10 ✓</span></td>'
            )
        else:
            score_cell = (
                f'<td {td_base}>'
                f'<span style="color:#D08030;">Pending review</span></td>'
            )
        rows += (
            f'<tr>'
            f'<td {td_base}>Week {g["week"]}</td>'
            f'{score_cell}'
            f'<td {td_base} style="padding:10px 12px;border-bottom:1px solid #2E2E2E;color:#9A9590;font-size:0.85rem;background:#1A1A1A;">'
            f'{g["created_at"][:10]}</td>'
            f'</tr>'
        )
    th = 'style="padding:10px 12px;border-bottom:1px solid #2E2E2E;text-align:left;background:#222222;color:#9A9590;font-size:0.78rem;text-transform:uppercase;font-family:Inter,sans-serif;font-weight:600;"'
    return (
        f'<div class="sh">Your Grades</div>'
        f'<table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;">'
        f'<thead><tr>'
        f'<th {th}>Week</th>'
        f'<th {th}>Grade</th>'
        f'<th {th}>Date</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
    )


def _kb_detail_html(kb: dict) -> str:
    concepts = kb.get("key_concepts", [])
    concepts_html = "".join(
        f'<li style="font-size:0.88rem;margin-bottom:4px;">{c}</li>'
        for c in concepts
    ) if concepts else '<li style="color:#9A9590;">None extracted.</li>'
    return (
        f'<div class="sh">Week {kb["week"]} — Knowledge Base</div>'
        f'<div style="margin-bottom:14px;font-size:0.9rem;line-height:1.65;color:#F0EDE8;">'
        f'{kb.get("summary", "No summary available.")}</div>'
        f'<div class="sh">Key Concepts</div>'
        f'<ul style="padding-left:18px;margin:0;">{concepts_html}</ul>'
    )


def _tutor_context_html(week: int) -> str:
    kb = get_knowledge(week)
    if kb:
        concepts = kb.get("key_concepts", [])
        preview  = ", ".join(concepts[:3])
        if len(concepts) > 3:
            preview += "…"
        detail = f"Topics: {preview}" if preview else "Material loaded"
        return (
            f'<div style="display:flex;align-items:center;gap:10px;'
            f'background:#1E1E1E;border:1px solid #2E2E2E;border-radius:8px;'
            f'padding:8px 14px;margin-bottom:4px;flex-wrap:wrap;">'
            f'<span style="font-size:0.72rem;font-weight:600;color:#fff;'
            f'background:#E07340;border-radius:4px;padding:2px 8px;white-space:nowrap;">'
            f'Week {week}</span>'
            f'<span style="font-size:0.84rem;color:#F0EDE8;">{detail}</span>'
            f'</div>'
        )
    return (
        f'<div style="background:#1A1A1A;border:1px solid #2E2E2E;border-radius:8px;'
        f'padding:8px 14px;margin-bottom:4px;font-size:0.84rem;color:#9A9590;">'
        f'No week selected — go to <strong>Course Materials</strong> and set an active topic.'
        f'</div>'
    )


def _materials_list_choices() -> list:
    """Per-PDF entries for the student topic/materials dropdown, value = 'rid|week'."""
    return [(f"Week {week} — {fn}", f"{rid}|{week}") for rid, week, fn in get_resources_with_ids()]


def _settings_pdf_choices() -> list:
    """Per-PDF entries for the professor rubric-settings dropdown, value = resource_id string."""
    return [(f"Week {week} — {fn}", str(rid)) for rid, week, fn in get_resources_with_ids()]


def _delete_pdf_choices() -> list:
    """Per-PDF entries for the delete dropdown, keyed by resource row ID."""
    return [(f"Week {week} — {fn}", str(rid)) for rid, week, fn in get_resources_with_ids()]


# ── Dashboard helpers ─────────────────────────────────────────────────────────

def _get_dashboard_data():
    rows = get_dashboard_rows(ROLLING_WINDOW, AT_RISK_THRESHOLD)
    stat_html = _stat_cards_html(rows) if rows else _EMPTY_STAT_CARDS
    return stat_html, rows


# ── Session helpers ───────────────────────────────────────────────────────────

def _weeks_for_dropdown():
    weeks = get_available_weeks()
    return [str(w) for w in weeks], str(weeks[-1]) if weeks else None


def _login_updates(user: dict):
    """Build the 15-element output tuple for a successful login."""
    is_prof = user["role"] == "professor"
    name    = user["display_name"]

    if is_prof:
        stat_html, dash_rows = _get_dashboard_data()
        resources = get_resources_list()
        students  = get_students()
        pdf_html  = _pdf_sidebar_html(resources)
        student_choices = [(dn, uname) for uname, dn in students]
        final_html  = ""
        mat_choices = []
    else:
        stat_html, dash_rows = _EMPTY_STAT_CARDS, []
        latest = get_latest_week()
        if latest:
            bus.set_week(latest)
        pdf_html        = ""
        student_choices = []
        final_html  = _final_grades_html(get_approved_grades(user["username"]))
        mat_choices = _materials_list_choices()

    choices, default = _weeks_for_dropdown()
    return (
        user,                                               # 1  mem_session
        gr.update(visible=False),                           # 2  login_view
        gr.update(visible=is_prof),                         # 3  prof_view
        gr.update(visible=not is_prof),                     # 4  student_view
        gr.update(value=_topbar("Professor Dashboard", name)),  # 5 prof_topbar
        gr.update(value=_topbar("Student Portal", name)),   # 6  student_topbar
        gr.update(visible=False),                           # 7  login_err
        gr.update(value=stat_html),                         # 8  stat_cards
        gr.update(value=dash_rows),                         # 9  student_table
        gr.update(choices=choices, value=default),          # 10 week_selector
        gr.update(value=pdf_html),                          # 11 pdf_sidebar
        gr.update(choices=student_choices, value=None),     # 12 review_student_dd
        gr.update(value=final_html),                        # 13 final_grades_html
        gr.update(choices=mat_choices, value=None),         # 14 materials_dd
        user,                                               # 15 session (BrowserState — LAST)
    )


def _no_change(current_mem_sess, err_msg="", err_vis=False):
    return (
        current_mem_sess,                           # 1
        gr.update(), gr.update(), gr.update(),      # 2-4  views
        gr.update(), gr.update(),                   # 5-6  topbars
        gr.update(value=err_msg, visible=err_vis),  # 7    login_err
        gr.update(), gr.update(), gr.update(),      # 8-10 stat_cards, table, week
        gr.update(), gr.update(), gr.update(), gr.update(),  # 11-14 new components
        gr.update(),                                # 15   session (BrowserState)
    )


def do_login(username, password, current_mem_sess):
    if not username.strip():
        return _no_change(current_mem_sess, "Please enter your username.", True)
    if not password.strip():
        return _no_change(current_mem_sess, "Please enter your password.", True)
    user = verify_login(username, password)
    if user is None:
        return _no_change(current_mem_sess, "Incorrect username or password. Please try again.", True)
    return _login_updates(user)


def restore_session(session_data):
    """Called on page load; reads BrowserState and rebuilds the 13-output UI state."""
    if not session_data:
        return (
            None,                          # 1  mem_session
            gr.update(visible=True),       # 2  login_view
            gr.update(visible=False),      # 3  prof_view
            gr.update(visible=False),      # 4  student_view
            gr.update(), gr.update(),      # 5-6  topbars
            gr.update(), gr.update(), gr.update(),       # 7-9  stat_cards, table, week
            gr.update(), gr.update(), gr.update(), gr.update(),  # 10-13 new components
            gr.update(),                   # 14  tutor_week_bar
            gr.update(),                   # 15  settings_pdf_dd
            gr.update(),                   # 16  delete_week_dd
        )

    is_prof = session_data["role"] == "professor"
    name    = session_data["display_name"]

    if is_prof:
        stat_html, dash_rows = _get_dashboard_data()
        resources = get_resources_list()
        students  = get_students()
        pdf_html  = _pdf_sidebar_html(resources)
        student_choices = [(dn, uname) for uname, dn in students]
        final_html      = ""
        mat_choices     = []
        latest_week     = None
        settings_ch     = _settings_pdf_choices()
        delete_ch       = _delete_pdf_choices()
    else:
        stat_html, dash_rows = _EMPTY_STAT_CARDS, []
        latest = get_latest_week()
        if latest:
            bus.set_week(latest)
        pdf_html        = ""
        student_choices = []
        final_html  = _final_grades_html(get_approved_grades(session_data["username"]))
        mat_choices = _materials_list_choices()
        latest_week = latest
        settings_ch = []
        delete_ch   = []

    choices, default = _weeks_for_dropdown()
    return (
        session_data,                                           # 1  mem_session
        gr.update(visible=False),                               # 2  login_view
        gr.update(visible=is_prof),                             # 3  prof_view
        gr.update(visible=not is_prof),                         # 4  student_view
        gr.update(value=_topbar("Professor Dashboard", name)),  # 5  prof_topbar
        gr.update(value=_topbar("Student Portal", name)),       # 6  student_topbar
        gr.update(value=stat_html),                             # 7  stat_cards
        gr.update(value=dash_rows),                             # 8  student_table
        gr.update(choices=choices, value=default),              # 9  week_selector
        gr.update(value=pdf_html),                              # 10 pdf_sidebar
        gr.update(choices=student_choices, value=None),         # 11 review_student_dd
        gr.update(value=final_html),                            # 12 final_grades_html
        gr.update(choices=mat_choices, value=None),             # 13 materials_dd
        gr.update(value=_tutor_context_html(latest_week or 1)), # 14 tutor_week_bar
        gr.update(choices=settings_ch, value=None),             # 15 settings_pdf_dd
        gr.update(choices=delete_ch,   value=None),             # 16 delete_week_dd
    )


def do_logout():
    return None, None, gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)


# ── Professor handlers ────────────────────────────────────────────────────────

def handle_upload(file, week_num):
    if file is None:
        return gr.update(value="⚠ Please choose a PDF file first.", visible=True), gr.update(), gr.update(), gr.update()
    try:
        raw_text = extract_text_from_pdf(file.name)
        week  = int(week_num)
        num_q = 4
        qtype = "open"
        resource_id = save_resource(week, os.path.basename(file.name), raw_text)
        result = ingest(week, raw_text)
        n = len(result.get("key_concepts", []))
        rubric_text_clean = ""
        save_rubric(resource_id, rubric_text_clean, num_q, qtype)
        type_label  = "MCQ" if qtype == "mcq" else "Open Answer"
        rubric_note = (
            f" Rubric saved — {num_q} {type_label} questions per quiz."
            if rubric_text_clean
            else f" Quiz: {num_q} {type_label} questions."
        )
        return (
            gr.update(
                value=f"✓ Week {week} ingested — {n} key concepts extracted.{rubric_note}",
                visible=True,
            ),
            gr.update(value=_pdf_sidebar_html(get_resources_list())),
            gr.update(choices=_settings_pdf_choices()),
            gr.update(choices=_delete_pdf_choices()),
        )
    except Exception as e:
        return gr.update(value=f"⚠ Upload failed: {e}", visible=True), gr.update(), gr.update(), gr.update()


def refresh_dashboard():
    stat_html, rows = _get_dashboard_data()
    return gr.update(value=stat_html), gr.update(value=rows)


def handle_export():
    rows = get_dashboard_rows(ROLLING_WINDOW, AT_RISK_THRESHOLD)
    if not rows:
        return gr.update(value="No student data to export yet.", visible=True), gr.update(visible=False)
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Class Report"
        headers = ["Student", "Quizzes Taken", "Avg Score (/10)", "Weak Topics", "Status"]
        ws.append(headers)
        bold = openpyxl.styles.Font(bold=True)
        for cell in ws[1]:
            cell.font = bold
        for row in rows:
            ws.append(list(row))
        for col, width in [("A", 22), ("D", 34), ("E", 14)]:
            ws.column_dimensions[col].width = width
        path = os.path.join(
            tempfile.gettempdir(),
            f"class_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
        )
        wb.save(path)
        return (
            gr.update(value="✓ Export ready — download the file below.", visible=True),
            gr.update(value=path, visible=True),
        )
    except Exception as e:
        return gr.update(value=f"⚠ Export failed: {e}", visible=True), gr.update(visible=False)


def on_review_student(student_username):
    if not student_username:
        return gr.update(choices=[], value=None), gr.update(value="")
    attempts = get_attempts_for_student(student_username)
    total = len(attempts)
    choices = [
        (
            f"Attempt {total - i} — Week {a['week']} — {a['filename'] or 'unknown'} | {a['created_at'][:10]} | AI: {a['ai_score']}/10"
            + (" ✓" if a["approval_state"] == "approved" else " ⏳"),
            str(a["id"]),
        )
        for i, a in enumerate(attempts)
    ]
    return gr.update(choices=choices, value=None), gr.update(value="")


def on_review_attempt(attempt_id_str):
    if not attempt_id_str:
        return gr.update(value=""), gr.update(value=None)
    try:
        attempt = get_attempt_by_id(int(attempt_id_str))
    except (ValueError, TypeError):
        return gr.update(value=""), gr.update(value=None)
    if not attempt:
        return gr.update(value="<p>Attempt not found.</p>"), gr.update(value=None)

    # Backfill question_text / expected_answer for attempts saved before the
    # grading-agent enrichment step was added (student_answer is unrecoverable).
    payload = attempt.get("results", {})
    items = payload.get("results", []) if isinstance(payload, dict) else []
    if items and not items[0].get("question_text"):
        quiz_qs = get_quiz_questions(attempt["quiz_id"])
        id_to_q = {q["id"]: q for q in quiz_qs}
        for r in items:
            src = id_to_q.get(r.get("id"), {})
            r["question_text"]   = src.get("question", "")
            r["expected_answer"] = src.get("expected_answer", "")

    default_score = (
        attempt["approved_score"] if attempt["approved_score"] is not None
        else attempt["ai_score"]
    )
    return gr.update(value=_review_detail_html(attempt)), gr.update(value=default_score)


def handle_approve(attempt_id_str, override_score):
    if not attempt_id_str:
        return (
            gr.update(value="⚠ Select an attempt first.", visible=True),
            gr.update(), gr.update(), gr.update(),
        )
    if override_score is None:
        return (
            gr.update(value="⚠ Enter a score between 0 and 10.", visible=True),
            gr.update(), gr.update(), gr.update(),
        )
    try:
        db_approve_attempt(int(attempt_id_str), float(override_score))
        attempt   = get_attempt_by_id(int(attempt_id_str))
        detail    = _review_detail_html(attempt) if attempt else ""
        stat_html, rows = _get_dashboard_data()
        return (
            gr.update(value=f"✓ Approved — score: {override_score}/10.", visible=True),
            gr.update(value=stat_html),
            gr.update(value=rows),
            gr.update(value=detail),
        )
    except Exception as e:
        return (
            gr.update(value=f"⚠ Approval failed: {e}", visible=True),
            gr.update(), gr.update(), gr.update(),
        )


# ── Student handlers ──────────────────────────────────────────────────────────

def _quiz_reset_updates():
    return (
        gr.update(visible=False),                                        # quiz_panel
        *[gr.update(value="", visible=False) for _ in range(MAX_Q)],    # quiz_q_html
        None,                                                            # quiz_state
        gr.update(visible=False),                                        # quiz_status
        gr.update(visible=False),                                        # result_area
        gr.update(visible=False),                                        # feedback_area
        gr.update(value="", visible=False),                              # comp_check_html
        gr.update(visible=False),                                        # comp_check_in
        gr.update(visible=False),                                        # comp_check_btn
        gr.update(visible=False),                                        # comp_check_result
        None,                                                            # feedback_state
        *[gr.update(visible=False, value="") for _ in range(MAX_Q)],    # quiz_answers
        *[gr.update(visible=False, value=None) for _ in range(MAX_Q)],  # quiz_radio
    )


def set_student_week(week_str):
    if not week_str:
        return gr.update(visible=False), gr.update(), *_quiz_reset_updates()
    try:
        bus.set_week(int(week_str))
        return (
            gr.update(value=f"Now studying **Week {week_str}** material.", visible=True),
            gr.update(value=_tutor_context_html(int(week_str))),
            *_quiz_reset_updates(),
        )
    except Exception:
        return gr.update(visible=False), gr.update(), *_quiz_reset_updates()


def handle_chat(message, history):
    if not message.strip():
        return history, ""
    try:
        reply = tutor(message)
    except Exception as e:
        reply = f"Sorry, something went wrong: {e}"
    return history + [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": reply},
    ], ""


def refresh_grades(mem_sess):
    username = (mem_sess or {}).get("username", "")
    if not username:
        return gr.update(value='<p style="color:#9A9590;">Please sign in.</p>')
    return gr.update(value=_final_grades_html(get_approved_grades(username)))


def on_material_select(value):
    if not value:
        return gr.update(value="")
    try:
        week = int(str(value).split("|")[1])
        kb = get_knowledge(week)
        if not kb:
            return gr.update(
                value=f'<p style="color:#9A9590;">No knowledge-base entry for Week {week} yet.</p>'
            )
        return gr.update(value=_kb_detail_html(kb))
    except Exception as e:
        return gr.update(value=f'<p style="color:#C0392B;">Error: {e}</p>')


def handle_set_topic(value):
    if not value:
        return gr.update(), gr.update(value="⚠ Select a material first.", visible=True), gr.update()
    try:
        parts = str(value).split("|")
        rid  = int(parts[0])
        week = int(parts[1])
        bus.set_resource(rid, week)
        choices, _ = _weeks_for_dropdown()
        return (
            gr.update(choices=choices, value=str(week)),
            gr.update(value=f"✓ Active topic set to **Week {week}**.", visible=True),
            gr.update(value=_tutor_context_html(week)),
        )
    except Exception as e:
        return gr.update(), gr.update(value=f"⚠ {e}", visible=True), gr.update()


# ── Quiz helpers ──────────────────────────────────────────────────────────────

def handle_delete_week(value):
    """Delete a single uploaded PDF by resource ID and refresh dropdowns + sidebar."""
    if not value:
        return (
            gr.update(value="⚠ Select a PDF to remove first.", visible=True),
            gr.update(), gr.update(), gr.update(),
        )
    try:
        resource_id = int(value)
        # get the filename for the confirmation message before deleting
        resources = get_resources_with_ids()
        label = next((fn for rid, wk, fn in resources if rid == resource_id), f"resource {resource_id}")
        delete_resource(resource_id)
        return (
            gr.update(value=f"✓ {label} removed.", visible=True),
            gr.update(value=_pdf_sidebar_html(get_resources_list())),
            gr.update(choices=_settings_pdf_choices(), value=None),
            gr.update(choices=_delete_pdf_choices(), value=None),
        )
    except Exception as e:
        return gr.update(value=f"⚠ {e}", visible=True), gr.update(), gr.update(), gr.update()


def on_settings_pdf_select(value):
    """Pre-fill rubric settings and populate topic dropdown when professor picks a PDF."""
    _empty_topic = gr.update(choices=[], value=None)
    if not value:
        return gr.update(value=""), gr.update(value=4), gr.update(value="Open Answer"), _empty_topic
    try:
        resource_id = int(value)
        s    = get_rubric_settings_by_resource(resource_id)
        week = get_resource_week(resource_id)
        kb   = get_knowledge(week) if week else None
        topics = kb["key_concepts"] if kb else []
        topic_update = gr.update(choices=topics, value=topics[0] if topics else None)
        if not s:
            return gr.update(value=""), gr.update(value=4), gr.update(value="Open Answer"), topic_update
        qtype_label = "Multiple Choice" if s["quiz_type"] == "mcq" else "Open Answer"
        return (
            gr.update(value=s["rubric_text"]),
            gr.update(value=s["num_questions"]),
            gr.update(value=qtype_label),
            topic_update,
        )
    except Exception:
        return gr.update(value=""), gr.update(value=4), gr.update(value="Open Answer"), gr.update(choices=[], value=None)


def handle_save_settings(selected_pdf, rubric_text, num_q, quiz_type_choice):
    """Save rubric settings for a specific uploaded PDF."""
    if not selected_pdf:
        return gr.update(value="⚠ Select a PDF first.", visible=True)
    try:
        resource_id = int(selected_pdf)
        num_q = max(1, min(10, int(num_q or 4)))
        qtype = "mcq" if "Multiple" in (quiz_type_choice or "") else "open"
        save_rubric(resource_id, (rubric_text or "").strip(), num_q, qtype)
        type_label = "MCQ" if qtype == "mcq" else "Open Answer"
        return gr.update(
            value=f"✓ Settings saved — {num_q} {type_label} questions.",
            visible=True,
        )
    except Exception as e:
        return gr.update(value=f"⚠ {e}", visible=True)


def handle_generate_questions(selected_pdf, topic, num_q, quiz_type_choice):
    """Generate quiz questions for the chosen topic so the professor can preview and edit them."""
    _err = lambda msg: (
        gr.update(value=msg, visible=True),
        *[gr.update(visible=False, value="") for _ in range(MAX_Q)],
        gr.update(visible=False),
        None,
    )
    if not selected_pdf:
        return _err("⚠ Select a PDF first.")
    if not topic:
        return _err("⚠ Pick a topic first.")
    try:
        resource_id = int(selected_pdf)
        week = get_resource_week(resource_id) or bus.current_week
        bus.set_week(week)
        num_q = max(1, min(10, int(num_q or 4)))
        qtype = "mcq" if "Multiple" in (quiz_type_choice or "") else "open"
        if qtype == "mcq":
            _, questions = generate_mcq_quiz(num_questions=num_q, weak_topics=[topic])
        else:
            _, questions = generate_quiz(num_questions=num_q, weak_topics=[topic])
        box_updates = [
            gr.update(value=questions[i]["question"], visible=True) if i < len(questions)
            else gr.update(value="", visible=False)
            for i in range(MAX_Q)
        ]
        return (
            gr.update(value=f"✓ {len(questions)} questions generated — edit below, then click Confirm.", visible=True),
            *box_updates,
            gr.update(visible=True),
            {"questions": questions, "qtype": qtype},
        )
    except Exception as e:
        return _err(f"⚠ {e}")


def handle_confirm_quiz(selected_pdf, topic, quiz_type_choice, quiz_gen_state, *edited_texts):
    """Persist the (possibly edited) questions as the confirmed quiz for this PDF."""
    if not selected_pdf:
        return gr.update(value="⚠ Select a PDF first.", visible=True)
    if not quiz_gen_state:
        return gr.update(value="⚠ Generate questions first.", visible=True)
    try:
        resource_id = int(selected_pdf)
        week        = get_resource_week(resource_id) or bus.current_week
        questions   = quiz_gen_state["questions"]
        qtype       = "mcq" if "Multiple" in (quiz_type_choice or "") else "open"
        for i, q in enumerate(questions):
            edited = (list(edited_texts)[i] if i < len(edited_texts) else "").strip()
            if edited:
                q["question"] = edited
        if qtype == "mcq":
            bus.set_week(week)
            questions = regenerate_mcq_options(questions)
        save_confirmed_quiz(resource_id, week, topic or "", questions, qtype)
        return gr.update(
            value=f"✓ Quiz confirmed — {len(questions)} questions saved. Students can now take it.",
            visible=True,
        )
    except Exception as e:
        return gr.update(value=f"⚠ {e}", visible=True)


def _grade_mcq(questions, student_choices, quiz_id, student_username):
    results = []
    for q in questions:
        selected   = (student_choices.get(q["id"]) or "").strip().upper()
        correct    = (q.get("correct") or "").strip().upper()
        is_correct = bool(selected) and selected == correct
        opts       = q.get("options", {})
        results.append({
            "id":              q["id"],
            "score":           1.0 if is_correct else 0.0,
            "question_text":   q.get("question", ""),
            "expected_answer": f'{correct}. {opts.get(correct, "")}',
            "student_answer":  f'{selected}. {opts.get(selected, "")}' if selected else "—",
            "miss_type":       None if is_correct else "knowledge_gap",
            "concept":         q.get("concept", ""),
            "feedback":        "Correct!" if is_correct else f"Correct answer: {correct}. {opts.get(correct, '')}",
            "routing":         "",
        })
    correct_count = sum(1 for r in results if r["score"] >= 1)
    final_score   = round(correct_count / len(questions) * 10, 1) if questions else 0
    payload       = {"final_score": final_score, "results": results}
    save_attempt(quiz_id, payload, final_score, student_username=student_username)
    return payload


def _take_quiz_error(msg):
    return (
        gr.update(visible=False),                                        # quiz_panel
        *[gr.update(value="", visible=False) for _ in range(MAX_Q)],    # quiz_q_html
        None,                                                            # quiz_state
        gr.update(value=msg, visible=True),                              # quiz_status
        gr.update(visible=False),                                        # result_area
        gr.update(visible=False),                                        # feedback_area
        gr.update(value="", visible=False),                              # comp_check_html
        gr.update(visible=False),                                        # comp_check_in
        gr.update(visible=False),                                        # comp_check_btn
        gr.update(visible=False),                                        # comp_check_result
        None,                                                            # feedback_state
        *[gr.update(visible=False, value="") for _ in range(MAX_Q)],    # quiz_answers
        *[gr.update(visible=False, value=None) for _ in range(MAX_Q)],  # quiz_radio
    )


def handle_take_quiz(mem_sess):
    confirmed = None
    if bus.current_resource_id:
        confirmed = get_confirmed_quiz_for_resource(bus.current_resource_id)
    if confirmed is None:
        confirmed = get_confirmed_quiz_for_week(bus.current_week)
    if confirmed is None:
        return _take_quiz_error("⚠ No quiz available yet for this week. Your professor hasn't published one.")

    quiz_id   = confirmed["quiz_id"]
    questions = confirmed["questions"]
    qtype     = confirmed["quiz_type"]

    n      = len(questions)
    is_mcq = qtype == "mcq"
    q_html_updates = [
        gr.update(value=_question_html(i, questions[i]) if i < n else "", visible=(i < n))
        for i in range(MAX_Q)
    ]
    ans_updates = [
        gr.update(visible=(i < n and not is_mcq), value="", label=f"Your answer — Question {i + 1}")
        for i in range(MAX_Q)
    ]
    radio_updates = [
        gr.update(visible=(i < n and is_mcq), value=None)
        for i in range(MAX_Q)
    ]
    return (
        gr.update(visible=True),                                              # quiz_panel
        *q_html_updates,                                                      # quiz_q_html
        {"quiz_id": quiz_id, "questions": questions, "quiz_type": qtype},    # quiz_state
        gr.update(visible=False),                                             # quiz_status
        gr.update(visible=False),                                             # result_area
        gr.update(visible=False),                                             # feedback_area
        gr.update(value="", visible=False),                                   # comp_check_html
        gr.update(visible=False),                                             # comp_check_in
        gr.update(visible=False),                                             # comp_check_btn
        gr.update(visible=False),                                             # comp_check_result
        None,                                                                 # feedback_state
        *ans_updates,                                                         # quiz_answers
        *radio_updates,                                                       # quiz_radio
    )


def _submit_error(msg):
    return (
        gr.update(value=msg, visible=True),
        gr.update(visible=False),
        gr.update(value="", visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        None,
    )


def handle_submit_quiz(quiz_state, mem_sess, *answers):
    if not quiz_state:
        return _submit_error("⚠ No quiz loaded. Click 'Take Quiz' first.")

    username  = (mem_sess or {}).get("username", "student")
    questions = quiz_state["questions"]
    quiz_id   = quiz_state["quiz_id"]
    week      = bus.current_week
    quiz_type = quiz_state.get("quiz_type", "open")

    text_answers  = list(answers[:MAX_Q])
    radio_answers = list(answers[MAX_Q:])

    # ── MCQ path: instant local grading, no LLM needed ────────────────────
    if quiz_type == "mcq":
        student_choices = {
            q["id"]: (radio_answers[i] if i < len(radio_answers) else "")
            for i, q in enumerate(questions)
        }
        try:
            grading = _grade_mcq(questions, student_choices, quiz_id, username)
        except Exception as e:
            return _submit_error(f"⚠ Grading failed: {e}")
        return (
            gr.update(value=_results_html(grading), visible=True),
            gr.update(visible=False),
            gr.update(value="", visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            None,
        )

    # ── Open-answer path: LLM grading ────────────────────────────────────
    student_answers = {q["id"]: (text_answers[i] if i < len(text_answers) else "") for i, q in enumerate(questions)}
    rubric = get_rubric(week)

    try:
        grading = grade_quiz(quiz_id, questions, student_answers, student_username=username, rubric=rubric)
    except Exception as e:
        return _submit_error(f"⚠ Grading failed: {e}")

    results_html = _results_html(grading)

    misses = [r for r in grading.get("results", []) if r.get("miss_type")]
    reteach_items = []
    first_check   = None

    for r in misses:
        concept  = r.get("concept", "")
        miss_t   = r.get("miss_type")
        orig_q   = next((q for q in questions if q["id"] == r["id"]), {})
        orig_ans = student_answers.get(r["id"], "")
        try:
            if miss_t == "conceptual":
                item = reteach(concept, orig_q.get("question", ""), orig_ans)
                reteach_items.append({"type": "conceptual", "concept": concept, **item})
                if first_check is None:
                    first_check = item["check_question"]
            elif miss_t == "knowledge_gap":
                item = reteach_knowledge_gap(concept)
                reteach_items.append({"type": "knowledge_gap", "concept": concept, **item})
                if first_check is None:
                    first_check = item["check_question"]
            elif miss_t == "careless":
                reteach_items.append({"type": "careless", "concept": concept})
        except Exception:
            pass

    fb_html   = _reteach_html(reteach_items)
    has_check = first_check is not None

    return (
        gr.update(value=results_html, visible=True),
        gr.update(value=fb_html, visible=bool(reteach_items)),
        gr.update(value=_comp_check_html(first_check) if has_check else "", visible=has_check),
        gr.update(visible=has_check, value=""),
        gr.update(visible=has_check),
        gr.update(visible=False),
        first_check,
    )


def handle_comp_check(answer, feedback_state):
    if not answer or not answer.strip():
        return gr.update(value="Please write your answer above first.", visible=True)
    check_q = feedback_state if isinstance(feedback_state, str) else ""
    if not check_q:
        return gr.update(visible=False)
    try:
        feedback = evaluate_comp_check(check_q, answer)
    except Exception as e:
        feedback = f"Could not evaluate answer: {e}"
    return gr.update(value=feedback, visible=True)


# ── Interface ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="Agentic AI for Academic Staff") as demo:

    # mem_session: in-memory state for immediate UI rendering.
    # session (BrowserState): persisted to localStorage for refresh survival.
    # BrowserState is always placed LAST in login outputs so UI updates fire
    # before the localStorage write, preventing the blank-page-on-sign-in bug.
    mem_session    = gr.State(None)
    session        = gr.BrowserState(None)
    quiz_state     = gr.State(None)
    feedback_state = gr.State(None)

    # ── Login ─────────────────────────────────────────────────────────────────
    with gr.Column(elem_id="login-view") as login_view:
        with gr.Row():
            gr.HTML("")
            with gr.Column(scale=2, min_width=400, elem_id="login-card"):
                gr.HTML("""
                  <div style="text-align:center;margin-bottom:28px;">
                    <span style="display:inline-block;width:10px;height:10px;background:#E07340;border-radius:50%;margin-bottom:16px;"></span>
                    <div style="font-family:'Source Serif 4',serif;font-size:1.65rem;font-weight:600;color:#F0EDE8;margin-bottom:6px;">Academic AI</div>
                    <div style="font-size:0.86rem;color:#9A9590;margin-top:4px;">
                      Agentic AI Platform for Academic Staff &amp; Students
                    </div>
                  </div>
                """)
                user_in   = gr.Textbox(label="Username", placeholder="e.g. hamza or abdin")
                pass_in   = gr.Textbox(label="Password", type="password", placeholder="••••••••")
                login_err = gr.Markdown(visible=False, elem_classes=["login-err"])
                login_btn = gr.Button("Sign In →", variant="primary", size="lg")
            gr.HTML("")

    # ── Professor View ────────────────────────────────────────────────────────
    with gr.Column(visible=False) as prof_view:
        with gr.Row(equal_height=True):
            prof_topbar = gr.HTML(_topbar("Professor Dashboard"), scale=8)
            prof_logout = gr.Button("Sign Out", size="sm", variant="secondary", scale=1)

        with gr.Tabs():

            with gr.Tab("📤  Upload Material"):
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        gr.HTML('<div class="sh">Upload Course Material</div>')
                        with gr.Row(equal_height=False):
                            with gr.Column():
                                upload_file  = gr.File(
                                    label="Course PDF",
                                    file_types=[".pdf"],
                                    elem_classes=["upload-dz"],
                                )
                                upload_week  = gr.Number(label="Week Number", value=1, precision=0, minimum=1, maximum=16)
                        upload_btn    = gr.Button("Upload & Ingest", variant="primary")
                        upload_status = gr.Markdown(visible=False)

                        with gr.Accordion("📋  Quiz Settings for Uploaded PDF", open=True):
                            gr.HTML('<div class="sh" style="margin-top:8px;">Select any uploaded PDF to view or update its rubric and quiz settings — no re-upload needed</div>')
                            settings_pdf_dd = gr.Dropdown(
                                label="Select PDF",
                                choices=[],
                                interactive=True,
                            )
                            settings_topic_dd = gr.Dropdown(
                                label="Quiz Topic",
                                choices=[],
                                interactive=True,
                            )
                            with gr.Row(equal_height=False):
                                with gr.Column():
                                    settings_rubric_in = gr.Textbox(
                                        label="Grading Rubric (optional)",
                                        placeholder="Marking criteria…",
                                        lines=5,
                                    )
                                with gr.Column():
                                    settings_num_in = gr.Number(
                                        label="Number of Quiz Questions",
                                        value=4,
                                        precision=0,
                                        minimum=1,
                                        maximum=10,
                                    )
                                    settings_type_in = gr.Radio(
                                        choices=["Open Answer", "Multiple Choice"],
                                        value="Open Answer",
                                        label="Quiz Type",
                                    )
                            settings_save_btn = gr.Button("Save Settings", variant="primary")
                            settings_status   = gr.Markdown(visible=False)

                            gr.HTML('<div class="sh" style="margin-top:20px;">Generate & Preview Questions</div>')
                            gen_questions_btn  = gr.Button("Generate Questions", variant="secondary")
                            gen_status         = gr.Markdown(visible=False)
                            gen_q_boxes = [
                                gr.Textbox(
                                    label=f"Question {i + 1}",
                                    visible=False,
                                    lines=2,
                                    interactive=True,
                                )
                                for i in range(MAX_Q)
                            ]
                            confirm_quiz_btn    = gr.Button("Confirm / Save Quiz", variant="primary", visible=False)
                            confirm_quiz_status = gr.Markdown(visible=False)
                            quiz_gen_state      = gr.State(None)

                    with gr.Column(scale=1):
                        pdf_sidebar = gr.HTML(_pdf_sidebar_html([]))
                        gr.HTML('<div class="sh" style="margin-top:20px;">Remove uploaded PDF</div>')
                        delete_week_dd = gr.Dropdown(
                            label="Select PDF to remove",
                            choices=[],
                            interactive=True,
                        )
                        delete_week_btn = gr.Button("✕  Remove PDF", variant="stop")
                        delete_status   = gr.Markdown(visible=False)

            with gr.Tab("📊  Class Dashboard"):
                stat_cards    = gr.HTML(_EMPTY_STAT_CARDS)
                gr.HTML('<div class="sh">Student Performance</div>')
                student_table = gr.Dataframe(
                    headers=["Student", "Quizzes Taken", "Avg Score (/10)", "Weak Topics", "Status"],
                    value=[],
                    interactive=False,
                    wrap=True,
                )
                with gr.Row():
                    refresh_btn   = gr.Button("🔄  Refresh", variant="secondary")
                    export_btn    = gr.Button("⬇  Export to Excel", variant="secondary")
                    export_status = gr.Markdown(visible=False, scale=5)
                export_file = gr.File(label="Download", visible=False, interactive=False)

                with gr.Accordion("🔍  Review & Approve Attempt", open=False):
                    gr.HTML('<div class="sh" style="margin-top:8px;">Select a student and attempt to review</div>')
                    with gr.Row():
                        review_student_dd = gr.Dropdown(
                            label="Student",
                            choices=[],
                            interactive=True,
                            scale=1,
                        )
                        review_attempt_dd = gr.Dropdown(
                            label="Attempt",
                            choices=[],
                            interactive=True,
                            scale=2,
                        )
                    review_detail_html = gr.HTML("")
                    with gr.Row():
                        review_score_in    = gr.Number(
                            label="Override Score (/10)",
                            value=None,
                            minimum=0,
                            maximum=10,
                            step=0.5,
                            scale=1,
                        )
                        review_approve_btn = gr.Button("✓  Approve", variant="primary", scale=1)
                    review_status = gr.Markdown(visible=False)

    # ── Student View ──────────────────────────────────────────────────────────
    with gr.Column(visible=False) as student_view:
        with gr.Row(equal_height=True):
            student_topbar = gr.HTML(_topbar("Student Portal"), scale=8)
            student_logout = gr.Button("Sign Out", size="sm", variant="secondary", scale=1)

        with gr.Row():
            week_selector = gr.Dropdown(
                label="Current week",
                choices=[],
                value=None,
                scale=2,
                min_width=160,
            )
            week_status = gr.Markdown(visible=False, scale=6)

        with gr.Tabs():

            with gr.Tab("💬  Tutor"):
                gr.HTML('<div class="sh">Ask the Teaching Agent</div>')
                tutor_week_bar = gr.HTML(_tutor_context_html(bus.current_week))
                chatbot = gr.Chatbot(
                    value=[{
                        "role": "assistant",
                        "content": (
                            "Hello! I'm your AI tutor, powered by the Teaching Agent.\n\n"
                            "Ask me anything about the current week's course material — "
                            "I can explain concepts, work through examples, and help you "
                            "prepare for quizzes. What would you like to explore?"
                        ),
                    }],
                    height=420,
                    show_label=False,
                    layout="bubble",
                )
                with gr.Row():
                    chat_in  = gr.Textbox(placeholder="Type your question and press Enter…", show_label=False, scale=9)
                    send_btn = gr.Button("Send", variant="primary", scale=1)

            with gr.Tab("📝  Official-Quizzes"):
                gr.HTML('<div class="sh">Weekly Quiz</div>')
                gr.Markdown(
                    "When you feel ready, click **Take Quiz** to receive this week's questions. "
                    "Write a complete answer for each one, then click **Submit**."
                )
                take_quiz_btn = gr.Button("Take Quiz", variant="primary", size="lg")
                quiz_status   = gr.Markdown(visible=False)

                with gr.Group(visible=False) as quiz_panel:
                    quiz_q_html  = []
                    quiz_answers = []
                    quiz_radio   = []
                    for _qi in range(MAX_Q):
                        quiz_q_html.append(gr.HTML("", visible=False))
                        quiz_answers.append(
                            gr.Textbox(
                                label=f"Your answer — Question {_qi + 1}",
                                lines=3,
                                placeholder="Write your answer here…",
                                visible=False,
                            )
                        )
                        quiz_radio.append(
                            gr.Radio(
                                choices=["A", "B", "C", "D"],
                                label=f"Your answer — Question {_qi + 1}",
                                visible=False,
                                value=None,
                                elem_classes=["quiz-mcq-radio"],
                            )
                        )
                    submit_btn = gr.Button("Submit Quiz", variant="primary")

                result_area   = gr.HTML(visible=False)
                feedback_area = gr.HTML(visible=False)

                comp_check_html   = gr.HTML(visible=False)
                comp_check_in     = gr.Textbox(
                    label="Your comprehension-check answer",
                    lines=2,
                    placeholder="Type your answer…",
                    visible=False,
                )
                comp_check_btn    = gr.Button("Submit Answer", variant="secondary", size="sm", visible=False)
                comp_check_result = gr.Markdown(visible=False)

            with gr.Tab("📋  Final Grades"):
                gr.Markdown(
                    "Grades shown here reflect your **professor-approved score**. "
                    "Attempts not yet reviewed show as *Pending review*."
                )
                with gr.Row():
                    grades_refresh_btn = gr.Button("🔄  Refresh", variant="secondary", scale=1)
                    gr.HTML("", scale=5)
                final_grades_html = gr.HTML('<p style="color:#9A9590;">Sign in to see your grades.</p>')

            with gr.Tab("📚  Course Materials"):
                gr.HTML('<div class="sh">Available Course Materials</div>')
                materials_dd = gr.Dropdown(
                    label="Select a PDF to preview its knowledge base",
                    choices=[],
                    interactive=True,
                )
                materials_detail = gr.HTML("")
                with gr.Row():
                    set_topic_btn = gr.Button("Set as Active Topic", variant="primary", scale=1)
                    topic_status  = gr.Markdown(visible=False, scale=4)

    # ── Wiring ────────────────────────────────────────────────────────────────

    # 15 outputs: mem_session first, BrowserState (session) last
    _LOGIN_OUTS = [
        mem_session, login_view, prof_view, student_view,
        prof_topbar, student_topbar, login_err,
        stat_cards, student_table, week_selector,
        pdf_sidebar, review_student_dd, final_grades_html, materials_dd,
        session,
    ]

    # Shared output list for session restore (used by demo.load AND post-login .then)
    _RESTORE_OUTS = [
        mem_session, login_view, prof_view, student_view,
        prof_topbar, student_topbar,
        stat_cards, student_table, week_selector,
        pdf_sidebar, review_student_dd, final_grades_html, materials_dd,
        tutor_week_bar, settings_pdf_dd, delete_week_dd,
    ]

    # After do_login writes the BrowserState, immediately re-run restore_session
    # so the correct view and all content render without a manual browser refresh.
    login_btn.click(do_login, inputs=[user_in, pass_in, mem_session], outputs=_LOGIN_OUTS).then(
        restore_session, inputs=[session], outputs=_RESTORE_OUTS
    )
    pass_in.submit(do_login, inputs=[user_in, pass_in, mem_session], outputs=_LOGIN_OUTS).then(
        restore_session, inputs=[session], outputs=_RESTORE_OUTS
    )

    for _btn in [prof_logout, student_logout]:
        _btn.click(
            do_logout,
            outputs=[mem_session, session, login_view, prof_view, student_view],
        )

    demo.load(restore_session, inputs=[session], outputs=_RESTORE_OUTS)

    upload_btn.click(
        handle_upload,
        inputs=[upload_file, upload_week],
        outputs=[upload_status, pdf_sidebar, settings_pdf_dd, delete_week_dd],
    )

    settings_pdf_dd.change(
        on_settings_pdf_select,
        inputs=[settings_pdf_dd],
        outputs=[settings_rubric_in, settings_num_in, settings_type_in, settings_topic_dd],
    )
    settings_save_btn.click(
        handle_save_settings,
        inputs=[settings_pdf_dd, settings_rubric_in, settings_num_in, settings_type_in],
        outputs=[settings_status],
    )
    gen_questions_btn.click(
        handle_generate_questions,
        inputs=[settings_pdf_dd, settings_topic_dd, settings_num_in, settings_type_in],
        outputs=[gen_status, *gen_q_boxes, confirm_quiz_btn, quiz_gen_state],
    )
    confirm_quiz_btn.click(
        handle_confirm_quiz,
        inputs=[settings_pdf_dd, settings_topic_dd, settings_type_in, quiz_gen_state, *gen_q_boxes],
        outputs=[confirm_quiz_status],
    )
    delete_week_btn.click(
        handle_delete_week,
        inputs=[delete_week_dd],
        outputs=[delete_status, pdf_sidebar, settings_pdf_dd, delete_week_dd],
    )

    refresh_btn.click(refresh_dashboard, outputs=[stat_cards, student_table])
    export_btn.click(handle_export,      outputs=[export_status, export_file])

    review_student_dd.change(
        on_review_student,
        inputs=[review_student_dd],
        outputs=[review_attempt_dd, review_detail_html],
    )
    review_attempt_dd.change(
        on_review_attempt,
        inputs=[review_attempt_dd],
        outputs=[review_detail_html, review_score_in],
    )
    review_approve_btn.click(
        handle_approve,
        inputs=[review_attempt_dd, review_score_in],
        outputs=[review_status, stat_cards, student_table, review_detail_html],
    )

    # week_selector.change wired below after _TAKE_OUTS is defined

    chat_in.submit(handle_chat, inputs=[chat_in, chatbot], outputs=[chatbot, chat_in])
    send_btn.click(handle_chat, inputs=[chat_in, chatbot], outputs=[chatbot, chat_in])

    grades_refresh_btn.click(refresh_grades, inputs=[mem_session], outputs=[final_grades_html])

    materials_dd.change(on_material_select, inputs=[materials_dd], outputs=[materials_detail])
    set_topic_btn.click(
        handle_set_topic,
        inputs=[materials_dd],
        outputs=[week_selector, topic_status, tutor_week_bar],
    )

    _TAKE_OUTS = [
        quiz_panel, *quiz_q_html, quiz_state, quiz_status,
        result_area, feedback_area,
        comp_check_html, comp_check_in, comp_check_btn, comp_check_result,
        feedback_state,
        *quiz_answers,
        *quiz_radio,
    ]
    take_quiz_btn.click(handle_take_quiz, inputs=[mem_session], outputs=_TAKE_OUTS)

    week_selector.change(
        set_student_week,
        inputs=[week_selector],
        outputs=[week_status, tutor_week_bar, *_TAKE_OUTS],
    )

    _SUBMIT_OUTS = [
        result_area, feedback_area,
        comp_check_html, comp_check_in, comp_check_btn, comp_check_result,
        feedback_state,
    ]
    submit_btn.click(handle_submit_quiz, inputs=[quiz_state, mem_session, *quiz_answers, *quiz_radio], outputs=_SUBMIT_OUTS)

    comp_check_btn.click(handle_comp_check, inputs=[comp_check_in, feedback_state], outputs=[comp_check_result])


if __name__ == "__main__":
    demo.launch(
        theme=gr.themes.Base(
            font=gr.themes.GoogleFont("Inter"),
            font_mono=gr.themes.GoogleFont("Inter"),
        ),
        css=CSS,
    )
