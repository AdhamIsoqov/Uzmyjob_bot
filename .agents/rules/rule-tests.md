---
name: rule-tests
globs: ["src/uzmyjob/adapters/**/*.py", "src/uzmyjob/agents/**/*.py"]
---
# Test qoidasi

1. Har yangi adapter uchun unit test (mock fetch) yoziladi.
2. CI yashil bo'lmasa merge yo'q.
3. Gemini API real chaqirilmaydi — mock ishlatiladi.
4. `pytest-asyncio` bilan async testlar yoziladi.

