import asyncio
import base64
import copy
import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from core.database import DB, AsyncSessionLocal
from core.rate_limit import user_limiter
from models.models import JobStatus, Resume, ResumeJob, Template, User
from schemas.schema import (
    CompileRequest,
    ModifyRequest,
    PaginatedResume,
    ResumeCreate,
    ResumeOut,
    ResumeUpdate,
    RewriteResume,
    SyncContentRequest,
)
from services.llm_service import get_llm_client
from services.renderer import render_resume_template, render_resume_template_from_string
from services.resume_service import CurrentUser, build_graph_state, save_and_upload
from services.workflow import ResumeWorkflowService
from utils.constants import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER
from utils.error_helpers import classify_llm_error
from utils.pdf_extractor import extract_resume_text_and_links
from utils.prompts import parse_resume_prompt
from utils.pubsub import get_redis, publish_job_update
from utils.resume_text import (
    extract_profile_details,
    extract_resume_details,
    resolve_resume_label,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resumes", tags=["resumes"])


# ─────────────────────────────────────────────────────────────────────────────
# Resume CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=PaginatedResume)
async def get_resumes(user: CurrentUser, db: DB, skip: int = 0, limit: int = 100):
    """List all resumes for the authenticated user."""
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == user.id)
        .order_by(Resume.updated_at.desc())  # type: ignore
        .offset(skip)
        .limit(limit)
    )
    resumes = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Resume.id)).where(Resume.user_id == user.id)  # type: ignore
    )
    total_count = count_result.scalar_one()

    return PaginatedResume(
        resumes=resumes,  # type: ignore
        skip=skip,
        limit=limit,
        total_count=total_count,
    )


@router.post("", response_model=ResumeOut)
async def create_resume(body: ResumeCreate, user: CurrentUser, db: DB):
    # Compile LaTeX and upload preview if tex_source is provided
    pdf_url, preview_url = await save_and_upload(
        latex_code=body.tex_source,
        user=user,
        resume_id=int(datetime.now(UTC).timestamp()),
        pdf_base64=body.pdf_url,
    )

    resume = Resume(
        user_id=user.id,
        label=body.label,
        tex_source=body.tex_source,
        jd_snippet=body.jd_snippet,
        template_id=body.template_id,
        pdf_url=pdf_url,
        preview_url=preview_url,
        content=body.content,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return resume


@router.post("/compile")
async def compile_latex(body: CompileRequest, user: CurrentUser, db: DB):
    try:
        if body.id is not None:
            result = await db.execute(
                select(Resume).where(Resume.id == body.id, Resume.user_id == user.id)
            )
            resume = result.scalar_one_or_none()
            if resume:
                pdf_url, preview_url = await save_and_upload(
                    latex_code=body.latex_code, user=user, resume_id=body.id
                )
                resume.tex_source = body.latex_code
                resume.pdf_url = pdf_url
                if preview_url:
                    resume.preview_url = preview_url

                resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
                await db.commit()
                return {"pdf_url": pdf_url}

        # Fallback if body.id is None or resume not found
        service = ResumeWorkflowService()
        pdf_bytes = await service.latex_to_pdf(body.latex_code, "resume.pdf")
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        pdf_url = f"data:application/pdf;base64,{pdf_base64}"
        return {"pdf_url": pdf_url}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LaTeX compilation failed: {e!s}",
        )


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(resume_id: int, user: CurrentUser, db: DB):
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return resume


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: int, user: CurrentUser, db: DB):
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    await db.delete(resume)
    await db.commit()


@router.put("/{resume_id}", response_model=ResumeOut)
async def update_resume(resume_id: int, body: ResumeUpdate, user: CurrentUser, db: DB):
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    if body.label is not None:
        resume.label = body.label
    if body.tex_source is not None:
        resume.tex_source = body.tex_source
        pdf_url, preview_url = await save_and_upload(
            latex_code=body.tex_source, user=user, resume_id=resume_id
        )
        if pdf_url is not None:
            resume.pdf_url = pdf_url
        if preview_url is not None:
            resume.preview_url = preview_url

    resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return resume


