"""
database.py
-----------
Everything that touches the SQLite database lives here.
"""

import sqlite3
import json
import hashlib
import secrets
from datetime import datetime

DB_PATH = "capstone.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    """Create all tables and run any pending migrations. Safe to call on every startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            display_name  TEXT    NOT NULL,
            role          TEXT    NOT NULL CHECK(role IN ('professor', 'student')),
            created_at    TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            week       INTEGER NOT NULL,
            filename   TEXT    NOT NULL,
            raw_text   TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            week         INTEGER NOT NULL,
            summary      TEXT,
            key_concepts TEXT,
            glossary     TEXT,
            created_at   TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rubrics (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            week         INTEGER NOT NULL,
            rubric_text  TEXT    NOT NULL,
            created_at   TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            week           INTEGER NOT NULL,
            questions_json TEXT    NOT NULL,
            created_at     TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id          INTEGER NOT NULL,
            student_username TEXT    NOT NULL DEFAULT '',
            results_json     TEXT    NOT NULL,
            score            REAL,
            created_at       TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weak_topics (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            student_username TEXT    NOT NULL,
            concept          TEXT    NOT NULL,
            week             INTEGER NOT NULL,
            created_at       TEXT    NOT NULL
        )
    """)

    conn.commit()

    # Incremental migrations — safe to re-run, errors mean the column already exists.
    migrations = [
        ("attempts", "student_username", "TEXT NOT NULL DEFAULT ''"),
        ("attempts", "approval_state",   "TEXT NOT NULL DEFAULT 'pending'"),
        ("attempts", "approved_score",   "REAL"),
        ("rubrics",  "num_questions",    "INTEGER NOT NULL DEFAULT 4"),
        ("rubrics",  "quiz_type",        "TEXT NOT NULL DEFAULT 'open'"),
        ("rubrics",  "resource_id",      "INTEGER"),
        ("quizzes",  "topic",            "TEXT"),
        ("quizzes",  "confirmed",        "INTEGER NOT NULL DEFAULT 0"),
        ("quizzes",  "resource_id",      "INTEGER"),
        ("quizzes",  "quiz_type",        "TEXT NOT NULL DEFAULT 'open'"),
    ]
    for table, col, defn in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            conn.commit()
        except Exception:
            pass

    conn.close()


# ── Password helpers ───────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}:{key.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, key_hex = stored.split(":", 1)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return secrets.compare_digest(key.hex(), key_hex)


# ── User management ────────────────────────────────────────────────────────

def create_user(username: str, password: str, display_name: str, role: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, display_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (username, _hash_password(password), display_name, role, _now()),
    )
    conn.commit()
    conn.close()


def verify_login(username: str, password: str):
    """Return a user-info dict if credentials are valid, otherwise None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT username, password_hash, display_name, role FROM users WHERE username = ?",
        (username.strip().lower(),),
    ).fetchone()
    conn.close()
    if row is None or not _verify_password(password, row["password_hash"]):
        return None
    return {
        "username":     row["username"],
        "display_name": row["display_name"],
        "role":         row["role"],
    }


def seed_users():
    """Insert the two demo accounts on first run if they don't already exist."""
    conn = get_connection()
    existing = {r["username"] for r in conn.execute("SELECT username FROM users").fetchall()}
    # Rename legacy username "hamza" → "prof" on existing databases
    if "hamza" in existing and "prof" not in existing:
        conn.execute("UPDATE users SET username = 'prof' WHERE username = 'hamza'")
        conn.commit()
        existing.discard("hamza")
        existing.add("prof")
    # Fix display name on existing prof account
    conn.execute(
        "UPDATE users SET display_name = 'Professor Fatih' WHERE username = 'prof'",
    )
    conn.commit()
    conn.close()
    if "prof" not in existing:
        create_user("prof", "abcd1234", "Professor Fatih", "professor")
    if "abdin" not in existing:
        create_user("abdin", "abcd1234", "Abdin", "student")
    if "hamza" not in existing:
        create_user("hamza", "abcd1234", "Hamza", "student")


