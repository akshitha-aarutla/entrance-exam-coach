"""
Entrance Exam Coach - Flask Backend
-------------------------------------
Complete backend for the Entrance Exam Coach project.

=====================================================================
 BASE PAPER MAPPING
 (DK-PRACTICE: An Intelligent Educational Platform for Personalized
  Learning Content Recommendations Based on Students' Knowledge State
  — Delianidi et al., 2024)
=====================================================================

  Base Paper Step              -> This Project's Module / Route
  ------------------------------------------------------------------
  Step 1: Student Assessment    -> Mock Test (mocktest.html,
                                    /api/generate-questions)
  Step 2: Dynamic Question       -> Adaptive Question Generator
          Selection                 (/api/generate-questions with
                                    previous_percentage difficulty hint)
  Step 3: Knowledge Tracing       -> Score Analysis & Classification
          (predict knowledge        (/api/analyze-results,
           level)                   classify_score(): Needs Improvement /
                                    Intermediate / Proficient using
                                    50% Threshold / 70% Target — OBE
                                    framework)
  Step 4: Weak Topic Detection    -> Weak Subject/Topic Identification
                                    (analyze_results(): weak_subjects,
                                    weak_topics_json stored per test)
  Step 5: Content Recommendation  -> AI Remedial Recommendation Module
                                    (/api/remedial-recommendation,
                                    Gemini-based — generates learning
                                    objectives, topics to revise,
                                    explanation, practice activities,
                                    concept gap rationale)
  Step 6: Pre-test / Post-test     -> Retake Test (Adaptive) flow
          (measure improvement)     (/api/last-results feeds the next
                                    test's question topics + difficulty;
                                    progress chart on analysis.html
                                    compares tests over time)

  Additional module (not in base paper, added for this project):
  Adaptive Learning -> Personalized Timetable Generator
                        (/api/generate-timetable, weightage-based,
                        prioritizes weak topics from Knowledge Tracing)

  NOTE ON ML MODEL:
  The base paper uses a Feedforward Neural Network + PB-BoW
  (Paired-Bipolar Bag-of-Words) Knowledge Tracing model trained on a
  student-interaction dataset to predict knowledge state.
  This project uses the Google Gemini LLM API as a lightweight
  substitute for that trained ML model — Gemini performs the
  equivalent of "Content Recommendation" (Step 5) and assists with
  "Dynamic Question Selection" (Step 2) by generating questions whose
  difficulty is adapted based on the student's previous score
  (previous_percentage), and "Knowledge Tracing" (Step 3) is handled
  by rule-based score classification (Threshold/Target, OBE framework)
  rather than a neural network, since training a custom KT model was
  out of scope for this mini-project.

=====================================================================

Features:
- User signup/login (bcrypt password hashing + Flask session)
- SQLite database (auto-created on first run)
- Mock test result analysis with Threshold/Target classification
  (Knowledge Tracing equivalent)
- Weightage-based personalized study timetable generator
  (Adaptive Learning module)
- Gemini API integration for:
    - Remedial recommendations (Content Recommendation module)
    - AI-generated, difficulty-adaptive practice questions
      (Dynamic Question Selection)
    - AI doubt-solving chatbot
- Graceful fallbacks if Gemini API fails

Run with: python app.py
"""

import os
import json
import functools
from datetime import datetime, date

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
import bcrypt

import config
from weightage_data import WEIGHTAGE
import db as dbmod

import requests

# AI provider: Groq (free, fast, OpenAI-compatible API)
GROQ_API_KEY = getattr(config, "GROQ_API_KEY", "")
GROQ_AVAILABLE = bool(GROQ_API_KEY and GROQ_API_KEY != "PASTE_YOUR_GROQ_API_KEY_HERE")
GROQ_MODEL = getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Kept for backward compatibility with the rest of the code/comments below
# (this project previously used Gemini; GEMINI_AVAILABLE now mirrors Groq's
# availability so existing checks still work without further edits).
GEMINI_AVAILABLE = GROQ_AVAILABLE

# -----------------------------------------------------------------
# App setup
# -----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
app.secret_key = config.SECRET_KEY

# Session cookie settings — needed so login works correctly once the
# site is deployed over HTTPS (Render, Railway, etc. all serve HTTPS).
# Render automatically sets a RENDER=true environment variable on all
# its services, which we use to detect production. Locally (no RENDER
# env var, plain http://127.0.0.1) these settings are harmless either way.
IS_PRODUCTION = bool(os.environ.get("RENDER")) or os.environ.get("FLASK_ENV") == "production"
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)
CORS(app, supports_credentials=True)


# -----------------------------------------------------------------
# Database helpers
# -----------------------------------------------------------------
# get_db() / init_db() now live in db.py, which automatically uses
# PostgreSQL when a DATABASE_URL environment variable is present
# (set automatically by Render/Railway/Heroku-style hosts), and falls
# back to a local SQLite file (database.db) for development on your
# own laptop. This lets the exact same code run locally and in
# production without changes.
get_db = dbmod.get_db
init_db = dbmod.init_db


