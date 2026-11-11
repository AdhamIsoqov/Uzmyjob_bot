"""Gemini API client singleton va umumiy LLM yordamchilari."""
import asyncio
import os

from google import genai
from google.genai import types

from uzmyjob.config import settings

_client: genai.Client | None = None
_llm_semaphore: asyncio.Semaphore | None = None


def get_client() -> genai.Client:
    """Singleton Gemini client."""
    global _client
    if _client is None:
        api_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        _client = genai.Client(api_key=api_key)
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(5)
    return _llm_semaphore


def strip_markdown_fences(raw_text: str) -> str:
    """LLM javobidagi ```json ... ``` markdown bloklarini tozalaydi."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1].removeprefix("json")
    return text.strip()


async def generate_gemini_text(
    prompt: str,
    system_instruction: str,
    model: str = "gemini-2.5-flash",
    response_mime_type: str | None = None,
    timeout: float = 12.0,
    client: genai.Client | None = None,
) -> str:
    """Gemini modeliga bir vaqtda so'rovlar sonini cheklagan holda murojaat qiladi."""
    active_client = client or get_client()
    config_kwargs: dict = {"system_instruction": system_instruction}
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type

    config = types.GenerateContentConfig(**config_kwargs)

    async with _get_semaphore():
        response = await asyncio.wait_for(
            asyncio.to_thread(
                active_client.models.generate_content,
                model=model,
                contents=prompt,
                config=config,
            ),
            timeout=timeout,
        )

    if hasattr(response, "text") and isinstance(response.text, str):
        return response.text
    if hasattr(response, "output_text") and isinstance(response.output_text, str):
        return response.output_text
    return ""
