"""
config.py
---------
Central place for configuration. Loads your secret Groq API key from the
.env file and creates one shared Groq client that every agent reuses.

Nothing in here should ever be hard-coded with your real key — it always
comes from the .env file, which is never uploaded to GitHub.
"""

import os
from dotenv import load_dotenv
from groq import Groq

# Read the .env file in this folder and load its values into the environment.
load_dotenv()

# Pull the key out of the environment. If it's missing, fail early with a
# clear message instead of a confusing error deep inside an API call.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY not found. Create a file named .env in this folder "
        "with the line:  GROQ_API_KEY=your_key_here"
    )

# One shared client for the whole app.
client = Groq(api_key=GROQ_API_KEY)

# --- Model choice -----------------------------------------------------------
# MODEL is the high-quality model used for teaching and grading.
# FAST_MODEL is cheaper/faster, fine for lighter tasks.
# Groq occasionally retires models — if you get a "model not found" error,
# check the current list at https://console.groq.com/docs/models and update.
MODEL = "llama-3.3-70b-versatile"
FAST_MODEL = "llama-3.1-8b-instant"

# Where the SQLite database file lives (created automatically on first run).
DB_PATH = "capstone.db"

# --- Performance monitoring -------------------------------------------------
ROLLING_WINDOW = 3        # number of recent quizzes used for rolling average
AT_RISK_THRESHOLD = 5.0   # rolling average below this flags a student as at-risk
RECOVERABLE_CAP = 7.0     # realistic score ceiling for a struggling student
