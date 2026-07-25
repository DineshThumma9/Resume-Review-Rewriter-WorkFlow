from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Column, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSON
from sqlmodel import Field, SQLModel


def naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "users"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    name: str
    email: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=naive_utcnow)
    github: str | None = Field(default=None, sa_column=Column(Text))
    linkedin: str | None = Field(default=None, sa_column=Column(Text))
    website: str | None = Field(default=None, sa_column=Column(Text))
    location: str | None = Field(default=None, sa_column=Column(Text))
    phone: str | None = Field(default=None, sa_column=Column(Text))
    raw_resume: str | None = Field(default=None, sa_column=Column(Text))


class Template(SQLModel, table=True):
    __tablename__ = "templates"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id")
    name: str
    tex_source: str = Field(sa_column=Column(Text))
    is_builtin: bool = Field(default=False)
    preview_url: str | None = None
    created_at: datetime = Field(default_factory=naive_utcnow)


class Resume(SQLModel, table=True):
    __tablename__ = "resumes"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="users.id")
    label: str
    template_id: int | None = Field(default=None, foreign_key="templates.id", ondelete="SET NULL")
    jd_snippet: str | None = None
    content: dict | None = Field(default=None, sa_column=Column(JSON))
    tex_source: str | None = Field(default=None, sa_column=Column(Text))
    pdf_url: str | None = None
    preview_url: str | None = None
    created_at: datetime = Field(default_factory=naive_utcnow)
    updated_at: datetime = Field(default_factory=naive_utcnow)


class APIKEYS(SQLModel, table=True):
    __tablename__ = "api_keys"  # type: ignore
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", primary_key=True)
    provider: str = Field(primary_key=True, index=True)
    encrypted_key: str


class UserLLMConfig(SQLModel, table=True):
    __tablename__ = "config"  # type: ignore
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE", primary_key=True)
    provider: str = Field(index=True)
    model: str


class OAuthCode(SQLModel, table=True):
    __tablename__ = "oauth_codes"  # type: ignore
    code: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    is_new: bool
    created_at: datetime = Field(default_factory=naive_utcnow)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResumeJob(SQLModel, table=True):
    __tablename__ = "resume_jobs"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    resume_id: int = Field(foreign_key="resumes.id", ondelete="CASCADE")
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    style: str
    status: str = Field(
        default=JobStatus.PENDING.value,
        sa_column=Column(
            SAEnum(
                "pending",
                "running",
                "completed",
                "failed",
                name="jobstatus",
                create_type=False,
            ),
            nullable=False,
        ),
    )
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    pdf_url: str | None = None
    created_at: datetime = Field(default_factory=naive_utcnow)
    completed_at: datetime | None = None
