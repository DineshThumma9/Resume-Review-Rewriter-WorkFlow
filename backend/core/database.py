"""
backend/db.py

Async SQLAlchemy engine and session setup.
Tables are created on app startup via create_tables().
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Annotated, Any, cast

from dotenv import load_dotenv
from fastapi import Depends
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from core.config import settings
from models.models import (  # noqa: F401 – ensures table is registered
    Resume,
    ResumeJob,
    Template,
)

logger = logging.getLogger(__name__)


load_dotenv()


# echo=True logs all SQL incl. bound params — only enable in dev
engine = create_async_engine(settings.database_url, echo=settings.dev_mode, future=True)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_session)]


async def seed_templates(session: AsyncSession):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(base_dir, "templates")

    allowed_builtin_names = {"modern1", "modern2", "modern3"}

    # 1. Purge any legacy templates with misspelled "mordern" in name (builtin or custom)
    mordern_result = await session.execute(
        select(Template).where(cast(Any, Template.name).ilike("%mordern%"))
    )
    mordern_templates = mordern_result.scalars().all()
    if mordern_templates:
        mordern_ids = [t.id for t in mordern_templates]
        await session.execute(
            update(Resume)
            .where(Resume.template_id.in_(mordern_ids))  # type: ignore
            .values(template_id=None)
        )
        await session.flush()
        for tmpl in mordern_templates:
            await session.delete(tmpl)
        await session.flush()

    # 2. Find and remove non-canonical builtins
    stale_result = await session.execute(select(Template).where(Template.is_builtin))
    stale_templates = [
        t for t in stale_result.scalars().all() if t.name not in allowed_builtin_names
    ]

    if stale_templates:
        stale_ids = [t.id for t in stale_templates]

        # Detach any resumes that reference these stale templates to avoid FK violation
        await session.execute(
            update(Resume)
            .where(Resume.template_id.in_(stale_ids))  # type: ignore
            .values(template_id=None)
        )
        await session.flush()

        # Now safe to delete the stale templates
        for tmpl in stale_templates:
            await session.delete(tmpl)
        await session.flush()

    preview_urls = {
        "modern1": "/previews/template_1-1.jpg",
        "modern2": "/previews/template_2-1.jpg",
        "modern3": "/previews/template_3-1.jpg",
    }

    # 3. Seed / refresh / deduplicate the three canonical builtin templates
    for template_name in sorted(allowed_builtin_names):
        result = await session.execute(
            select(Template).where(Template.name == template_name, Template.is_builtin)
        )
        existing_list = result.scalars().all()

        canonical_template: Template | None = None
        if existing_list:
            canonical_template = existing_list[0]
            # Deduplicate if multiple builtins exist with the same name
            if len(existing_list) > 1:
                dup_templates = existing_list[1:]
                dup_ids = [t.id for t in dup_templates]
                await session.execute(
                    update(Resume)
                    .where(Resume.template_id.in_(dup_ids))  # type: ignore
                    .values(template_id=canonical_template.id)
                )
                await session.flush()
                for dup in dup_templates:
                    await session.delete(dup)
                await session.flush()

        template_path = os.path.join(templates_dir, f"{template_name}.tex")
        if not os.path.exists(template_path):
            continue

        with open(template_path, encoding="utf-8") as f:
            tex_source = f.read()

        preview_url = preview_urls.get(template_name)

        if canonical_template is None:
            # First-time seed
            session.add(
                Template(
                    name=template_name,
                    tex_source=tex_source,
                    is_builtin=True,
                    preview_url=preview_url,
                )
            )
            logger.info("Seeded builtin template: %s", template_name)
        elif (
            canonical_template.tex_source != tex_source
            or canonical_template.preview_url != preview_url
        ):
            # File changed on disk or preview url missing — update
            canonical_template.tex_source = tex_source
            canonical_template.preview_url = preview_url
            logger.info("Updated builtin template: %s", template_name)

    await session.commit()


async def create_tables() -> None:
    """Called on app startup. Creates all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Add new columns to users table if they don't exist
    for col in ["github", "linkedin", "website", "location", "phone", "raw_resume"]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} TEXT"))
        except Exception as e:
            logger.warning(f"Could not add column {col} to users table: {e}")

    # Update resumes template_id foreign key constraint to ON DELETE SET NULL
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE resumes DROP CONSTRAINT IF EXISTS resumes_template_id_fkey")
            )
            await conn.execute(
                text(
                    "ALTER TABLE resumes ADD CONSTRAINT resumes_template_id_fkey FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL"
                )
            )
    except Exception as e:
        logger.warning(f"Could not update resumes template_id foreign key constraint: {e}")

    # Seed builtin templates
    async with AsyncSessionLocal() as session:
        await seed_templates(session)
