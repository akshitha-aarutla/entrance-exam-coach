# Deploying Entrance Exam Coach (Live, Free, Accessible from Any Device)

This guide gets your app running on the public internet — accessible
from any laptop or phone — using **Render.com's free tier**.

What you'll have at the end: a URL like
`https://entrance-exam-coach.onrender.com` that works from anywhere,
backed by a real PostgreSQL database (so data persists, unlike
SQLite on most free hosts).

---

## Why Render + PostgreSQL?

- **Render** has a genuinely free tier for both a web app AND a database
  (no credit card required for the free tier)
- Your Flask app already auto-detects: if a `DATABASE_URL` environment
  variable exists, it uses PostgreSQL; otherwise it uses SQLite. This
  means **the same code runs locally (SQLite) and in production
  (PostgreSQL) with zero changes**
- Free-tier web services on Render "spin down" after 15 minutes of
  inactivity and take ~30-60 seconds to wake up on the next request —
  this is normal for free hosting and fine for a student project

---

## Step 1 — Push your project to GitHub

Render deploys directly from a GitHub repository.

1. Go to https://github.com and create a new repository (e.g. `entrance-exam-coach`)
2. On your laptop, open Command Prompt in your project folder and run:
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/entrance-exam-coach.git
   git push -u origin main
   ```
   (If `git` isn't installed, download it from https://git-scm.com/downloads first)

3. **IMPORTANT**: make sure `config.py` does NOT contain your real Groq
   API key when you push — your key should only exist as an environment
   variable on Render (set in Step 3), never committed to GitHub. Check
   that `config.py` uses `os.environ.get(...)` (it already does in this
   project) so the actual key never needs to be in the file.

---

## Step 2 — Create a Render account

1. Go to https://render.com
2. Sign up (GitHub login is easiest — it lets Render see your repos)

---

## Step 3 — Deploy using the Blueprint (render.yaml)

This project already includes a `render.yaml` file that tells Render
exactly how to set everything up (web service + free Postgres database)
in one step.

1. In the Render dashboard, click **New +** then **Blueprint**
2. Connect your GitHub account if prompted, then select your
   `entrance-exam-coach` repository
3. Render will detect `render.yaml` and show you a preview: one web
   service (`entrance-exam-coach`) and one database
   (`entrance-exam-coach-db`)
4. Click **Apply**
5. Render will ask you to fill in the `GROQ_API_KEY` value (since
   `render.yaml` marks it `sync: false` for security) — paste your real
   Groq key here
6. Click **Create** — Render will now:
   - Provision a free PostgreSQL database
   - Install your Python dependencies (`pip install -r requirements.txt`)
   - Start your app with `gunicorn app:app`
   - Automatically connect the database via the `DATABASE_URL`
     environment variable

This takes a few minutes the first time.

---

## Step 4 — Get your live URL

Once deployment finishes (status shows "Live" in green), Render shows
your URL at the top of the service page, e.g.:

```
https://entrance-exam-coach.onrender.com
```

Open this on your phone, a friend's laptop, anywhere — it's now public.

---

## Step 5 — Verify everything works

1. Visit the URL — the homepage should load
2. Sign up for a new account
3. Take a mock test
4. Check the AI features (questions, chatbot, remedial recommendations)
   work — if `GROQ_API_KEY` was set correctly in Step 3, AI-generated
   content will appear; check server logs in Render's dashboard if
   anything seems off

---

## Updating your app later

Whenever you push new commits to GitHub's `main` branch, Render
automatically redeploys:
```
git add .
git commit -m "Describe your change"
git push
```
Render picks this up within a minute or two and redeploys automatically.

---

## Common Issues

**"Application Error" or blank page on first visit**
The free tier spins down when idle — the first request after
inactivity can take 30-60 seconds while it wakes up. Just wait and
refresh.

**Database tables missing / signup fails**
Check Render's dashboard, your web service, then the Logs tab. You
should see "Database: PostgreSQL (production)" in the startup logs.
If you see SQLite-related messages instead, the DATABASE_URL
environment variable isn't linked correctly — check the Environment
tab on your web service and confirm DATABASE_URL is present (it should
be auto-filled by the Blueprint from the database service).

**AI features always show fallback content**
Check the Environment tab and confirm GROQ_API_KEY has your real key
(not the placeholder). You can edit environment variables anytime from
the Render dashboard without redeploying your code.

**Changes not showing up after a push**
Check the Events tab on your Render service to confirm a new deploy
was triggered. If not, verify you pushed to the branch Render is
watching (default: main).

---

## Cost

Both the free web service and free Postgres database have no cost and
no credit card requirement at signup. Render's free Postgres databases
do expire after 90 days of the database (not the app) being idle — if
that happens, you'd need to create a fresh one and the old data would
be lost. For a long-lived class project, keep this in mind; for
serious production use later, a paid tier removes this limitation.

---

## Alternative: Railway.app

If Render doesn't work for you, Railway.app is a very similar
free-tier alternative with the same general flow (GitHub auto-deploy,
free Postgres add-on). The same app.py/db.py setup works there too —
Railway also sets a DATABASE_URL environment variable automatically
when you add a Postgres plugin, and you'd set GROQ_API_KEY and
SECRET_KEY as environment variables in their dashboard, with start
command "gunicorn app:app".
