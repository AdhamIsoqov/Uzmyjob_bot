"""Gemini API client singleton."""
import os

from google import genai

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Singleton Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client
