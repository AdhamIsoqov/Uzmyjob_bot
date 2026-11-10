"""Application (murojaat) modeli."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from uzmyjob.models.base import Base


class AppStatus(str, enum.Enum):
    SENT = "sent"
    VIEWED = "viewed"
    REPLIED = "replied"
    REJECTED = "rejected"


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_id", name="uq_app_user_source_ext"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(200))
    vacancy_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("vacancies.id"))
    status: Mapped[AppStatus] = mapped_column(
        Enum(AppStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=AppStatus.SENT,
    )
    match_score: Mapped[float | None] = mapped_column(Float)
    cover_letter_sent: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
