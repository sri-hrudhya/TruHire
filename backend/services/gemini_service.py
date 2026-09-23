"""
Gemini Service (Optional integration).
Keep commented out / optional as specified in architecture.
"""
import os
from typing import Optional

# Optional Google Gemini configuration
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# if GEMINI_API_KEY:
#     import google.generativeai as genai
#     genai.configure(api_key=GEMINI_API_KEY)


def call_gemini(prompt: str, model_name: str = "gemini-1.5-flash") -> Optional[str]:
    """
    Optional Gemini completion fallback.
    Returns None if not configured.
    """
    # if GEMINI_API_KEY:
    #     try:
    #         model = genai.GenerativeModel(model_name)
    #         response = model.generate_content(prompt)
    #         return response.text
    #     except Exception as e:
    #         print(f"Gemini call failed: {e}")
    #         return None
    return None
