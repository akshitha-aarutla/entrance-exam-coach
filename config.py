# config.py
#
# For LOCAL development: edit the values below directly.
#
# For DEPLOYMENT (Render, Railway, etc.): set these as environment
# variables in your hosting platform's dashboard instead — they will
# automatically override the values below, and your real API key
# never needs to be committed to GitHub.

import os

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "PASTE_YOUR_GROQ_API_KEY_HERE")

# Groq model to use. llama-3.3-70b-versatile is a good free, fast default.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Flask secret key (used for sessions). Change to any random string locally;
# on Render this is auto-generated via render.yaml.
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-string")
