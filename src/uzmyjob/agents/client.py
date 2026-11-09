"""Gemini API client singleton."""
import os

from google import genai

from uzmyjob.config import settings

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Singleton Gemini client."""
    global _client
    if _client is None:
        api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        _client = genai.Client(api_key=api_key)
    return _client