@router.put("/{resume_id}/render")
async def render_resume(resume_id: int, user: CurrentUser, db: DB, template_id: str = ""):
    """Re-render with a different template without re-running AI."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    if not resume.content:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Resume content is empty, please run analysis first",
        )

    template_source = None
    db_template_id = None
    if template_id and template_id.isdigit():
        t_res = await db.execute(select(Template).where(Template.id == int(template_id)))
        template_obj = t_res.scalar_one_or_none()
        if template_obj:
            template_source = template_obj.tex_source
            db_template_id = template_obj.id

    try:
        data_dict = copy.deepcopy(resume.content) if resume.content else {}
        data_dict["jd"] = resume.jd_snippet

        if template_source and template_source.strip():
            latex_code = render_resume_template_from_string(template_source, data_dict)
        else:
            latex_code = render_resume_template("modern1.tex", data_dict)

        pdf_url, preview_url = await save_and_upload(
            latex_code=latex_code, user=user, resume_id=resume_id
        )
        resume.tex_source = latex_code
        resume.pdf_url = pdf_url
        if preview_url:
            resume.preview_url = preview_url
        resume.template_id = db_template_id
        resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.add(resume)
        await db.commit()
        await db.refresh(resume)
        return resume
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to re-render resume: {e!s}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# AI Analysis (streaming SSE)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/analyze")
@user_limiter.limit("20/minute")
async def analyze(
    request: Request,
    user: CurrentUser,
    db: DB,
    jd: str = Form(...),
    label: str = Form(""),
    tone: str = Form("Professional"),
    template_id: str = Form("1"),
    provider: str = Form(DEFAULT_LLM_PROVIDER),
    model: str = Form(DEFAULT_LLM_MODEL),
    exclude_sections: str = Form("{}"),
    resume_file: UploadFile | None = File(None),
):
    """
    Main AI workflow. Streams progress as Server-Sent Events.
    Events: progress | complete | error
    """

    async def event_stream():
        try:
            resume_text = ""
            page_count = None
            if resume_file is not None:
                text_extracted, p_count = await extract_resume_text_and_links(resume_file)
                resume_text += text_extracted
                page_count = p_count
            else:
                raw_res = user.raw_resume
                if isinstance(raw_res, (dict, list)):
                    raw_res_str = json.dumps(raw_res)
                else:
                    raw_res_str = str(raw_res) if raw_res else ""

                if not raw_res_str or not raw_res_str.strip():
                    yield f"data: {json.dumps({'event': 'error', 'message': 'No resume provided. Please upload a PDF resume or type your resume in your Profile.'})}\n\n"
                    return

                resume_text += extract_resume_details(raw_res)

            # Append candidate
            resume_text += extract_profile_details(user)

            initial_state = await build_graph_state(
                db,
                provider,
                user,
                template_id,
                exclude_sections,
                model,
                tone,
                jd,
                resume_text,
                page_count,
            )
        except Exception as graph_err:
            tb = traceback.format_exc()
            logger.error(f"GRAPH ERROR: {tb}")
            err_msg = classify_llm_error(graph_err, dev_mode=settings.dev_mode, tb=tb)
            yield f"data: {json.dumps({'event': 'error', 'message': err_msg})}\n\n"
            return

        service = ResumeWorkflowService()
        graph = service.graph

        analysis_data = None
        try:
            async for event in graph.astream(initial_state, stream_mode="updates"):  # type: ignore
                if "match_jd" in event:
                    analysis_data = event["match_jd"].get("analysis")
                    if analysis_data:
                        # 1. Score & match — instant
                        yield f"data: {json.dumps({'event': 'analysis_score', 'score': analysis_data.get('score'), 'match': analysis_data.get('match'), 'urgency': analysis_data.get('urgency')})}\n\n"

                        # 2. Resume quality — send immediately
                        quality = analysis_data.get("resume_quality") or ""
                        if quality:
                            yield f"data: {json.dumps({'event': 'analysis_quality', 'text': quality})}\n\n"

                        # 3. Explanation — send immediately
                        explanation = analysis_data.get("match_explanation") or ""
                        if explanation:
                            yield f"data: {json.dumps({'event': 'analysis_explanation', 'text': explanation})}\n\n"

                        # 4. Missing keywords — one per event
                        for kw in analysis_data.get("missing_keywords") or []:
                            yield f"data: {json.dumps({'event': 'analysis_keyword', 'keyword': kw})}\n\n"

                        # 5. Negative points — one per event
                        for pt in analysis_data.get("negative_points") or []:
                            yield f"data: {json.dumps({'event': 'analysis_negative', 'text': pt})}\n\n"

                        # 6. Improvements — one per event
                        for imp in analysis_data.get("potential_improvements") or []:
                            yield f"data: {json.dumps({'event': 'analysis_improvement', 'text': imp})}\n\n"

                        # 7. Done — triggers UI to flip to success state
                        yield f"data: {json.dumps({'event': 'analysis_done'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'analysis_done'})}\n\n"
                elif "rewrite_resume" in event:
                    yield f"data: {json.dumps({'event': 'progress', 'step': 'rewrite_resume', 'message': 'Finished rewriting resume...'})}\n\n"
                elif "judge_resume" in event:
                    judgement = (
                        event["judge_resume"].get("judgements", [])[-1]
                        if event["judge_resume"].get("judgements")
                        else None
                    )
                    iteration = event["judge_resume"].get("iteration", 1)
                    if judgement:
                        if isinstance(judgement, dict):
                            should_rewrite = judgement.get("should_rewrite", False)
                            req_changes = judgement.get("request_changes", [])
                        else:
                            should_rewrite = getattr(judgement, "should_rewrite", False)
                            req_changes = getattr(judgement, "request_changes", [])

                        if should_rewrite:
                            msg = f"Judge requested changes (Iteration {iteration}). Rewriting again..."
                            if req_changes:
                                msg += f" Feedback: {'; '.join(req_changes)}"
                        else:
                            msg = f"Judge approved rewrite (Iteration {iteration}). Proceeding to PDF generation..."
                        yield f"data: {json.dumps({'event': 'progress', 'step': 'judge_resume', 'message': msg})}\n\n"
                    else:
                        yield f"data: {json.dumps({'event': 'progress', 'step': 'judge_resume', 'message': f'Evaluating rewritten resume (Iteration {iteration})...'})}\n\n"
                elif "rewrite_latex" in event:
                    data = event["rewrite_latex"]
                    latex_code = data.get("latex_code", "")
                    diff_latex_code = data.get("diff_latex_code", "")
                    pdf_base64 = data.get("pdf_base64", "")
                    diff_pdf_base64 = data.get("diff_pdf_base64", "")
                    error_msg = data.get("error", None)

                    resume_id = None
                    if latex_code and not latex_code.startswith("Error:") and not error_msg:
                        try:
                            changes_content = data.get("changes_content")
                            content_dict = None
                            if changes_content:
                                if hasattr(changes_content, "model_dump"):
                                    content_dict = changes_content.model_dump()
                                elif isinstance(changes_content, dict):
                                    content_dict = changes_content

                            resolved_label = resolve_resume_label(label, analysis_data, user)

                            try:
                                template_id_val = initial_state.get("template_id")
                                body = ResumeCreate(
                                    label=resolved_label,
                                    tex_source=latex_code,
                                    jd_snippet=jd,
                                    template_id=(
                                        int(template_id_val)
                                        if template_id_val is not None
                                        else None
                                    ),
                                    pdf_url=pdf_base64,
                                    content=content_dict,
                                )
                                resume = await create_resume(body, user, db)
                                resume_id = resume.id
                                pdf_base64 = (
                                    resume.pdf_url
                                )  # Use the uploaded Cloudinary URL instead!
                            except Exception as db_err:
                                logger.error(
                                    f"Failed to save resume to DB via create_resume: {db_err}"
                                )

                        except Exception as db_err:
                            logger.error(f"Failed to save resume to DB: {db_err}")

                    payload = {
                        "event": "complete",
                        "message": "Done!",
                        "latexCode": latex_code,
                        "diffLatexCode": diff_latex_code,
                        "pdfUrl": pdf_base64,
                        "diffPdfUrl": diff_pdf_base64,
                    }
                    if error_msg:
                        payload["error"] = error_msg
                    if resume_id is not None:
                        payload["resumeId"] = resume_id

                    yield f"data: {json.dumps(payload)}\n\n"

        except Exception as stream_err:
            tb = traceback.format_exc()
            logger.error(f"STREAM ERROR: {tb}")
            err_msg = classify_llm_error(stream_err, dev_mode=settings.dev_mode, tb=tb)
            yield f"data: {json.dumps({'event': 'error', 'message': err_msg})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Modify LaTeX (streaming SSE)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/modify")
@user_limiter.limit("20/minute")
async def modify_latex(
    request: Request,
    req: ModifyRequest,
    user: CurrentUser,
    db: DB,
):
    """
    Modifies raw LaTeX code based on user instruction and streams the updated code.
    """
    try:
        llm = await get_llm_client(db, user=user, provider=req.provider, model=req.model)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initialize model: {e!s}",
        )

    async def modify_stream():
        try:
            system_prompt = (
                "You are an expert LaTeX editor.\n"
                "Your task is to modify the provided LaTeX code according to the user's instructions.\n"
                "CRITICAL RULES:\n"
                "1. Return ONLY valid LaTeX code.\n"
                "2. Do NOT wrap your output in markdown code blocks (e.g. do not write ```latex ... ```). Start directly with the LaTeX code.\n"
                "3. Preserve the structure, design, packages, and formatting of the original LaTeX document. Only change what is requested.\n"
                "4. If the instruction is empty or irrelevant, return the original LaTeX document unchanged."
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=f"Original LaTeX:\n{req.latex_code}\n\nUser Instruction:\n{req.instruction}"
                ),
            ]
            async for chunk in llm.astream(messages):
                yield f"data: {json.dumps({'event': 'chunk', 'text': chunk.content})}\n\n"

        except Exception as stream_err:
            tb = traceback.format_exc()
            logger.error(f"STREAM ERROR: {tb}")
            err_msg = classify_llm_error(stream_err, dev_mode=settings.dev_mode, tb=tb)
            yield f"data: {json.dumps({'event': 'error', 'message': err_msg})}\n\n"

    return StreamingResponse(modify_stream(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Async style-change via background task + Redis Pub/Sub + SSE
# ─────────────────────────────────────────────────────────────────────────────


async def _run_style_change(job_id: int, resume_id: int, style: str, user_id: int):
    """
    Background task: applies an LLM-driven style change to the resume, generates
    a new PDF, persists the results and publishes completion via Redis Pub/Sub.
    """

    async def _set_status(session: AsyncSession, job: ResumeJob, st: JobStatus, **kw):
        job.status = st.value
        for k, v in kw.items():
            setattr(job, k, v)
        session.add(job)
        await session.commit()
        await publish_job_update(job_id, {"status": st.value, **kw})

    async with AsyncSessionLocal() as session:
        # Fetch the job
        r = await session.execute(select(ResumeJob).where(ResumeJob.id == job_id))
        job = r.scalar_one_or_none()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        # Fetch the resume
        rr = await session.execute(select(Resume).where(Resume.id == resume_id))
        resume = rr.scalar_one_or_none()
        if not resume:
            await _set_status(session, job, JobStatus.FAILED, error_message="Resume not found")
            return

        # Fetch the user
        ur = await session.execute(select(User).where(User.id == user_id))
        user_obj = ur.scalar_one_or_none()
        if not user_obj:
            await _set_status(session, job, JobStatus.FAILED, error_message="User not found")
            return

        await _set_status(session, job, JobStatus.RUNNING)

        try:
            # ── 1. Parse the CURRENT tex_source → JSON ────────────────────────
            # We MUST parse from tex_source (not resume.content) because the user
            # may have made tweaks via the AI input box that only updated tex_source.
            # resume.content still holds the old pre-tweak JSON, so using it would
            # silently discard all manual edits.
            #
            # We use parse_resume_prompt (verbatim extraction, no rewriting) so the
            # LLM copies content exactly as-is instead of hallucinating a summary,
            # restoring deleted sections, or changing bullet text.
            llm = await get_llm_client(session, user=user_obj)
            parse_llm = llm.with_structured_output(RewriteResume)
            parse_messages = [
                SystemMessage(content=parse_resume_prompt),
                HumanMessage(content=resume.tex_source or ""),
            ]
            try:
                parsed = await parse_llm.ainvoke(parse_messages)
                if hasattr(parsed, "model_dump") and callable(getattr(parsed, "model_dump", None)):
                    resume.content = parsed.model_dump()  # type: ignore
                elif isinstance(parsed, dict):
                    resume.content = parsed
                session.add(resume)
                await session.commit()
                logger.info(
                    "Style-change job %s: parsed tex_source → JSON successfully.",
                    job_id,
                )
            except Exception as parse_err:
                logger.error(
                    "Style-change job %s: failed to parse tex_source to JSON: %s",
                    job_id,
                    parse_err,
                )
                await _set_status(
                    session,
                    job,
                    JobStatus.FAILED,
                    error_message=f"Failed to parse resume content: {str(parse_err)[:300]}",
                )
                return

            data_dict = copy.deepcopy(resume.content) if resume.content else {}

            # Guard: suppress profile_summary if it is blank so the template never
            # renders an empty Summary section or one that wasn't in the tweaked LaTeX.
            ps = data_dict.get("profile_summary")
            if ps is not None:
                summary_text = ps.get("profile_summary") if isinstance(ps, dict) else str(ps)
                if not summary_text or not str(summary_text).strip():
                    data_dict["profile_summary"] = None

            # ── 2. Fetch template from DB or fallback ─────────────────────────
            t_res = await session.execute(
                select(Template).where(cast(Any, Template.name).ilike(style))
            )
            template_obj = t_res.scalar_one_or_none()
            data_dict["jd"] = resume.jd_snippet

            if template_obj and template_obj.tex_source and template_obj.tex_source.strip():
                new_latex = render_resume_template_from_string(template_obj.tex_source, data_dict)
            else:
                # Fallback to hardcoded ones
                fallback_map = {
                    "modern1": "modern1.tex",
                    "modern2": "modern2.tex",
                    "modern3": "modern3.tex",
                    "jakes resume": "jakes1.tex",
                }
                template_file = fallback_map.get(style.lower().replace(" ", ""), "jakes1.tex")
                new_latex = render_resume_template(template_file, data_dict)

            # ── 2. Compile to PDF and upload ─────────────────────────────────
            pdf_url, preview_url = await save_and_upload(
                latex_code=new_latex,
                user=user_obj,
                resume_id=resume_id,
            )

            # ── 3. Persist new tex_source + pdf_url on the resume row ─────────
            resume.tex_source = new_latex
            resume.pdf_url = pdf_url
            if preview_url:
                resume.preview_url = preview_url

            t_res = await session.execute(
                select(Template).where(cast(Any, Template.name).ilike(style))
            )
            template_obj = t_res.scalar_one_or_none()
            if template_obj:
                resume.template_id = template_obj.id

            resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
            session.add(resume)

            await _set_status(
                session,
                job,
                JobStatus.COMPLETED,
                pdf_url=pdf_url,
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Style-change job %s failed: %s", job_id, tb)
            await _set_status(
                session,
                job,
                JobStatus.FAILED,
                error_message=str(exc)[:500],
            )


@router.post("/{resume_id}/change-style")
@user_limiter.limit("5/minute")
async def change_style(
    resume_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    db: DB,
    style: str = Form(...),
):
    """
    Kick off an async style change for a resume.

    Returns immediately with a ``job_id`` the client can use to open the SSE
    stream at ``GET /resumes/jobs/{job_id}/updates``.
    If the user already has a PENDING or RUNNING job for this resume, the
    existing job_id is returned (rate-limit guard in addition to slowapi).
    """
    # Guard: don't allow more than one active job per resume
    existing = await db.execute(
        select(ResumeJob).where(
            ResumeJob.resume_id == resume_id,
            ResumeJob.user_id == user.id,
            ResumeJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),  # type: ignore
        )
    )
    active_job = existing.scalar_one_or_none()
    if active_job:
        return {
            "job_id": active_job.id,
            "message": "A style change is already in progress for this resume.",
            "status": active_job.status,
        }

    if user.id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User ID missing")

    # Verify the resume belongs to this user
    res = await db.execute(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if not res.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")

    # Create job entry
    job = ResumeJob(
        resume_id=resume_id,
        user_id=user.id,
        style=style,
        status=JobStatus.PENDING.value,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    if job.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create job ID")

    # Publish initial pending status
    await publish_job_update(job.id, {"status": JobStatus.PENDING.value, "resume_id": resume_id})

    # Queue background task
    background_tasks.add_task(_run_style_change, job.id, resume_id, style, user.id)

    return {
        "job_id": job.id,
        "message": "Style change started. You will be notified when it is ready.",
        "status": JobStatus.PENDING.value,
    }


@router.get("/jobs/{job_id}/updates")
async def job_updates(job_id: int, request: Request, user: CurrentUser):
    """
    Server-Sent Events stream for a single style-change job.

    Subscribes to the per-job Redis channel ``resume_job:{job_id}`` and
    forwards every message to the client.  Closes automatically once a
    COMPLETED or FAILED event is received, or when the client disconnects.
    """

    async def event_stream():
        redis = await get_redis()
        pubsub = redis.pubsub()
        channel = f"resume_job:{job_id}"
        await pubsub.subscribe(channel)
        try:
            while True:
                if await request.is_disconnected():
                    break
                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if raw and raw["type"] == "message":
                    data_str = raw["data"]
                    yield f"data: {data_str}\n\n"
                    # Auto-close on terminal states
                    try:
                        payload = json.loads(data_str)
                        if payload.get("status") in (
                            JobStatus.COMPLETED.value,
                            JobStatus.FAILED.value,
                        ):
                            break
                    except Exception:
                        pass
                await asyncio.sleep(0.1)
        finally:
            await pubsub.unsubscribe(channel)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: int, user: CurrentUser, db: DB):
    """Poll endpoint for clients that can't use SSE."""
    result = await db.execute(
        select(ResumeJob).where(ResumeJob.id == job_id, ResumeJob.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return {
        "job_id": job.id,
        "resume_id": job.resume_id,
        "style": job.style,
        "status": job.status,
        "pdf_url": job.pdf_url,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


@router.post("/{resume_id}/sync-content")
async def sync_content(resume_id: int, request: SyncContentRequest, user: CurrentUser, db: DB):
    """
    Parses modified LaTeX back into JSON content to preserve tweaks before style changes.
    """
    # Verify the resume belongs to this user
    res = await db.execute(select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    resume = res.scalar_one_or_none()
    if not resume:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")

    try:
        llm = await get_llm_client(db, user=user)
        # Use parse_resume_prompt (verbatim extraction) instead of a weak "keep as written"
        # instruction — the old prompt lost to the RewriteResume schema field descriptions
        # which encouraged the LLM to add a profile summary, change bullets, etc.
        structured_llm = llm.with_structured_output(RewriteResume)
        messages = [
            SystemMessage(content=parse_resume_prompt),
            HumanMessage(content=request.latex_code),
        ]
        details = await structured_llm.ainvoke(messages)
        if hasattr(details, "model_dump") and callable(getattr(details, "model_dump", None)):
            resume.content = details.model_dump()  # type: ignore
        elif isinstance(details, dict):
            resume.content = details
        resume.tex_source = request.latex_code
        if request.pdf_url:
            resume.pdf_url = request.pdf_url
        resume.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.add(resume)
        await db.commit()
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to sync content: {traceback.format_exc()}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to sync content: {e!s}")
