import base64
import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import get_session
from core.llm_throttle import throttle_provider
from core.security import decode_access_token
from models import User
from models.models import Template
from schemas.schema import Details, MaskDetails, RewriteResume
from services.auth_service import AuthService
from services.llm_service import get_llm_client
from services.storage import upload_pdf_to_cloudinary
from services.workflow import ResumeWorkflowService
from utils.mappers import map_llm_to_profile
from utils.prompts import extract_details_prompt, parse_resume_prompt

logger = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False)


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    if not token:
        token = request.query_params.get("token")
    return token


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    FastAPI dependency that resolves the authenticated user by checking
    cookies, Authorization header, or token query param.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> User | None:
    """
    Optional user dependency — returns User if authenticated, else None without raising 401.
    """
    token = _extract_token(request)
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
        if user_id is None:
            return None
        result = await db.execute(select(User).where(User.id == int(user_id)))
        return result.scalar_one_or_none()
    except Exception:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


async def mask_resume(resume_content, mask_details: MaskDetails):
    resume_content = RewriteResume.model_validate(resume_content)
    if mask_details.project_name and resume_content.projects:
        for project in resume_content.projects:
            project.name = "PROJECT NAME"

    if mask_details.company_name:
        if resume_content.experience:
            for exp in resume_content.experience:
                exp.company = "COMPANY NAME"
        if resume_content.internships:
            for internship in resume_content.internships:
                internship.company = "COMPANY NAME"

    if mask_details.education and resume_content.education:
        for edu in resume_content.education:
            if edu.institution:
                edu.institution = "UNIVERSITY NAME"

    if resume_content.details:
        if mask_details.name and resume_content.details.name:
            resume_content.details.name = "John Doe"
        if mask_details.email and resume_content.details.email:
            resume_content.details.email = "doejohn"
        if mask_details.phone and resume_content.details.contact:
            resume_content.details.contact = "1234567890"
        if mask_details.location and resume_content.details.location:
            resume_content.details.location = "LOCATION"
        if mask_details.github and resume_content.details.github:
            resume_content.details.github = "GITHUB USERNAME"
        if mask_details.linkedin and resume_content.details.linkedin:
            resume_content.details.linkedin = "LINKEDIN USERNAME"
        if mask_details.leetcode and resume_content.details.leetcode:
            resume_content.details.leetcode = "LEETCODE USERNAME"
        if mask_details.portfolio and resume_content.details.portfolio:
            resume_content.details.portfolio = "PORTFOLIO URL"

        if resume_content.details.profile_links:
            # Type ignoring for dict assignment warnings from linter
            links = resume_content.details.profile_links
            for k in list(links.keys()):  # type: ignore
                if k == "phone" and mask_details.phone:
                    links[k] = "PHONE_NUMBER"  # type: ignore
                elif k == "email" and mask_details.email:
                    links[k] = "EMAIL ADDRESS"  # type: ignore
                elif k == "github" and mask_details.github:
                    links[k] = "GITHUB USERNAME"  # type: ignore
                elif k == "linkedin" and mask_details.linkedin:
                    links[k] = "LINKEDIN USERNAME"  # type: ignore
                elif k == "leetcode" and mask_details.leetcode:
                    links[k] = "LEETCODE USERNAME"  # type: ignore
                elif k in ("portfolio", "website") and mask_details.portfolio:
                    links[k] = "PORTFOLIO URL"  # type: ignore

    return resume_content.model_dump_json()


def extract_username(url: str):
    if not url:
        return None
    url = url.strip().rstrip("/")
    parts = url.split("/")
    if parts and len(parts[-1]) > 3:
        return parts[-1]
    return None


