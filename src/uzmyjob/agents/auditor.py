"""Code Auditor Agent — gemini-4-argon bilan security/PII tekshirish."""
import json

from uzmyjob.agents.client import get_client
from uzmyjob.utils.logger import log

SYSTEM_INSTRUCTION = """Sen kodni audit qiluvchi xavfsizlik agentisan.
Berilgan Python kodni quyidagi mezonlar bo'yicha tekshir:
1. PII ma'lumotlar (telefon, email, CV matni) logga tushayaptimi?
2. Secrets (token, parol) kod ichida hardcode qilinganmi?
3. SQL injection xavfi bormi?
4. Rate limit buzilganmi (1 rps dan oshganmi)?
5. ToS buzilishi bormi?

Javob JSON formatida:
{
  "issues": [
    {"severity": "critical|warning|info", "line": 42, "message": "..."}
  ],
  "passed": true|false
}"""


async def audit_code(code: str, filename: str = "unknown.py") -> dict:
    """
    Kodni security/PII/ToS mezonlari bo'yicha tekshiradi.
    Returns: {"issues": [...], "passed": bool}
    """
    client = get_client()
    prompt = f"Fayl: {filename}\n\n```python\n{code}\n```"
    try:
        interaction = client.interactions.create(
            model="gemini-4-argon",
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            store=False,
        )
        result = json.loads(interaction.output_text or '{"issues":[],"passed":true}')
        log.info("audit_complete", filename=filename, passed=result.get("passed"))
        return result
    except Exception as e:
        log.error("auditor_error", error=str(e))
        return {"issues": [], "passed": False, "error": str(e)}
