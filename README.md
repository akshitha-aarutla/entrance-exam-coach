# Entrance Exam Coach — Setup & Run Guide (Windows)

This guide walks you through setting up and running the complete project
(Flask backend + frontend) on a Windows PC, step by step.

---

## 1. Folder Structure

Put all files in **one folder**, like this:

```
EntranceExamCoach/
│
├── app.py                  <- Main Flask backend
├── config.py                <- Put your Gemini API key here
├── weightage_data.py        <- Topic weightage data (already filled in)
├── requirements.txt         <- Python dependencies
├── database.db               <- Auto-created when you first run app.py
│
├── style.css                 <- Shared stylesheet
├── index.html
├── login.html
├── signup.html
├── exam.html
├── mocktest.html
└── analysis.html
```

All the `.html` files and `style.css` must be in the **same folder** as
`app.py` (the project root). Flask is configured to serve them directly.

> Note: The original `index.html` references images like
> `/frontend/Dog Education Logo.jpg`. If you have these image files,
> create a `frontend` folder inside the project root and place the images
> there. If you don't have them, the page will still work — the images
> will just show as broken icons.

---

## 2. Install Python

Make sure Python 3.10+ is installed. Check by opening Command Prompt and running:

```
python --version
```

If not installed, download it from https://www.python.org/downloads/
(During installation, check "Add Python to PATH").

---

## 3. Install Dependencies

1. Open Command Prompt.
2. Navigate to the project folder:
   ```
   cd path\to\EntranceExamCoach
   ```
3. (Recommended) Create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
4. Install required packages:
   ```
   pip install -r requirements.txt
   ```

---

## 4. Add Your Gemini API Key

1. Get a free Gemini API key from: https://aistudio.google.com/app/apikey
2. Open `config.py` in a text editor (e.g., Notepad).
3. Replace the placeholder with your actual key:
   ```python
   GEMINI_API_KEY = "your-actual-api-key-here"
   ```
4. Save the file.

> If you skip this step, the app will still run — AI features (chatbot,
> remedial recommendations, AI-generated questions) will automatically
> fall back to pre-written generic content instead of crashing.

---

## 5. Run the Flask Server

In the same Command Prompt (with venv activated, if used):

```
python app.py
```

You should see output like:
```
Database initialized at: ...\database.db
Gemini API available: True
 * Running on http://127.0.0.1:5000
```

The first run automatically creates `database.db` with all required tables.

---

## 6. Open the Website

Open your web browser and go to:

```
http://127.0.0.1:5000
```

This loads `index.html` directly from the Flask server (no need to
double-click the HTML files — opening them directly with `file://` will
NOT work because the API calls require the Flask server).

---

## 7. Using the App

1. **Signup** — Create an account (name, email, password ≥ 8 chars).
2. **Login** — Log in with your credentials.
3. **Select Exam** — Choose your target exam (JEE Main, JEE Advanced,
   EAMCET, EAPCET, NEET), select subjects, and pick your exam date.
4. **Mock Test** — Answer the questions (AI-generated if Gemini key is
   configured, otherwise from the built-in question bank).
5. **Analysis** — View:
   - Subject-wise score and classification (Needs Improvement /
     Intermediate / Proficient)
   - A weightage-based, day-by-day study timetable based on your exam date
   - "Get AI Recommendation" buttons for weak subjects
   - Progress chart across multiple tests
   - AI Doubt Bot chat

---

## 8. Troubleshooting

- **"Could not connect to the server"** — Make sure `python app.py` is
  still running in Command Prompt, and that you're accessing the site via
  `http://127.0.0.1:5000` (not by double-clicking HTML files).
- **AI features show fallback/generic text** — Check that your Gemini API
  key in `config.py` is correct and that you have internet access.
- **"Email already registered"** — Use the login page instead, or sign up
  with a different email.
- **Port already in use** — Close any other program using port 5000, or
  change the port in the last line of `app.py`
  (`app.run(debug=True, port=5000)`) to another number like `5001`, then
  visit `http://127.0.0.1:5001` instead.

---

## 9. Database

`database.db` is a SQLite file created automatically. It contains:

- `users` — registered accounts (passwords stored as bcrypt hashes)
- `test_results` — every mock test result per user
- `timetables` — every generated study timetable per user

You can inspect it with any SQLite browser (e.g., "DB Browser for SQLite")
if you want to show the database during evaluation.

---

## 10. For Evaluation / Demo

- Mention that passwords are hashed with **bcrypt** (never stored in plain text).
- Mention the **Threshold (50%) / Target (70%)** classification is based on
  an Outcome-Based Education (OBE) framework.
- Mention the **weightage-based timetable**: topics are tagged
  high/medium/low importance per exam in `weightage_data.py`, and the
  timetable logic changes based on days left (`<15`, `15-45`, `>45`).
- Mention **Gemini AI** powers: practice question generation, remedial
  recommendations, and the doubt-solving chatbot — all with graceful
  fallbacks if the API is unavailable.

---

## 11. Mapping to the Base Paper (for viva)

This project is modeled on:

**DK-PRACTICE: An Intelligent Educational Platform for Personalized
Learning Content Recommendations Based on Students' Knowledge State**
(Delianidi, Diamantaras, Moras, Sidiropoulos — 2024)

| Base Paper Step | Base Paper Method | This Project | Where in Code |
|---|---|---|---|
| 1. Student Assessment | Adaptive question-answer test | Mock Test | `mocktest.html`, `/api/generate-questions` |
| 2. Dynamic Question Selection | Correct → harder, Wrong → easier | Difficulty adapts via `previous_percentage` | `/api/generate-questions` |
| 3. Knowledge Tracing | PB-BoW / Feedforward NN predicts knowledge level | Threshold (50%) / Target (70%) classification: Needs Improvement / Intermediate / Proficient (OBE framework) | `classify_score()`, `/api/analyze-results` |
| 4. Weak Topic Detection | Identify knowledge gaps | Weak subjects + weak topics stored per test | `/api/analyze-results`, `test_results` table |
| 5. Content Recommendation | Recommend learning materials | AI Remedial Recommendation (5-part structured output via Gemini) | `/api/remedial-recommendation` |
| 6. Pre-test / Post-test | Measure improvement over time | "Retake Test (Adaptive)" + Progress Chart; `/api/last-results` feeds next test | `/api/last-results`, `analysis.html` progress chart |
| (Extra) Adaptive Learning | — | Personalized weightage-based study timetable | `/api/generate-timetable`, `weightage_data.py` |

**Key difference from the base paper**: the base paper trains a custom
Feedforward Neural Network + PB-BoW Knowledge Tracing model on a student
interaction dataset. This project substitutes that trained ML model with
the **Google Gemini LLM API** for content recommendation and adaptive
question generation, and uses a simple **rule-based Threshold/Target
classifier** for knowledge tracing (since collecting a large interaction
dataset and training a custom KT model was out of scope for a 2-day
mini-project). This is a reasonable and explainable substitution: Gemini
performs the "intelligence" role that the trained model plays in the
paper, while the OBE-based classification gives a transparent,
rule-based proxy for knowledge state prediction.