def mask_latex(latex_code: str, resume_content: dict, mask_details: MaskDetails) -> str:
    resume_content_model = RewriteResume.model_validate(resume_content)

    replacements = []

    if mask_details.project_name and resume_content_model.projects:
        for project in resume_content_model.projects:
            if project.name:
                replacements.append((project.name, "PROJECT NAME"))

    if mask_details.company_name:
        if resume_content_model.experience:
            for exp in resume_content_model.experience:
                if exp.company:
                    replacements.append((exp.company, "COMPANY NAME"))
        if resume_content_model.internships:
            for internship in resume_content_model.internships:
                if internship.company:
                    replacements.append((internship.company, "COMPANY NAME"))

    if mask_details.education and resume_content_model.education:
        for edu in resume_content_model.education:
            if edu.institution:
                replacements.append((edu.institution, "UNIVERSITY NAME"))

    if resume_content_model.details:
        if mask_details.name and resume_content_model.details.name:
            name = resume_content_model.details.name
            replacements.append((name, "John Doe"))
            parts = name.split()
            if len(parts) >= 2:
                for p in parts:
                    if len(p) > 3:
                        replacements.append((p, "Doe"))

        if mask_details.email and resume_content_model.details.email:
            replacements.append((resume_content_model.details.email, "doejohn@example.com"))

        if mask_details.phone and resume_content_model.details.contact:
            contact = resume_content_model.details.contact
            replacements.append((contact, "1234567890"))
            clean_phone = contact.replace(" ", "")
            if clean_phone != contact:
                replacements.append((clean_phone, "1234567890"))

        if mask_details.location and resume_content_model.details.location:
            replacements.append((resume_content_model.details.location, "LOCATION"))

        if mask_details.github and resume_content_model.details.github:
            replacements.append((resume_content_model.details.github, "GITHUB USERNAME"))
            uname = extract_username(resume_content_model.details.github)
            if uname:
                replacements.append((uname, "GITHUB USERNAME"))

        if mask_details.linkedin and resume_content_model.details.linkedin:
            replacements.append((resume_content_model.details.linkedin, "LINKEDIN_USERNAME"))
            uname = extract_username(resume_content_model.details.linkedin)
            if uname:
                replacements.append((uname, "LINKEDIN_USERNAME"))

        if mask_details.leetcode and resume_content_model.details.leetcode:
            replacements.append((resume_content_model.details.leetcode, "LEETCODE USERNAME"))
            uname = extract_username(resume_content_model.details.leetcode)
            if uname:
                replacements.append((uname, "LEETCODE USERNAME"))

        if mask_details.portfolio and resume_content_model.details.portfolio:
            replacements.append((resume_content_model.details.portfolio, "PORTFOLIO_URL"))

    # deduplicate and sort
    replacements = list(set(replacements))
    replacements.sort(key=lambda x: len(x[0]), reverse=True)

    for old, new in replacements:
        if old.strip():
            latex_code = latex_code.replace(old, new)

    return latex_code





async def autofill_resume_profile(resume_text: str, user: User, db: AsyncSession) -> dict[str, Any]:
    """
    Parse a resume's raw text into a structured profile dictionary using the LLM.
    This is a pure resume-domain operation: it has no HTTP or authentication concerns.

    Steps:
      1. Call 1 — Extract personal Details (name, links) with high precision.
      2. Call 2 — Parse full RewriteResume structure.
      3. Merge Call 1 results into Call 2 to fill any gaps.

    Returns a plain dict suitable for the autofill profile API response.
    """

    llm = await get_llm_client(db, user=user)
    provider_name = getattr(llm, "model_provider", None)

    # ── Call 1: Extract personal details + links with precision ──────────
    details_obj: Details | None = None
    try:
        details_llm = llm.with_structured_output(Details)
        details_messages = [
            SystemMessage(content=extract_details_prompt),
            HumanMessage(content=f"Resume text:\n{resume_text}"),
        ]
        await throttle_provider(provider_name)
        raw_details = await details_llm.ainvoke(details_messages)
        details_obj = cast(Details, raw_details)
    except Exception as details_err:
        logger.warning(f"Autofill details extraction failed: {details_err}")

    # ── Call 2: Parse full resume structure ──────────────────────────────
    structured_llm = llm.with_structured_output(RewriteResume)
    messages = [
        SystemMessage(content=parse_resume_prompt),
        HumanMessage(content=f"Resume text:\n{resume_text}"),
    ]
    await throttle_provider(provider_name)
    raw_parsed = await structured_llm.ainvoke(messages)
    if not raw_parsed:
        raise ValueError("LLM returned an empty parsed result.")

    parsed = cast(RewriteResume, raw_parsed)
    if isinstance(parsed, dict):
        parsed = RewriteResume.model_validate(parsed)

    # ── Merge Call 1 into Call 2 ─────────────────────────────────────────
    if details_obj is not None and isinstance(details_obj, Details):
        if parsed.details is not None:
            if not parsed.details.name and details_obj.name:
                parsed.details.name = details_obj.name
            if details_obj.profile_links:
                if not parsed.details.profile_links:
                    parsed.details.profile_links = details_obj.profile_links
                else:
                    for k, v in details_obj.profile_links.items():
                        if not parsed.details.profile_links.get(k) and v:
                            parsed.details.profile_links[k] = v
        else:
            parsed.details = details_obj

    return map_llm_to_profile(parsed)


