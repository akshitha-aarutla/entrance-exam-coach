"""
Run this script to find out which Gemini models your API key can use.

Usage:
    python list_models.py

This will print a list of models and whether they support generateContent.
Copy the name of a model that supports generateContent (e.g. "models/gemini-2.0-flash")
and tell Claude — we'll hardcode that exact name into app.py.
"""

import config
import google.generativeai as genai

genai.configure(api_key=config.GEMINI_API_KEY)

print("Models available for your API key:\n")

for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"  {m.name}")

print("\nDone. Copy one of the names above (the part after 'models/' or the full string)")
print("and send it back — we'll use that exact model name in app.py.")
