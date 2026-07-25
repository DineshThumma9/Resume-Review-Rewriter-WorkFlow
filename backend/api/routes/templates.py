from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import RedirectResponse, Response
from sqlmodel import func, or_, select

from core.database import DB
from models.models import Resume, Template
from schemas.schema import (
    PaginatedTemplateResponse,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from services.preview import generate_template_preview_task
from services.renderer import render_resume_template_from_string
from services.resume_service import CurrentUser, OptionalCurrentUser
from services.storage import upload_pdf_to_cloudinary
from services.workflow import ResumeWorkflowService
from utils.constants import DUMMY_RESUME_DATA

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=PaginatedTemplateResponse)
async def list_templates(current_user: CurrentUser, db: DB, skip: int = 0, limit: int = 100):
    query = select(Template).where(or_(Template.is_builtin, Template.user_id == current_user.id))
    result = await db.execute(query.offset(skip).limit(limit))
    templates = result.scalars().all()

    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    return PaginatedTemplateResponse(
        templates=templates,  # type: ignore
        skip=skip,
        limit=limit,
        total_count=total_count,  # type: ignore
    )


@router.post("", response_model=TemplateOut)
async def create_template(
    body: TemplateCreate,
    current_user: CurrentUser,
    db: DB,
    background_tasks: BackgroundTasks,
):
    template = Template(name=body.name, tex_source=body.tex_source, user_id=current_user.id)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    background_tasks.add_task(generate_template_preview_task, template.id)  # type: ignore
    return template


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    current_user: CurrentUser,
    db: DB,
    background_tasks: BackgroundTasks,
):
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.user_id == current_user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    template.name = body.name
    template.tex_source = body.tex_source
    await db.commit()
    await db.refresh(template)
    background_tasks.add_task(generate_template_preview_task, template.id)  # type: ignore
    return template


@router.delete("/{template_id}")
async def delete_template(template_id: int, current_user: CurrentUser, db: DB):
    result = await db.execute(
        select(Template).where(Template.id == template_id, Template.user_id == current_user.id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    await db.delete(template)
    await db.commit()
    return {"message": "Template deleted"}


@router.get("/{template_id}/pdf")
async def get_template_pdf(
    template_id: int,
    current_user: OptionalCurrentUser,
    db: DB,
):
    """
    Compiles a template to an actual PDF file, uploads to Cloudinary,
    and returns the PDF stream or redirects to Cloudinary.
    """
    user_id = current_user.id if current_user else None
    query = select(Template).where(
        or_(Template.is_builtin, Template.user_id == user_id),
        Template.id == template_id,
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

    # Determine sample data to render: prioritize candidate's latest resume if present
    resume_data = DUMMY_RESUME_DATA
    if current_user:
        res = await db.execute(
            select(Resume)
            .where(Resume.user_id == current_user.id)
            .order_by(Resume.created_at.desc())  # type: ignore
            .limit(1)
        )
        latest_resume = res.scalar_one_or_none()
        if (
            latest_resume
            and latest_resume.content
            and isinstance(latest_resume.content, dict)
            and latest_resume.content.get("details")
        ):
            resume_data = latest_resume.content
    latex_code = render_resume_template_from_string(template.tex_source, resume_data)

    workflow_service = ResumeWorkflowService()
    filename = f"template_{template_id}.pdf"
    pdf_bytes = await workflow_service.latex_to_pdf(latex_code, filename)

    if not pdf_bytes:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to compile template PDF")

    try:
        upload_res = await upload_pdf_to_cloudinary(pdf_bytes, filename)
        pdf_url = upload_res.get("pdf_url")
        if pdf_url:
            return RedirectResponse(url=pdf_url)
    except Exception:
        pass

    return Response(content=pdf_bytes, media_type="application/pdf")
