"""User modeli."""
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from uzmyjob.models.base import Base


class Language(StrEnum):
    UZ = "uz"
    RU = "ru"
    EN = "en"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[Language] = mapped_column(
        Enum(Language, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=Language.UZ,
    )

    # Profil
    position: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    experience_years: Mapped[int | None]
    min_salary: Mapped[int | None]
    employment_type: Mapped[str | None] = mapped_column(String(100))
    keywords: Mapped[str | None] = mapped_column(Text)   # JSON array satr
    blacklist: Mapped[str | None] = mapped_column(Text)  # JSON array satr

    # CV & cover letter
    cv_file_id: Mapped[str | None] = mapped_column(String(200))  # Telegram file_id
    cv_encrypted: Mapped[bytes | None]                            # Fernet shifrlangan
    cover_letter_template: Mapped[str | None] = mapped_column(Text)
    portfolio_links: Mapped[str | None] = mapped_column(Text)

    # hh.uz OAuth
    hh_access_token_enc: Mapped[str | None] = mapped_column(Text)
    hh_refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    hh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hh_resume_id: Mapped[str | None] = mapped_column(String(100))

    # Matching
    match_threshold: Mapped[float] = mapped_column(Float, default=0.55)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )
