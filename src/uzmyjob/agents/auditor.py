"""Code Auditor Agent — gemini-2.5-flash bilan security/PII tekshirish."""
import asyncio
import json
import sys
from pathlib import Path

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
    try:
        client = get_client()
        prompt = f"Fayl: {filename}\n\n```python\n{code}\n```"
        interaction = await asyncio.wait_for(
            asyncio.to_thread(
                client.interactions.create,
                model="gemini-2.5-flash",
                system_instruction=SYSTEM_INSTRUCTION,
                input=prompt,
                store=False,
            ),
            timeout=15.0,
        )
        result = json.loads(interaction.output_text or '{"issues":[],"passed":true}')
        log.info("audit_complete", filename=filename, passed=result.get("passed"))
        return result
    except Exception as e:
        log.error("auditor_error", error=str(e))
        return {"issues": [], "passed": False, "error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Foydalanish: python -m uzmyjob.agents.auditor <fayl_yo'li>")
        sys.exit(1)

    target_path = Path(sys.argv[1])
    if not target_path.exists():
        print(f"Xato: {target_path} topilmadi.")
        sys.exit(1)

    code_text = target_path.read_text(encoding="utf-8")
    report = asyncio.run(audit_code(code_text, target_path.name))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report.get("passed") else 1)