# ── Infrastructure helpers ────────────────────────────────────────────────────


async def save_and_upload(
    latex_code: str,
    user: User,
    resume_id: int,
    pdf_base64: str | None = None,
) -> tuple[str, str | None]:
    """
    Compile LaTeX source to PDF (if not already base64), upload to Cloudinary,
    and return (pdf_url, preview_image_url).

    If *pdf_base64* is a data-URI already containing base64-encoded PDF bytes,
    the compilation step is skipped and the bytes are decoded directly.
    """

    if pdf_base64 and "base64," in pdf_base64:
        b64_str = pdf_base64.split("base64,")[1]
        pdf_bytes = base64.b64decode(b64_str)
        pdf_url = pdf_base64
    elif not latex_code or not latex_code.strip():
        pdf_bytes = b""
        pdf_url = ""
    else:
        service = ResumeWorkflowService()
        pdf_bytes = await service.latex_to_pdf(latex_code, "resume.pdf")
        pdf_url = f"data:application/pdf;base64,{base64.b64encode(pdf_bytes).decode()}"

    preview_url = None
    try:
        ts = int(datetime.now(UTC).timestamp())
        filename = f"resume_{user.id}_{resume_id}_{ts}.pdf"
        upload_res = await upload_pdf_to_cloudinary(pdf_bytes, filename)
        if upload_res:
            pdf_url = upload_res.get("pdf_url") or pdf_url
            preview_url = upload_res.get("preview_image_url")
    except Exception as err:
        logger.error(f"Failed to upload resume: {err}")

    return pdf_url, preview_url


async def build_graph_state(
    db: AsyncSession,
    provider: str,
    user: User,
    template_id: str,
    exclude_sections: str,
    model: str,
    tone: str,
    jd: str,
    resume_text: str,
    page_count: int | None = None,
) -> dict:
    """
    Assemble the initial LangGraph state dict for the resume analysis workflow.
    Resolves the user's API key for the requested provider and the LaTeX template
    source (if a DB-backed template ID is given).

    This replaces the ad-hoc `start_graph` helper that used to live in the route file.
    """

    auth_service = AuthService(db)
    api_key = ""
    try:
        api_key = await auth_service.get_api_key(provider, user)
    except Exception:
        pass  # fall through — workflow will fail gracefully with a clear error

    template_source = None
    db_template_id = None
    if template_id and template_id.isdigit():
        t_res = await db.execute(select(Template).where(Template.id == int(template_id)))
        template_obj = t_res.scalar_one_or_none()
        if template_obj:
            template_source = template_obj.tex_source
            db_template_id = template_obj.id

    return {
        "jd": jd,
        "resume": resume_text,
        "page_count": page_count,
        "tone": tone,
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "exclude_sections": json.loads(exclude_sections),
        "analysis": None,
        "changes_content": None,
        "latex_code": "",
        "output_path": "/output",
        "template_source": template_source or "",
        "template_id": db_template_id,
    }
