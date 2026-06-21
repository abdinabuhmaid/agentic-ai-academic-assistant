# Agentic AI for Academic Staff

A capstone project: an agentic AI assistant for academic staff that unifies
three agents — a **Research Agent**, a **Teaching Agent**, and a **Grading
Agent** — over a shared context bus. It ingests course PDFs, tutors students,
generates tagged quizzes, grades answers with structured output, and classifies
each mistake (conceptual / knowledge gap / careless) for targeted remediation.

Built with Python, the **Groq API** for inference, **Gradio** for the
interface, and **SQLite** for storage.

---

## What's in here

| File / folder | What it does |
| --- | --- |
| `app.py` | The Gradio interface — run this. Three tabs: Ingest, Tutor, Quiz. |
| `config.py` | Loads your API key and sets the model and database path. |
| `database.py` | SQLite setup and all save/load helpers. |
| `context_bus.py` | The shared context the three agents read and write. |
| `ingestion.py` | Extracts text from uploaded PDFs. |
| `agents/` | The three agents plus shared `base_agent.py` (Groq call logic). |
| `prompts/` | The prompt template for each agent, kept separate for easy tuning. |
| `requirements.txt` | The Python packages this project needs. |
| `.env.example` | Template for your secret key file. |

---

## How to run it (first time)

You need **Python 3.11+** and a **Groq API key** (free at
<https://console.groq.com>).

**1. Open this folder in VS Code**, then open a terminal
(Terminal → New Terminal).

**2. Create and activate a virtual environment** (an isolated box for this
project's packages):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

You should see `(venv)` at the start of the terminal line.

> If you get *"running scripts is disabled on this system,"* run this once,
> then activate again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

> On macOS/Linux the activate command is instead: `source venv/bin/activate`

**3. Install the packages:**

```powershell
pip install -r requirements.txt
```

**4. Add your Groq key.** Make a copy of `.env.example`, name the copy `.env`,
and put your real key in it:

```
GROQ_API_KEY=gsk_your_real_key_here
```

**5. Run the app:**

```powershell
python app.py
```

Then **Ctrl+click** the local URL it prints (e.g. `http://127.0.0.1:7860`) to
open it in your browser. Press **Ctrl+C** in the terminal to stop it.

---

## How to run it (every time after that)

1. Open the folder in VS Code, open a terminal.
2. Activate the environment: `.\venv\Scripts\Activate.ps1`
3. `python app.py`

---

## Using the app

1. **Upload & Ingest** — pick a week number, upload a course PDF, click Ingest.
   The Research Agent builds a knowledge base for that week.
2. **Tutor** — ask questions about the material; the Teaching Agent answers.
3. **Quiz** — generate a quiz, type your answers, click Grade. The Grading
   Agent scores out of 10 and classifies any mistakes.

---

## Changing the model

The model is set in `config.py` (`MODEL` and `FAST_MODEL`). Groq occasionally
retires models — if you ever see a "model not found" error, check the current
list at <https://console.groq.com/docs/models> and update those values.

---

## Next milestones (not yet implemented)

- The **feedback loop**: route a missed question back to the right agent
  (re-teach mode is sketched in `prompts/teaching_prompts.py`).
- A **comprehension check** after re-teaching to close the loop.
- A **performance analyser** and **professor dashboard** (rubric trace, export).

---

## AI usage disclosure

In line with the course policy, this project was developed with AI assistance.
Tools used:

- **Claude Code** — coding assistance (scaffolding, debugging, refactoring).
- **Groq API** — the language-model inference that powers the three agents.
- **Gradio** — the user-interface framework.

All AI-generated code and content was reviewed, tested, and verified by the
project team, who take full responsibility for the final work.
