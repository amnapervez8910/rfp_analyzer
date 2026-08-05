import os
import google.generativeai as genai


def configure_gemini():
    """Configure Gemini and return the original model tiers."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return {
        "fast": genai.GenerativeModel("models/gemini-3.6-flash"),
        "pro": genai.GenerativeModel("models/gemini-3.6-flash"),
        "lite": genai.GenerativeModel("models/gemini-3.5-flash-lite"),
    }
