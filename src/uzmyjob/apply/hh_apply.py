"""hh.uz OAuth2 va avtomatik murojaat (apply) moduli."""
from typing import Any

import httpx

from uzmyjob.config import settings
from uzmyjob.utils.logger import log


class HeadHunterApplyService:
    """hh.uz da OAuth2 avtorizatsiyasi, resume olish va vakansiyaga murojaat qilish."""

    AUTH_URL = "https://hh.uz/oauth/authorize"
    TOKEN_URL = "https://hh.uz/oauth/token"
    API_BASE = "https://api.hh.uz"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str = "https://t.me/Uzmyjob_bot",
        user_agent: str = "UzMyJobBot/1.0 (dev@uzmyjob.local)",
    ):
        self.client_id = client_id or settings.hh_client_id
        self.client_secret = client_secret or settings.hh_client_secret
        self.redirect_uri = redirect_uri
        self.user_agent = user_agent

    def get_authorization_url(self, state: str = "") -> str:
        """Foydalanuvchi brauzerda hh.uz hisobiga ruxsat berishi uchun havola."""
        params = [
            "response_type=code",
            f"client_id={self.client_id}",
            f"redirect_uri={self.redirect_uri}",
        ]
        if state:
            params.append(f"state={state}")
        return f"{self.AUTH_URL}?{'&'.join(params)}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any] | None:
        """
        Authorization code orqali access_token va refresh_token olish.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(self.TOKEN_URL, headers=headers, data=data)
                if res.status_code == 200:
                    payload = res.json()
                    log.info("hh_token_exchange_success")
                    return payload
                log.error("hh_token_exchange_failed", status=res.status_code, body=res.text)
                return None
        except Exception as e:
            log.error("hh_token_exchange_exception", error=str(e))
            return None

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any] | None:
        """
        Muddati tugagan access_token ni refresh_token orqali yangilash.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(self.TOKEN_URL, headers=headers, data=data)
                if res.status_code == 200:
                    payload = res.json()
                    log.info("hh_token_refresh_success")
                    return payload
                log.error("hh_token_refresh_failed", status=res.status_code, body=res.text)
                return None
        except Exception as e:
            log.error("hh_token_refresh_exception", error=str(e))
            return None

    async def get_my_resumes(self, access_token: str) -> list[dict[str, Any]]:
        """
        Foydalanuvchining hh.uz dagi rezyumelarini olish (resume_id topish uchun).
        """
        headers = {
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        url = f"{self.API_BASE}/resumes/mine"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("items", [])
                log.error("hh_get_resumes_failed", status=res.status_code)
                return []
        except Exception as e:
            log.error("hh_get_resumes_exception", error=str(e))
            return []

    async def apply(
        self,
        access_token: str,
        vacancy_id: str,
        resume_id: str,
        message: str = "",
    ) -> tuple[bool, str]:
        """
        Vakansiyaga murojaat (отклик / negotiation) yuborish.
        Returns: (success, result_message_or_error)
        """
        headers = {
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        url = f"{self.API_BASE}/negotiations"
        data = {
            "vacancy_id": vacancy_id,
            "resume_id": resume_id,
        }
        if message:
            data["message"] = message

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, headers=headers, data=data)
                # 201 Created = muvaffaqiyatli murojaat
                if res.status_code == 201:
                    location = res.headers.get("Location", "")
                    log.info("hh_apply_success", vacancy_id=vacancy_id, location=location)
                    return True, "Murojaat muvaffaqiyatli yuborildi."

                # 400 yoki boshqa xatolar (masalan allaqachon topshirilgan bo'lsa)
                err_text = res.text
                log.warning("hh_apply_rejected", status=res.status_code, body=err_text[:200])
                if "already_applied" in err_text:
                    return False, "Siz bu vakansiyaga allaqachon murojaat qilgansiz."
                return False, f"Xatolik (status {res.status_code}): {err_text[:150]}"

        except Exception as e:
            log.error("hh_apply_exception", error=str(e))
            return False, f"Tarmoq xatosi: {e!s}"


HeadHunterApplyClient = HeadHunterApplyService