# -----------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------
def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        return f(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------
# Auth routes
# -----------------------------------------------------------------
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Name, email and password are required."}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Email already registered. Please login."}), 409

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, password_hash, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Signup successful! Please login."}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cur.fetchone()
    conn.close()

    if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]

    return jsonify({
        "message": "Login successful.",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]}
    }), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."}), 200


@app.route("/api/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"logged_in": False}), 200
    return jsonify({
        "logged_in": True,
        "user": {"id": session["user_id"], "name": session["user_name"], "email": session["user_email"]}
    }), 200


# -----------------------------------------------------------------
# [BASE PAPER STEP 3: Knowledge Tracing]
# Classification helper (Threshold/Target - OBE framework)
# Predicts the student's knowledge level for a subject from their score.
# -----------------------------------------------------------------
def classify_score(percentage):
    if percentage < 50:
        return "Needs Improvement"
    elif percentage <= 70:
        return "Intermediate"
    else:
        return "Proficient"


# -----------------------------------------------------------------
# [BASE PAPER STEP 3 + 4: Knowledge Tracing & Weak Topic Detection]
# Analyze results: classifies each subject's knowledge level and
# identifies weak subjects/topics, then stores the result for use
# in Step 5 (Content Recommendation) and Step 6 (Pre/Post-test
# comparison via /api/last-results).
# -----------------------------------------------------------------
@app.route("/api/analyze-results", methods=["POST"])
@login_required
def analyze_results():
    """
    Input JSON:
    {
        "exam_type": "jee_main",
        "results": {
            "Physics": {"score": 2, "total": 3, "weak_topics": ["Mechanics"]},
            "Chemistry": {"score": 1, "total": 3, "weak_topics": ["Organic Chemistry - Reactions"]}
        }
    }
    """
    data = request.get_json(silent=True) or {}
    exam_type = data.get("exam_type")
    results = data.get("results", {})

    if not exam_type or not results:
        return jsonify({"error": "exam_type and results are required."}), 400

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    analysis = {}
    weak_subjects = []

    for subject, info in results.items():
        score = int(info.get("score", 0))
        total = int(info.get("total", 1))
        weak_topics = info.get("weak_topics", [])
        percentage = round((score / total) * 100) if total > 0 else 0
        classification = classify_score(percentage)

        if classification != "Proficient":
            weak_subjects.append(subject)

        analysis[subject] = {
            "score": score,
            "total": total,
            "percentage": percentage,
            "classification": classification,
            "weak_topics": weak_topics
        }

        cur.execute(
            """INSERT INTO test_results
               (user_id, exam_type, subject, score, total_questions, weak_topics_json, test_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, exam_type, subject, score, total, json.dumps(weak_topics), datetime.utcnow().isoformat())
        )

    conn.commit()
    conn.close()

    return jsonify({
        "exam_type": exam_type,
        "analysis": analysis,
        "weak_subjects": weak_subjects
    }), 200


@app.route("/api/last-results", methods=["GET"])
@login_required
def last_results():
    """
    [BASE PAPER STEP 6: Pre-test / Post-test comparison]
    Returns the most recent test result per subject for the logged-in user.
    Used when retaking a test (Post-test), so questions/timetable can
    adapt to the student's latest performance (Pre-test).
    """
    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT subject, exam_type, score, total_questions, weak_topics_json, test_date
        FROM test_results
        WHERE user_id = ?
        ORDER BY test_date DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    latest_by_subject = {}
    for row in rows:
        sub = row["subject"]
        if sub not in latest_by_subject:
            percentage = round((row["score"] / row["total_questions"]) * 100) if row["total_questions"] > 0 else 0
            latest_by_subject[sub] = {
                "exam_type": row["exam_type"],
                "score": row["score"],
                "total": row["total_questions"],
                "percentage": percentage,
                "classification": classify_score(percentage),
                "weak_topics": json.loads(row["weak_topics_json"] or "[]"),
                "test_date": row["test_date"]
            }

    return jsonify({"last_results": latest_by_subject}), 200


@app.route("/api/test-history", methods=["GET"])
@login_required
def test_history():
    """
    [BASE PAPER STEP 6: Pre-test / Post-test comparison]
    Returns the FULL history of test results per subject for the logged-in
    user, ordered oldest -> newest, so the frontend can show a clear
    test-by-test progress comparison (e.g. "Test 1: 33% -> Test 2: 60%").
    """
    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT subject, exam_type, score, total_questions, weak_topics_json, test_date
        FROM test_results
        WHERE user_id = ?
        ORDER BY test_date ASC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    history_by_subject = {}
    for row in rows:
        sub = row["subject"]
        percentage = round((row["score"] / row["total_questions"]) * 100) if row["total_questions"] > 0 else 0
        entry = {
            "exam_type": row["exam_type"],
            "score": row["score"],
            "total": row["total_questions"],
            "percentage": percentage,
            "classification": classify_score(percentage),
            "weak_topics": json.loads(row["weak_topics_json"] or "[]"),
            "test_date": row["test_date"]
        }
        history_by_subject.setdefault(sub, []).append(entry)

    return jsonify({"history": history_by_subject}), 200


# -----------------------------------------------------------------
# [ADDITIONAL MODULE — Adaptive Learning / Personalized Timetable]
# (Maps to "Adaptive learning -> Personalized timetable" in the
#  base-paper comparison table. Uses the weak topics from Step 4
#  to prioritize what gets scheduled first.)
# Timetable generator
# -----------------------------------------------------------------
def build_timetable(exam_type, days_left, weak_subjects, all_subjects, weak_topics_by_subject):
    """
    Build a ROLLING WEEKLY timetable (max 7 days, or fewer if days_left < 7).

    `days_left` (days until the actual exam) is used ONLY to decide WHICH
    topics qualify for this week's plan (the weightage tier), per the
    rules below. The returned timetable itself always covers at most one
    week, so it can be regenerated each week as the student's weak topics
    change (via Retake Test).

      days_left < 15   -> only HIGH weightage topics from weak subjects
      15 <= days_left <= 45 -> HIGH + MEDIUM from weak subjects, light
                               revision of strong subjects
      days_left > 45   -> full syllabus, all subjects, weighted by
                          importance and weakness

    Returns a list of {"day": n, "tasks": [ {subject, topic, hours, weightage}, ... ]}
    """
    exam_weightage = WEIGHTAGE.get(exam_type, {})
    strong_subjects = [s for s in all_subjects if s not in weak_subjects]

    # Build topic pool depending on days_left
    topic_pool = []  # list of dicts {subject, topic, weightage, hours}

    def topics_for(subject, levels):
        subj_topics = exam_weightage.get(subject, {})
        return [(t, w) for t, w in subj_topics.items() if w in levels]

    if days_left < 15:
        # Only HIGH weightage topics from weak subjects
        for sub in weak_subjects:
            for topic, w in topics_for(sub, ["high"]):
                topic_pool.append({"subject": sub, "topic": topic, "weightage": w, "hours": 2})

    elif 15 <= days_left <= 45:
        # HIGH + MEDIUM from weak subjects
        for sub in weak_subjects:
            for topic, w in topics_for(sub, ["high", "medium"]):
                hours = 2 if w == "high" else 1
                topic_pool.append({"subject": sub, "topic": topic, "weightage": w, "hours": hours})
        # Light revision of strong subjects (high topics only, 1 hr)
        for sub in strong_subjects:
            for topic, w in topics_for(sub, ["high"]):
                topic_pool.append({"subject": sub, "topic": topic, "weightage": w, "hours": 1})

    else:
        # Full syllabus, all subjects, weak subjects / high weightage get more hours
        for sub in all_subjects:
            subj_topics = exam_weightage.get(sub, {})
            for topic, w in subj_topics.items():
                if sub in weak_subjects:
                    hours = 2 if w == "high" else (1 if w == "medium" else 1)
                else:
                    hours = 2 if w == "high" else 1
                topic_pool.append({"subject": sub, "topic": topic, "weightage": w, "hours": hours})

    if not topic_pool:
        # Fallback: if no topics found (e.g. unknown exam type), give generic revision
        for sub in all_subjects:
            topic_pool.append({"subject": sub, "topic": "General Revision", "weightage": "high", "hours": 2})

    # Sort: specific weak topics first, then weak subjects, then high weightage first
    weightage_order = {"high": 0, "medium": 1, "low": 2}

    def is_specific_weak_topic(task):
        return task["topic"] in weak_topics_by_subject.get(task["subject"], [])

    topic_pool.sort(key=lambda x: (
        0 if is_specific_weak_topic(x) else 1,
        0 if x["subject"] in weak_subjects else 1,
        weightage_order.get(x["weightage"], 3)
    ))

    # Boost hours for topics the student specifically got wrong in the latest test
    for task in topic_pool:
        if is_specific_weak_topic(task):
            task["hours"] = min(task["hours"] + 1, 3)

    # Distribute across days. Max ~4 hours per day.
    MAX_HOURS_PER_DAY = 4

    # ROLLING WEEKLY WINDOW: never plan more than 7 days at once, even if
    # days_left is large. If fewer than 7 days remain until the exam,
    # use exactly that many days (the final sprint).
    num_days = min(max(days_left, 1), 7)

    timetable = [{"day": d + 1, "tasks": [], "total_hours": 0} for d in range(num_days)]

    # Round-robin distribution with hour cap per day, cycling through topic pool
    day_idx = 0
    pool_idx = 0
    pool_len = len(topic_pool)
    safety_counter = 0
    max_iterations = num_days * MAX_HOURS_PER_DAY * 3  # avoid infinite loops

    while day_idx < num_days and safety_counter < max_iterations:
        safety_counter += 1
        task = topic_pool[pool_idx % pool_len]
        day = timetable[day_idx]

        if day["total_hours"] + task["hours"] <= MAX_HOURS_PER_DAY:
            day["tasks"].append({
                "subject": task["subject"],
                "topic": task["topic"],
                "hours": task["hours"],
                "weightage": task["weightage"]
            })
            day["total_hours"] += task["hours"]
            pool_idx += 1
        else:
            day_idx += 1

    # Any remaining empty days get a generic revision task
    for day in timetable:
        if not day["tasks"]:
            day["tasks"].append({
                "subject": "General",
                "topic": "Revision & Practice Tests",
                "hours": 2,
                "weightage": "medium"
            })
            day["total_hours"] = 2

    return timetable


@app.route("/api/generate-timetable", methods=["POST"])
@login_required
def generate_timetable():
    """
    Input JSON:
    {
        "exam_type": "jee_main",
        "exam_date": "2026-08-15",
        "analysis": { ... result of /api/analyze-results "analysis" field ... }
    }
    """
    data = request.get_json(silent=True) or {}
    exam_type = data.get("exam_type")
    exam_date_str = data.get("exam_date")
    analysis = data.get("analysis", {})

    if not exam_type or not exam_date_str:
        return jsonify({"error": "exam_type and exam_date are required."}), 400

    try:
        exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "exam_date must be in YYYY-MM-DD format."}), 400

    days_left = (exam_date - date.today()).days
    if days_left < 0:
        days_left = 0

    all_subjects = list(analysis.keys()) if analysis else list(WEIGHTAGE.get(exam_type, {}).keys())
    weak_subjects = [s for s, info in analysis.items() if info.get("classification") != "Proficient"] \
        if analysis else all_subjects

    weak_topics_by_subject = {s: info.get("weak_topics", []) for s, info in analysis.items()} if analysis else {}

    timetable = build_timetable(exam_type, days_left, weak_subjects, all_subjects, weak_topics_by_subject)

    user_id = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO timetables (user_id, exam_date, days_left, plan_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, exam_date_str, days_left, json.dumps(timetable), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({
        "days_left": days_left,
        "exam_date": exam_date_str,
        "weak_subjects": weak_subjects,
        "plan_days": len(timetable),
        "timetable": timetable,
        "note": ("This is your study plan for the upcoming "
                 f"{len(timetable)} day(s). Retake the test after "
                 "completing it to get an updated plan based on your "
                 "new weak topics.")
    }), 200


# -----------------------------------------------------------------
# Gemini helper
# -----------------------------------------------------------------
def call_gemini(prompt):
    """
    Call the Groq API (OpenAI-compatible chat completions) and return the
    raw text response. Raises on failure.

    Named call_gemini for backward compatibility with the rest of the
    code/comments (which map to the base paper's "Content Recommendation"
    / "Dynamic Question Selection" modules) — internally it now uses Groq.
    """
    if not GROQ_AVAILABLE:
        raise RuntimeError("Groq API not configured.")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"Groq API error {response.status_code}: {response.text[:300]}")

    data = response.json()
    text = data["choices"][0]["message"]["content"]

    if not text:
        raise RuntimeError("Empty response from Groq.")

    return text


def extract_json(text):
    """
    Extract and parse a JSON object/array from an LLM response that may
    contain markdown code fences and/or extra explanatory text before or
    after the JSON (common with Llama models on Groq).
    """
    text = text.strip()

    # Strip markdown code fences if present
    if "```" in text:
        # Take content between the first pair of triple backticks
        parts = text.split("```")
        if len(parts) >= 2:
            candidate = parts[1]
            if candidate.lower().startswith("json"):
                candidate = candidate[4:]
            text = candidate.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back: find the first '[' or '{' and the matching last ']' or '}'
    import re
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not parse JSON from response: {text[:200]}")


# -----------------------------------------------------------------
# [BASE PAPER STEP 5: Content Recommendation]
# Remedial recommendation (Gemini) — recommends learning content
# (objectives, topics to revise, explanation, practice activities)
# for weak topics identified in Step 4.
# -----------------------------------------------------------------
FALLBACK_RECOMMENDATION = {
    "learning_objectives": [
        "Understand the core concepts of the topic",
        "Be able to solve standard problems related to the topic",
        "Identify common mistakes and avoid them"
    ],
    "topics_to_revise": [
        "Basic definitions and formulas",
        "Previous chapter fundamentals",
        "Solved examples from textbook",
        "Important derivations"
    ],
    "explanation": "This topic builds on foundational concepts you may need to revisit. "
                   "Focus on understanding the 'why' behind each formula, not just memorizing it. "
                   "Work through solved examples step by step before attempting new problems. "
                   "Consistent daily practice will help strengthen this area.",
    "practice_activities": [
        {"problem": "Review 2-3 solved examples from your textbook on this topic.", "expected_answer": "Self-check against textbook solutions"},
        {"problem": "Attempt 5 previous year questions on this topic.", "expected_answer": "Compare with answer key and note mistakes"}
    ],
    "concept_gap_rationale": "Your score in this area was below the target threshold, indicating a need to revisit fundamentals before attempting advanced problems."
}


@app.route("/api/remedial-recommendation", methods=["POST"])
@login_required
def remedial_recommendation():
    data = request.get_json(silent=True) or {}
    subject = data.get("subject", "")
    topic = data.get("topic", "")
    score = data.get("score", 0)
    exam_type = data.get("exam_type", "")
    classification = classify_score(score)

    prompt = f"""Generate a structured remedial recommendation for the topic "{topic}" in {subject} for a {exam_type} student who scored {score}% (classified as {classification}).

The response should include these 5 sections in JSON format:
1. "learning_objectives": list of 2-3 specific objectives
2. "topics_to_revise": list of 3-4 foundational topics to review
3. "explanation": a simple, clear explanation of the core concept (3-4 sentences)
4. "practice_activities": list of 2 practice problems with expected answers (each item should be an object with "problem" and "expected_answer" keys)
5. "concept_gap_rationale": brief explanation of why this was recommended based on their score

Return ONLY valid JSON, no markdown formatting, no extra commentary before or after the JSON."""

    try:
        raw = call_gemini(prompt)
        try:
            parsed = extract_json(raw)
        except Exception as parse_err:
            print(f"[REMEDIAL PARSE ERROR] {parse_err}")
            print(f"[REMEDIAL RAW RESPONSE] {raw[:500]}")
            raise

        # Basic validation: make sure all 5 expected sections are present
        required_keys = ["learning_objectives", "topics_to_revise", "explanation",
                          "practice_activities", "concept_gap_rationale"]
        if not all(k in parsed for k in required_keys):
            raise ValueError(f"AI response missing expected sections: {parsed.keys()}")

        return jsonify(parsed), 200
    except Exception as e:
        print(f"[REMEDIAL ERROR] {type(e).__name__}: {e}")
        app.logger.warning(f"Gemini remedial recommendation failed: {e}")
        fallback = dict(FALLBACK_RECOMMENDATION)
        fallback["explanation"] = (
            f"AI service unavailable right now. Here's general guidance for {topic} ({subject}): " + fallback["explanation"]
        )
        return jsonify(fallback), 200


# -----------------------------------------------------------------
# [BASE PAPER STEP 1 + 2: Student Assessment & Dynamic Question
#  Selection]
# AI-generated practice questions (Gemini) with fallback question bank.
# Difficulty adapts based on previous_percentage (Step 2: correct ->
# harder questions next time, wrong -> easier questions next time).
# -----------------------------------------------------------------
FALLBACK_QUESTION_BANK = {
    "Physics": [
        {"question": "Unit of force?", "options": ["Newton", "Joule", "Watt", "Pascal"], "answer": "Newton", "difficulty": "easy"},
        {"question": "Speed of light?", "options": ["3x10^8 m/s", "3x10^6 m/s", "3x10^5 m/s", "3x10^7 m/s"], "answer": "3x10^8 m/s", "difficulty": "easy"},
        {"question": "Acceleration due to gravity?", "options": ["9.8 m/s^2", "10 m/s^2", "8 m/s^2", "9 m/s"], "answer": "9.8 m/s^2", "difficulty": "easy"},
        {"question": "SI unit of work?", "options": ["Joule", "Newton", "Watt", "Pascal"], "answer": "Joule", "difficulty": "easy"},
        {"question": "Which law states F = ma?", "options": ["Newton's Second Law", "Newton's First Law", "Newton's Third Law", "Hooke's Law"], "answer": "Newton's Second Law", "difficulty": "easy"},
        {"question": "Unit of electric current?", "options": ["Ampere", "Volt", "Ohm", "Watt"], "answer": "Ampere", "difficulty": "easy"},
        {"question": "What type of lens is used to correct myopia?", "options": ["Concave lens", "Convex lens", "Cylindrical lens", "Bifocal lens"], "answer": "Concave lens", "difficulty": "medium"},
        {"question": "SI unit of frequency?", "options": ["Hertz", "Joule", "Newton", "Pascal"], "answer": "Hertz", "difficulty": "easy"},
        {"question": "Which particle has no charge?", "options": ["Neutron", "Proton", "Electron", "Positron"], "answer": "Neutron", "difficulty": "easy"},
        {"question": "Formula for kinetic energy?", "options": ["1/2 mv^2", "mgh", "mv", "m/v"], "answer": "1/2 mv^2", "difficulty": "medium"}
    ],
    "Chemistry": [
        {"question": "Which is a chemical element?", "options": ["Water", "Oxygen", "Salt", "Sugar"], "answer": "Oxygen", "difficulty": "easy"},
        {"question": "Atomic number of Hydrogen?", "options": ["1", "2", "3", "4"], "answer": "1", "difficulty": "easy"},
        {"question": "HCl is what type of acid?", "options": ["Strong", "Weak", "Moderate", "None"], "answer": "Strong", "difficulty": "medium"},
        {"question": "What is the pH of a neutral solution?", "options": ["7", "0", "14", "1"], "answer": "7", "difficulty": "easy"},
        {"question": "Which gas is released during photosynthesis?", "options": ["Oxygen", "Carbon dioxide", "Nitrogen", "Hydrogen"], "answer": "Oxygen", "difficulty": "easy"},
        {"question": "What is the chemical formula of table salt?", "options": ["NaCl", "KCl", "CaCl2", "NaOH"], "answer": "NaCl", "difficulty": "easy"},
        {"question": "Which element has the symbol 'Fe'?", "options": ["Iron", "Fluorine", "Francium", "Iodine"], "answer": "Iron", "difficulty": "easy"},
        {"question": "What type of bond is formed by sharing electrons?", "options": ["Covalent bond", "Ionic bond", "Metallic bond", "Hydrogen bond"], "answer": "Covalent bond", "difficulty": "medium"},
        {"question": "Which is the most abundant gas in Earth's atmosphere?", "options": ["Nitrogen", "Oxygen", "Carbon dioxide", "Argon"], "answer": "Nitrogen", "difficulty": "medium"},
        {"question": "What is the atomic number of Carbon?", "options": ["6", "12", "8", "14"], "answer": "6", "difficulty": "easy"}
    ],
    "Mathematics": [
        {"question": "Derivative of x^2?", "options": ["2x", "x", "x^2", "1"], "answer": "2x", "difficulty": "easy"},
        {"question": "Integral of 1/x dx?", "options": ["ln|x|", "x", "x^2", "1/x"], "answer": "ln|x|", "difficulty": "medium"},
        {"question": "Value of sin(90 deg)?", "options": ["1", "0", "0.5", "-1"], "answer": "1", "difficulty": "easy"},
        {"question": "What is the value of pi (approx)?", "options": ["3.14", "2.71", "1.41", "1.73"], "answer": "3.14", "difficulty": "easy"},
        {"question": "Derivative of sin(x)?", "options": ["cos(x)", "-cos(x)", "tan(x)", "-sin(x)"], "answer": "cos(x)", "difficulty": "medium"},
        {"question": "What is the slope formula between two points?", "options": ["(y2-y1)/(x2-x1)", "(x2-x1)/(y2-y1)", "x2+y2", "x1*y1"], "answer": "(y2-y1)/(x2-x1)", "difficulty": "medium"},
        {"question": "Sum of angles in a triangle?", "options": ["180 degrees", "90 degrees", "360 degrees", "270 degrees"], "answer": "180 degrees", "difficulty": "easy"},
        {"question": "Value of log(1)?", "options": ["0", "1", "10", "undefined"], "answer": "0", "difficulty": "medium"},
        {"question": "What is the formula for area of a circle?", "options": ["pi*r^2", "2*pi*r", "pi*d", "r^2"], "answer": "pi*r^2", "difficulty": "easy"},
        {"question": "Number of roots of a quadratic equation?", "options": ["2", "1", "3", "0"], "answer": "2", "difficulty": "easy"}
    ],
    "Botany": [
        {"question": "Which part of plant performs photosynthesis?", "options": ["Root", "Leaf", "Stem", "Flower"], "answer": "Leaf", "difficulty": "easy"},
        {"question": "What pigment gives leaves their green color?", "options": ["Chlorophyll", "Carotene", "Anthocyanin", "Xanthophyll"], "answer": "Chlorophyll", "difficulty": "easy"},
        {"question": "Which part of the plant absorbs water?", "options": ["Root hairs", "Leaf", "Flower", "Stem"], "answer": "Root hairs", "difficulty": "easy"},
        {"question": "What is the male reproductive part of a flower?", "options": ["Stamen", "Pistil", "Sepal", "Petal"], "answer": "Stamen", "difficulty": "medium"},
        {"question": "Which process releases water vapor from leaves?", "options": ["Transpiration", "Respiration", "Photosynthesis", "Germination"], "answer": "Transpiration", "difficulty": "medium"},
        {"question": "What is the basic unit of classification in plants?", "options": ["Species", "Genus", "Family", "Order"], "answer": "Species", "difficulty": "medium"},
        {"question": "Which tissue transports water in plants?", "options": ["Xylem", "Phloem", "Cortex", "Epidermis"], "answer": "Xylem", "difficulty": "medium"},
        {"question": "What gas do plants absorb during photosynthesis?", "options": ["Carbon dioxide", "Oxygen", "Nitrogen", "Hydrogen"], "answer": "Carbon dioxide", "difficulty": "easy"},
        {"question": "Which plant hormone promotes cell division?", "options": ["Cytokinin", "Auxin", "Gibberellin", "Ethylene"], "answer": "Cytokinin", "difficulty": "hard"},
        {"question": "What is the female reproductive part of a flower called?", "options": ["Pistil", "Stamen", "Anther", "Filament"], "answer": "Pistil", "difficulty": "medium"}
    ],
    "Zoology": [
        {"question": "Humans have how many heart chambers?", "options": ["2", "3", "4", "5"], "answer": "4", "difficulty": "easy"},
        {"question": "Which organ pumps blood in the human body?", "options": ["Heart", "Lungs", "Liver", "Kidney"], "answer": "Heart", "difficulty": "easy"},
        {"question": "Which blood cells help fight infection?", "options": ["White blood cells", "Red blood cells", "Platelets", "Plasma"], "answer": "White blood cells", "difficulty": "easy"},
        {"question": "What is the basic unit of the nervous system?", "options": ["Neuron", "Nephron", "Axon", "Synapse"], "answer": "Neuron", "difficulty": "medium"},
        {"question": "Which organ filters blood to form urine?", "options": ["Kidney", "Liver", "Heart", "Lungs"], "answer": "Kidney", "difficulty": "easy"},
        {"question": "What is the powerhouse of the cell?", "options": ["Mitochondria", "Nucleus", "Ribosome", "Golgi body"], "answer": "Mitochondria", "difficulty": "easy"},
        {"question": "Which hormone regulates blood sugar?", "options": ["Insulin", "Thyroxine", "Adrenaline", "Estrogen"], "answer": "Insulin", "difficulty": "medium"},
        {"question": "How many pairs of chromosomes do humans have?", "options": ["23", "22", "24", "46"], "answer": "23", "difficulty": "medium"},
        {"question": "Which gas is exchanged in the lungs during respiration?", "options": ["Oxygen and Carbon dioxide", "Nitrogen and Oxygen", "Hydrogen and Oxygen", "Carbon monoxide and Oxygen"], "answer": "Oxygen and Carbon dioxide", "difficulty": "easy"},
        {"question": "What is the process of cell division called?", "options": ["Mitosis", "Meiosis only", "Osmosis", "Diffusion"], "answer": "Mitosis", "difficulty": "medium"}
    ]
}


@app.route("/api/generate-questions", methods=["POST"])
def generate_questions():
    data = request.get_json(silent=True) or {}
    exam_type = data.get("exam_type", "")
    subject = data.get("subject", "")
    topic = data.get("topic", "")
    count = int(data.get("count", 10))
    # Optional: previous score % for this subject, used to adapt difficulty
    previous_percentage = data.get("previous_percentage")

    difficulty_hint = ""
    if previous_percentage is not None:
        try:
            pct = float(previous_percentage)
            if pct < 50:
                difficulty_hint = ("The student scored below 50% on this topic last time, indicating they are "
                                    "struggling with fundamentals. Make the questions mostly easy to medium "
                                    "difficulty, focused on core concepts and common misconceptions.")
            elif pct <= 70:
                difficulty_hint = ("The student scored between 50-70% on this topic last time. Make the "
                                    "questions a mix of medium difficulty, reinforcing concepts they may have "
                                    "partially understood.")
            else:
                difficulty_hint = ("The student scored above 70% on this topic last time and is proficient. "
                                    "Make the questions medium to hard difficulty to challenge them further.")
        except (ValueError, TypeError):
            pass

    # Random seed phrase forces Gemini to generate a fresh, different set of
    # questions each time (instead of returning the same ones repeatedly).
    import random
    variation_seed = random.randint(1, 100000)

    prompt = f"""Generate {count} NEW and UNIQUE multiple-choice questions (variation set #{variation_seed}) for {exam_type} level students on the topic "{topic}" in {subject}.
{difficulty_hint}
Each question should have 4 options with exactly one correct answer.
Make sure these questions are different from commonly repeated textbook examples — vary the numbers, scenarios, and phrasing.
Return ONLY valid JSON in this format:
[
  {{
    "question": "...",
    "options": ["A", "B", "C", "D"],
    "answer": "correct option text",
    "difficulty": "easy/medium/hard"
  }}
]"""

    try:
        raw = call_gemini(prompt)
        try:
            questions = extract_json(raw)
        except Exception as parse_err:
            print(f"[QUESTIONS PARSE ERROR] {parse_err}")
            print(f"[QUESTIONS RAW RESPONSE] {raw[:500]}")
            raise
        if not isinstance(questions, list) or not questions:
            raise ValueError("Invalid question format from AI.")
        return jsonify({"questions": questions, "source": "ai"}), 200
    except Exception as e:
        print(f"[QUESTIONS ERROR] {type(e).__name__}: {e}")
        app.logger.warning(f"Gemini question generation failed: {e}")
        # Fallback: shuffle the hardcoded bank so it's not always identical
        fallback = FALLBACK_QUESTION_BANK.get(subject, [])
        shuffled = fallback[:]
        random.shuffle(shuffled)
        return jsonify({"questions": shuffled[:count], "source": "fallback"}), 200



# -----------------------------------------------------------------
# AI Chatbot (Gemini)
# -----------------------------------------------------------------
@app.route("/api/chatbot", methods=["POST"])
def chatbot():
    data = request.get_json(silent=True) or {}
    exam_type = data.get("exam_type", "your entrance exam")
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "message is required."}), 400

    prompt = f"""You are a helpful AI tutor for a student preparing for {exam_type}. The student asks: "{message}"
Give a clear, concise, encouraging answer (max 100 words) appropriate for an entrance exam aspirant."""

    try:
        raw = call_gemini(prompt)
        return jsonify({"response": raw.strip()}), 200
    except Exception as e:
        print(f"[CHATBOT ERROR] {type(e).__name__}: {e}")
        app.logger.warning(f"Gemini chatbot failed: {e}")
        return jsonify({"response": "AI is busy right now, please try again in a moment. "
                                     "Meanwhile, try revising your weak topics using the study plan above."}), 200


# -----------------------------------------------------------------
# Admin Stats Dashboard
# -----------------------------------------------------------------
# Simple password-protected page showing usage numbers: total users,
# total tests taken, breakdown by exam type, average scores, and
# recent signups. Password is set via the ADMIN_PASSWORD environment
# variable (set this in Render's dashboard under Environment).
# -----------------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")


@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    provided_password = request.args.get("password", "")
    if provided_password != ADMIN_PASSWORD:
        return """
            <html><body style="font-family:sans-serif; max-width:400px; margin:80px auto; text-align:center;">
                <h2>Admin Stats</h2>
                <form method="get">
                    <input type="password" name="password" placeholder="Enter admin password"
                           style="padding:10px; width:100%; box-sizing:border-box; margin-bottom:10px;">
                    <button type="submit" style="padding:10px 20px; width:100%;">View Stats</button>
                </form>
            </body></html>
        """, 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM users")
    total_users = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as total FROM test_results")
    total_tests = cur.fetchone()["total"]

    cur.execute("""
        SELECT exam_type, COUNT(*) as count
        FROM test_results
        GROUP BY exam_type
        ORDER BY count DESC
    """)
    exam_breakdown = cur.fetchall()

    cur.execute("""
        SELECT subject, AVG(CAST(score AS FLOAT) / total_questions * 100) as avg_pct
        FROM test_results
        GROUP BY subject
        ORDER BY avg_pct ASC
    """)
    subject_avg = cur.fetchall()

    cur.execute("""
        SELECT name, email, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent_signups = cur.fetchall()

    cur.execute("""
        SELECT u.name, t.exam_type, t.subject, t.score, t.total_questions, t.test_date
        FROM test_results t
        JOIN users u ON u.id = t.user_id
        ORDER BY t.test_date DESC
        LIMIT 15
    """)
    recent_tests = cur.fetchall()

    conn.close()

    def rows_html(rows, columns):
        html = "<tr>" + "".join(f"<th>{c}</th>" for c in columns) + "</tr>"
        for row in rows:
            html += "<tr>" + "".join(f"<td>{row[c]}</td>" for c in columns) + "</tr>"
        return html

    exam_rows = "".join(
        f"<tr><td>{r['exam_type']}</td><td>{r['count']}</td></tr>" for r in exam_breakdown
    )
    subject_rows = "".join(
        f"<tr><td>{r['subject']}</td><td>{round(r['avg_pct'], 1)}%</td></tr>" for r in subject_avg
    )
    signup_rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r['email']}</td><td>{r['created_at'][:10]}</td></tr>"
        for r in recent_signups
    )
    test_rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r['exam_type']}</td><td>{r['subject']}</td>"
        f"<td>{r['score']}/{r['total_questions']}</td><td>{r['test_date'][:10]}</td></tr>"
        for r in recent_tests
    )

    html = f"""
    <html>
    <head>
        <title>Admin Stats — Entrance Exam Coach</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }}
            h1 {{ color: #4169E1; }}
            h2 {{ margin-top: 40px; color: #4169E1; border-bottom: 2px solid #6495ED; padding-bottom: 5px; }}
            .stat-cards {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
            .stat-card {{ background: #f0f8ff; padding: 20px 30px; border-radius: 12px; text-align: center; flex: 1; min-width: 150px; }}
            .stat-card .number {{ font-size: 32px; font-weight: bold; color: #4169E1; }}
            .stat-card .label {{ font-size: 14px; color: #666; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ddd; }}
            th {{ background: #6495ED; color: white; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
        </style>
    </head>
    <body>
        <h1>Entrance Exam Coach — Admin Stats</h1>

        <div class="stat-cards">
            <div class="stat-card"><div class="number">{total_users}</div><div class="label">Total Users</div></div>
            <div class="stat-card"><div class="number">{total_tests}</div><div class="label">Total Tests Taken</div></div>
        </div>

        <h2>Tests by Exam Type</h2>
        <table><tr><th>Exam Type</th><th>Tests Taken</th></tr>{exam_rows}</table>

        <h2>Average Score % by Subject (lower = needs more attention)</h2>
        <table><tr><th>Subject</th><th>Average Score %</th></tr>{subject_rows}</table>

        <h2>Recent Signups</h2>
        <table><tr><th>Name</th><th>Email</th><th>Signed Up</th></tr>{signup_rows}</table>

        <h2>Recent Test Attempts</h2>
        <table><tr><th>Student</th><th>Exam</th><th>Subject</th><th>Score</th><th>Date</th></tr>{test_rows}</table>

        <p style="margin-top:40px; color:#999; font-size:12px;">Refresh the page to see updated numbers.</p>
    </body>
    </html>
    """
    return html


# -----------------------------------------------------------------
# Serve frontend files (so the whole site can run from one Flask server)
# -----------------------------------------------------------------
@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def serve_static_file(filename):
    return send_from_directory(BASE_DIR, filename)


# -----------------------------------------------------------------
# Database initialization
# -----------------------------------------------------------------
# IMPORTANT: this must run at MODULE level (not inside
# `if __name__ == "__main__"`), because production servers like
# gunicorn import this file as a module and never execute the
# __main__ block. Without this, the database tables would never get
# created when deployed on Render/Railway/etc.
init_db()
if dbmod.USING_POSTGRES:
    print("Database: PostgreSQL (production)")
else:
    print("Database initialized at:", dbmod.SQLITE_PATH)
print("Groq API available:", GROQ_AVAILABLE)
print("Groq model in use:", GROQ_MODEL)


# -----------------------------------------------------------------
# Main (used only for local development: `python app.py`)
# -----------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", debug=debug_mode, port=port)