def get_students():
    """Return [(username, display_name), ...] for all student accounts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT username, display_name FROM users WHERE role = 'student' ORDER BY display_name"
    ).fetchall()
    conn.close()
    return [(r["username"], r["display_name"]) for r in rows]


# ── Rubrics ────────────────────────────────────────────────────────────────

def save_rubric(resource_id: int, rubric_text: str, num_questions: int = 4, quiz_type: str = "open"):
    """Save rubric settings keyed to a specific uploaded PDF (resource_id)."""
    conn = get_connection()
    # Look up the week for context
    res_row = conn.execute("SELECT week FROM resources WHERE id = ?", (resource_id,)).fetchone()
    week = res_row["week"] if res_row else 0
    existing = conn.execute(
        "SELECT id FROM rubrics WHERE resource_id = ?", (resource_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE rubrics SET rubric_text=?, num_questions=?, quiz_type=? WHERE resource_id=?",
            (rubric_text, num_questions, quiz_type, resource_id),
        )
    else:
        conn.execute(
            "INSERT INTO rubrics (resource_id, week, rubric_text, num_questions, quiz_type, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (resource_id, week, rubric_text, num_questions, quiz_type, _now()),
        )
    conn.commit()
    conn.close()


def delete_week(week: int):
    """Remove all uploaded material for a week (resource, KB, rubrics). Quiz attempts are preserved."""
    conn = get_connection()
    conn.execute("DELETE FROM resources WHERE week = ?", (week,))
    conn.execute("DELETE FROM knowledge_base WHERE week = ?", (week,))
    conn.execute("DELETE FROM rubrics WHERE week = ?", (week,))
    conn.commit()
    conn.close()


def get_rubric(week: int):
    """Return the most recent rubric text for a week, or None if none/empty."""
    conn = get_connection()
    row = conn.execute(
        "SELECT rubric_text FROM rubrics WHERE week = ? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    return (row["rubric_text"] or None) if row else None


def get_num_questions(week: int) -> int:
    """Return the professor's configured question count for a week, defaulting to 4."""
    conn = get_connection()
    row = conn.execute(
        "SELECT num_questions FROM rubrics WHERE week = ? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    return int(row["num_questions"]) if row else 4


def get_quiz_type(week: int) -> str:
    """Return 'open' or 'mcq' for the week's quiz type, defaulting to 'open'."""
    conn = get_connection()
    row = conn.execute(
        "SELECT quiz_type FROM rubrics WHERE week = ? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    return (row["quiz_type"] or "open") if row else "open"


def get_rubric_settings(week: int):
    """Return the most recent rubric settings for a week, or None if none set."""
    conn = get_connection()
    row = conn.execute(
        "SELECT rubric_text, num_questions, quiz_type FROM rubrics WHERE week = ? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "rubric_text":   row["rubric_text"] or "",
        "num_questions": int(row["num_questions"]),
        "quiz_type":     row["quiz_type"] or "open",
    }


def get_rubric_settings_by_resource(resource_id: int):
    """Return rubric settings for a specific uploaded PDF, or None if none saved."""
    conn = get_connection()
    row = conn.execute(
        "SELECT rubric_text, num_questions, quiz_type FROM rubrics WHERE resource_id = ? LIMIT 1",
        (resource_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "rubric_text":   row["rubric_text"] or "",
        "num_questions": int(row["num_questions"]),
        "quiz_type":     row["quiz_type"] or "open",
    }


def get_num_questions_by_resource(resource_id: int) -> int:
    s = get_rubric_settings_by_resource(resource_id)
    return s["num_questions"] if s else 4


def get_quiz_type_by_resource(resource_id: int) -> str:
    s = get_rubric_settings_by_resource(resource_id)
    return s["quiz_type"] if s else "open"


# ── Resources ──────────────────────────────────────────────────────────────

def save_resource(week, filename, raw_text) -> int:
    """Insert a resource row and return its new ID."""
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO resources (week, filename, raw_text, created_at) VALUES (?, ?, ?, ?)",
        (week, filename, raw_text, _now()),
    )
    resource_id = cur.lastrowid
    conn.commit()
    conn.close()
    return resource_id


def get_resources_list():
    """Return [(week, filename), ...] for all uploaded resources, ordered by week then id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT week, filename FROM resources ORDER BY week, id"
    ).fetchall()
    conn.close()
    return [(r["week"], r["filename"]) for r in rows]


def get_resources_with_ids():
    """Return [(id, week, filename), ...] for all uploaded resources, ordered by week then id."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, week, filename FROM resources ORDER BY week, id"
    ).fetchall()
    conn.close()
    return [(r["id"], r["week"], r["filename"]) for r in rows]


def delete_resource(resource_id: int):
    """Delete one uploaded PDF by its row ID. Cleans up KB and rubric if it was the last for its week."""
    conn = get_connection()
    row = conn.execute("SELECT week FROM resources WHERE id = ?", (resource_id,)).fetchone()
    if not row:
        conn.close()
        return
    week = row["week"]
    conn.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
    # always remove the rubric tied to this specific PDF
    conn.execute("DELETE FROM rubrics WHERE resource_id = ?", (resource_id,))
    remaining = conn.execute(
        "SELECT COUNT(*) as n FROM resources WHERE week = ?", (week,)
    ).fetchone()["n"]
    if remaining == 0:
        conn.execute("DELETE FROM knowledge_base WHERE week = ?", (week,))
        conn.execute("DELETE FROM rubrics WHERE week = ?", (week,))  # legacy week-keyed rows
    conn.commit()
    conn.close()


# ── Knowledge base ─────────────────────────────────────────────────────────

def save_knowledge(week, summary, key_concepts, glossary):
    conn = get_connection()
    conn.execute(
        """INSERT INTO knowledge_base (week, summary, key_concepts, glossary, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (week, summary, json.dumps(key_concepts), json.dumps(glossary), _now()),
    )
    conn.commit()
    conn.close()


def get_knowledge(week):
    """Return the most recent knowledge-base entry for a week, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM knowledge_base WHERE week = ? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "week":         row["week"],
        "summary":      row["summary"],
        "key_concepts": json.loads(row["key_concepts"] or "[]"),
        "glossary":     json.loads(row["glossary"] or "[]"),
    }


def get_available_weeks():
    """Return a sorted list of weeks that have ingested material."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT week FROM knowledge_base ORDER BY week"
    ).fetchall()
    conn.close()
    return [row["week"] for row in rows]


def get_latest_week():
    conn = get_connection()
    row = conn.execute("SELECT MAX(week) as w FROM knowledge_base").fetchone()
    conn.close()
    return row["w"] if row and row["w"] is not None else None


# ── Quizzes ────────────────────────────────────────────────────────────────

def save_quiz(week, questions):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO quizzes (week, questions_json, created_at) VALUES (?, ?, ?)",
        (week, json.dumps(questions), _now()),
    )
    quiz_id = cur.lastrowid
    conn.commit()
    conn.close()
    return quiz_id


# ── Attempts ───────────────────────────────────────────────────────────────

def save_attempt(quiz_id, results, score, student_username=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO attempts
           (quiz_id, student_username, results_json, score, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (quiz_id, student_username, json.dumps(results), score, _now()),
    )
    conn.commit()
    conn.close()


def get_attempts_for_student(username: str):
    """All attempts for a student, newest first, with the quiz's week and PDF filename."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.id, a.quiz_id, a.results_json, a.score,
                  a.approval_state, a.approved_score, a.created_at, q.week,
                  (SELECT filename FROM resources
                   WHERE week = q.week ORDER BY id DESC LIMIT 1) AS filename
           FROM attempts a
           JOIN quizzes q ON a.quiz_id = q.id
           WHERE a.student_username = ?
           ORDER BY a.created_at DESC""",
        (username,),
    ).fetchall()
    conn.close()
    return [
        {
            "id":             r["id"],
            "quiz_id":        r["quiz_id"],
            "week":           r["week"],
            "filename":       r["filename"] or "",
            "results":        json.loads(r["results_json"] or "{}"),
            "ai_score":       r["score"],
            "approval_state": r["approval_state"] or "pending",
            "approved_score": r["approved_score"],
            "created_at":     r["created_at"],
        }
        for r in rows
    ]


def get_attempt_by_id(attempt_id: int):
    """Single attempt by primary key, with the quiz's week number."""
    conn = get_connection()
    row = conn.execute(
        """SELECT a.id, a.quiz_id, a.results_json, a.score,
                  a.approval_state, a.approved_score, a.created_at, q.week
           FROM attempts a
           JOIN quizzes q ON a.quiz_id = q.id
           WHERE a.id = ?""",
        (attempt_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id":             row["id"],
        "quiz_id":        row["quiz_id"],
        "week":           row["week"],
        "results":        json.loads(row["results_json"] or "{}"),
        "ai_score":       row["score"],
        "approval_state": row["approval_state"] or "pending",
        "approved_score": row["approved_score"],
        "created_at":     row["created_at"],
    }


def approve_attempt(attempt_id: int, approved_score: float):
    conn = get_connection()
    conn.execute(
        "UPDATE attempts SET approved_score = ?, approval_state = 'approved' WHERE id = ?",
        (approved_score, attempt_id),
    )
    conn.commit()
    conn.close()


def get_quiz_questions(quiz_id: int):
    """Return the questions list for a quiz, or [] if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT questions_json FROM quizzes WHERE id = ?", (quiz_id,)
    ).fetchone()
    conn.close()
    return json.loads(row["questions_json"]) if row else []


def get_resource_week(resource_id: int):
    """Return the week number for a resource row, or None."""
    conn = get_connection()
    row = conn.execute("SELECT week FROM resources WHERE id = ?", (resource_id,)).fetchone()
    conn.close()
    return row["week"] if row else None


def save_confirmed_quiz(resource_id: int, week: int, topic: str, questions: list, quiz_type: str = "open") -> int:
    """Replace the professor-confirmed quiz for a resource and return the new quiz id."""
    conn = get_connection()
    conn.execute("DELETE FROM quizzes WHERE resource_id = ? AND confirmed = 1", (resource_id,))
    cur = conn.execute(
        "INSERT INTO quizzes (week, questions_json, topic, confirmed, resource_id, quiz_type, created_at)"
        " VALUES (?, ?, ?, 1, ?, ?, ?)",
        (week, json.dumps(questions), topic, resource_id, quiz_type, _now()),
    )
    quiz_id = cur.lastrowid
    conn.commit()
    conn.close()
    return quiz_id


def get_confirmed_quiz_for_resource(resource_id: int):
    """Return the confirmed quiz for a specific PDF resource, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, questions_json, topic, quiz_type FROM quizzes"
        " WHERE resource_id = ? AND confirmed = 1 ORDER BY id DESC LIMIT 1",
        (resource_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "quiz_id":   row["id"],
        "questions": json.loads(row["questions_json"]),
        "topic":     row["topic"] or "",
        "quiz_type": row["quiz_type"] or "open",
    }


def get_confirmed_quiz_for_week(week: int):
    """Return the most recent confirmed quiz for a week (fallback when no resource is pinned), or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, questions_json, topic, quiz_type FROM quizzes"
        " WHERE week = ? AND confirmed = 1 ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "quiz_id":   row["id"],
        "questions": json.loads(row["questions_json"]),
        "topic":     row["topic"] or "",
        "quiz_type": row["quiz_type"] or "open",
    }


def get_approved_grades(username: str):
    """Per-attempt grade info for the student's Final Grades tab."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.id, a.score, a.approved_score, a.approval_state,
                  a.created_at, q.week
           FROM attempts a
           JOIN quizzes q ON a.quiz_id = q.id
           WHERE a.student_username = ?
           ORDER BY q.week, a.created_at""",
        (username,),
    ).fetchall()
    conn.close()
    return [
        {
            "week":           r["week"],
            "ai_score":       r["score"],
            "approved_score": r["approved_score"],
            "approval_state": r["approval_state"] or "pending",
            "created_at":     r["created_at"],
        }
        for r in rows
    ]


# ── Weak topics ────────────────────────────────────────────────────────────

def save_weak_topic(username: str, concept: str, week: int):
    """Record a weak topic for a student; skips duplicates within the same week."""
    conn = get_connection()
    exists = conn.execute(
        "SELECT id FROM weak_topics WHERE student_username = ? AND concept = ? AND week = ?",
        (username, concept, week),
    ).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO weak_topics (student_username, concept, week, created_at) VALUES (?, ?, ?, ?)",
            (username, concept, week, _now()),
        )
        conn.commit()
    conn.close()


def get_weak_topics(username: str):
    """Return the student's most recent distinct weak-topic concepts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT concept FROM weak_topics WHERE student_username = ? ORDER BY created_at DESC LIMIT 10",
        (username,),
    ).fetchall()
    conn.close()
    return [r["concept"] for r in rows]


# ── Professor dashboard ────────────────────────────────────────────────────

def get_dashboard_rows(rolling_window: int = 3, at_risk_threshold: float = 5.0):
    """
    One row per student for the professor dashboard.
    Uses approved_score when available; falls back to AI score for pending attempts.
    Row: [display_name, quiz_count, avg_score, weak_topics_str, status]
    """
    conn = get_connection()
    students = conn.execute(
        "SELECT username, display_name FROM users WHERE role = 'student' ORDER BY display_name"
    ).fetchall()

    rows = []
    for s in students:
        uname = s["username"]

        # Use approved_score when available, AI score otherwise.
        raw = conn.execute(
            """SELECT score, approved_score FROM attempts
               WHERE student_username = ? AND score IS NOT NULL
               ORDER BY created_at DESC""",
            (uname,),
        ).fetchall()

        scores = [
            (r["approved_score"] if r["approved_score"] is not None else r["score"])
            for r in raw
        ]

        quiz_count = len(scores)
        avg        = round(sum(scores) / len(scores), 1) if scores else None

        recent       = scores[:rolling_window]
        rolling_avg  = sum(recent) / len(recent) if recent else None
        at_risk      = rolling_avg is not None and rolling_avg < at_risk_threshold

        weak = conn.execute(
            "SELECT DISTINCT concept FROM weak_topics WHERE student_username = ? ORDER BY created_at DESC LIMIT 5",
            (uname,),
        ).fetchall()
        weak_str = ", ".join(r["concept"] for r in weak) if weak else "—"

        rows.append([
            s["display_name"],
            quiz_count,
            avg if avg is not None else "—",
            weak_str,
            "⚠ At Risk" if at_risk else ("✓ On Track" if quiz_count > 0 else "No data"),
        ])

    conn.close()
    return rows
