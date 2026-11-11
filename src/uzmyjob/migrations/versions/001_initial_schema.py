"""Initial schema — users, vacancies, applications, sources.

Revision ID: 001_initial
Revises:
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("language", sa.String(5), default="uz"),
        sa.Column("position", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("experience_years", sa.Integer),
        sa.Column("min_salary", sa.Integer),
        sa.Column("employment_type", sa.String(100)),
        sa.Column("keywords", sa.Text),
        sa.Column("blacklist", sa.Text),
        sa.Column("cv_file_id", sa.String(200)),
        sa.Column("cv_encrypted", sa.LargeBinary),
        sa.Column("cover_letter_template", sa.Text),
        sa.Column("portfolio_links", sa.Text),
        sa.Column("hh_access_token_enc", sa.Text),
        sa.Column("hh_refresh_token_enc", sa.Text),
        sa.Column("hh_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("hh_resume_id", sa.String(100)),
        sa.Column("match_threshold", sa.Float, default=0.55),
        sa.Column("auto_apply", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    # vacancies
    op.create_table(
        "vacancies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("company", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("currency", sa.String(10)),
        sa.Column("description", sa.Text),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("contact_phone", sa.String(50)),
        sa.Column("contact_telegram", sa.String(100)),
        sa.Column("contact_email", sa.String(200)),
        sa.Column("raw_data", sa.Text),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source", "external_id", name="uq_vacancy_source_external"),
    )
    op.create_index("ix_vacancies_source", "vacancies", ["source"])
    op.create_index("ix_vacancies_external_id", "vacancies", ["external_id"])

    # applications
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("vacancy_id", sa.Integer, sa.ForeignKey("vacancies.id")),
        sa.Column("status", sa.String(20), default="sent"),
        sa.Column("match_score", sa.Float),
        sa.Column("cover_letter_sent", sa.Text),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "source", "external_id", name="uq_app_user_source_ext"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])

    # sources
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("status", sa.String(20), default="ok"),
        sa.Column("last_error", sa.Text),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("error_count", sa.Integer, default=0),
    )


def downgrade() -> None:
    op.drop_table("applications")
    op.drop_table("vacancies")
    op.drop_table("users")
    op.drop_table("sources")

