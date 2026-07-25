import asyncio
import base64
import copy
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Literal, cast

import cloudconvert
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from core.config import settings
from core.llm_throttle import throttle_provider
from schemas.schema import (
    Details,
    JudgeResume,
    ResumeAnalysis,
    ResumeState,
    RewriteResume,
)
from services.llm_service import get_llm_client
from services.renderer import render_resume_template, render_resume_template_from_string
from utils.constants import MAX_REWRITE_ITERATIONS
from utils.diff_engine import apply_diff_to_data
from utils.prompts import (
    extract_details_prompt,
    judge_prompt,
    resume_analysis_prompt,
    rewrite_content_prompt,
)

logger = logging.getLogger(__name__)


class ResumeWorkflowService:
    def __init__(self, cloudconvert_api_key: str | None = None):
        api_key = cloudconvert_api_key or settings.cloudconvert_api_key
        if api_key:
            cloudconvert.configure(api_key=api_key)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ResumeState)  # type: ignore
        graph.add_node("match_jd", self.match_jd)
        graph.add_node("rewrite_resume", self.rewrite_resume)
        graph.add_node("judge_resume", self.judge_rewrite)
        graph.add_node("rewrite_latex", self.rewrite_latex)
        graph.add_edge(START, "match_jd")
        graph.add_edge("match_jd", "rewrite_resume")
        graph.add_edge("rewrite_resume", "judge_resume")
        graph.add_conditional_edges(source="judge_resume", path=self.route_path)
        graph.add_edge("rewrite_latex", END)
        return graph.compile()

    def route_path(self, state: "ResumeState") -> Literal["rewrite_resume", "rewrite_latex"]:
        iteration = int(state.get("iteration", 1))
        judgements = state.get("judgements", [])

        # Process and log the last judgement details if available (important for UI status updates)
        judgement = judgements[-1] if judgements else None
        should_rewrite = False
        req_changes = []
        if judgement:
            if isinstance(judgement, dict):
                should_rewrite = judgement.get("should_rewrite", False)
                req_changes = judgement.get("request_changes", [])
            else:
                should_rewrite = getattr(judgement, "should_rewrite", False)
                req_changes = getattr(judgement, "request_changes", [])

            if should_rewrite:
                logger.info(
                    f"Judge rejected rewrite (iteration {iteration}). {len(req_changes)} changes requested:"
                )
                for _idx, change in enumerate(req_changes):
                    change_str = str(change)
                    truncated = change_str[:150] + "..." if len(change_str) > 150 else change_str
                    logger.info(f"  - {truncated}")
            else:
                logger.info(f"Judge approved rewrite (iteration {iteration}). Proceeding to LaTeX.")

        if not judgements or iteration >= MAX_REWRITE_ITERATIONS:
            logger.info(
                f"Proceeding to rewrite_latex. Iteration: {iteration} (max iterations reached or no judgements)."
            )
            return "rewrite_latex"

        return "rewrite_resume" if should_rewrite else "rewrite_latex"

    def iterate_nested_dict(self, d, parent_key=""):
        for key, value in d.items():
            full_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                yield from self.iterate_nested_dict(value, full_key)
            else:
                yield full_key, value

    async def match_jd(self, state: ResumeState):
        jd = state["jd"]  # type: ignore
        resume = state["resume"]  # type: ignore
        page_count = state.get("page_count")
        pc_str = f"\nOriginal Resume Page Count: {page_count}" if page_count else ""

        current_date = datetime.now().strftime("%B %Y")
        messages = [
            SystemMessage(content=f"Current Date: {current_date}\n\n{resume_analysis_prompt}"),
            HumanMessage(content=f"Job Description:\n{jd}\n\nCandidate Resume:\n{resume}{pc_str}"),
        ]

        try:
            llm = await self._get_llm(state)  # type: ignore
            structured_llm = llm.with_structured_output(ResumeAnalysis)

            try:
                response = await self._invoke_with_retry(
                    structured_llm, messages, provider=state.get("provider")
                )
            except Exception as e:
                logger.error(f"match_jd structured output failed after retries: {e}")
                return {**state, "analysis": None}

            analysis_response = cast(ResumeAnalysis, response)
            analysis = analysis_response.model_dump()
        except Exception as e:
            logger.exception(f"Error in match_jd node: {e}")
            raise

        return {**state, "analysis": analysis}

    async def _get_llm(self, state: "ResumeState", temperature: float | None = None):
        """Helper: build the LLM instance from state config."""
        return await get_llm_client(
            provider=state.get("provider"),
            model=state.get("model"),
            api_key=state.get("api_key"),
            temperature=temperature,
        )

    async def _invoke_with_retry(
        self, structured_llm, messages, max_attempts=3, provider: str | None = None
    ):
        if provider:
            await throttle_provider(provider)

        is_groq = bool(provider and provider.lower().strip() == "groq")
        attempts = max(max_attempts, 5) if is_groq else max_attempts

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(
                multiplier=2 if is_groq else 1,
                min=4 if is_groq else 2,
                max=30 if is_groq else 10,
            ),
            reraise=True,
        ):
            with attempt:
                result = await structured_llm.ainvoke(messages)
                if result is None:
                    raise ValueError("LLM returned None for structured output")
                return result

    async def rewrite_resume(self, state: "ResumeState"):
        iteration = int(state.get("iteration", 0)) + 1
        resume = state["resume"]  # type: ignore
        jd = state["jd"]  # type: ignore
        tone = state["tone"]  # type: ignore
        page_count = state.get("page_count")
        pc_str = f"\nOriginal Resume Page Count: {page_count}" if page_count else ""
        exclude_sections = [
            sec for sec, sec_val in state.get("exclude_sections", {}).items() if sec_val
        ]

        if state.get("analysis") is None:
            return {**state, "changes_content": None, "iteration": iteration}

        try:
            analysis = state["analysis"]  # type: ignore
            if not isinstance(analysis, dict):
                analysis_dict = analysis.model_dump()  # type: ignore
            else:
                analysis_dict = analysis

            analysis_str = json.dumps(analysis_dict, indent=2)

            llm = await self._get_llm(state)

            # ── Call 1: Extract personal details + links only ────────────────
            # Small, focused schema → models handle it reliably every time
            details_obj: Details | None = None
            try:
                details_llm = llm.with_structured_output(Details)
                details_messages = [
                    SystemMessage(content=extract_details_prompt),
                    HumanMessage(content=f"Resume text:\n{resume}"),
                ]
                raw_details = await self._invoke_with_retry(details_llm, details_messages)
                details_obj: Details | None = cast("Details", raw_details)
            except Exception as details_err:
                logger.warning(
                    f"Details extraction failed (will rely on validator fallback): {details_err}"
                )

            # Robust URL fallback extraction from the entire resume text
            if details_obj is not None and isinstance(details_obj, Details):
                for full_url in re.findall(r"https?://[^\s\"\'\>]+", resume):
                    m = re.search(r"https?://(?:www\.)?([\w\-\.]+)", full_url)
                    if m:
                        domain = m.group(1).lower()
                        if domain.endswith((".com", ".org", ".net", ".io")):
                            domain = domain[:-4]

                        if domain not in details_obj.profile_links:
                            details_obj.profile_links[domain] = full_url

            # ── Call 2: Rewrite full content ─────────────────────────────────
            structured_llm = llm.with_structured_output(RewriteResume)

            # If Call 1 succeeded, tell the model the links are already known
            details_hint = ""
            if details_obj is not None and isinstance(details_obj, Details):
                details_hint = (
                    f"\n\n[PRE-EXTRACTED CONTACT INFO — copy these exactly into profile_links, do not change]\n"
                    f"Name: {details_obj.name}\n"
                    f"Links: {details_obj.profile_links}\n"
                )

            judgements = state.get("judgements", [])
            judgement_hint = ""
            if judgements:
                all_requests = []
                for i, j in enumerate(judgements, 1):
                    req = (
                        j.get("request_changes", [])
                        if isinstance(j, dict)
                        else getattr(j, "request_changes", [])
                    )
                    if req:
                        changes_str = "\n- ".join(req)
                        all_requests.append(f"Iteration {i} feedback:\n- {changes_str}")

                if all_requests:
                    history_str = "\n\n".join(all_requests)
                    judgement_hint = (
                        f"\n\n[PREVIOUS FEEDBACK HISTORY TO INCORPORATE]\n"
                        f"You have been asked to revise this resume multiple times. Here is the history of requested changes:\n{history_str}\n"
                        f"Ensure you address ALL unresolved feedback from previous iterations.\n"
                    )

            current_date = datetime.now().strftime("%B %Y")
            messages = [
                SystemMessage(content=f"Current Date: {current_date}\n\n{rewrite_content_prompt}"),
                HumanMessage(
                    content=(
                        f"Job Description:\n{jd}\n\n"
                        f"Candidate Resume:\n{resume}{pc_str}"
                        f"{details_hint}\n"
                        f"{judgement_hint}\n"
                        f"Analysis Report:\n{analysis_str}\n"
                        f"Tone: {tone}\n"
                        f"Exclude Sections: {exclude_sections}\n"
                    )
                ),
            ]

            try:
                raw_response = await self._invoke_with_retry(
                    structured_llm, messages, provider=state.get("provider")
                )
                response = cast(RewriteResume, raw_response)
            except Exception as e:
                logger.error(f"rewrite_resume structured output failed after retries: {e}")
                return {**state, "changes_content": None, "iteration": iteration}

            # If the response has empty profile_links but Call 1 gave us links, merge them
            if (
                details_obj is not None
                and isinstance(details_obj, Details)
                and response.details is not None
                and not response.details.profile_links
            ):
                response.details.profile_links = details_obj.profile_links

            return {**state, "changes_content": response, "iteration": iteration}
        except Exception as e:
            logger.exception(f"Error in rewrite_resume node: {e}")
            raise

    async def judge_rewrite(self, state: "ResumeState"):
        try:
            changes = state.get("changes_content")
            resume = state.get("resume")
            jd = state.get("jd")
            analysis = state.get("analysis")
            page_count = state.get("page_count")
            pc_str = f"\nOriginal Resume Page Count: {page_count}" if page_count else ""

            judgements = state.get("judgements", [])
            judgement_history = ""
            if judgements:
                all_requests = []
                for i, j in enumerate(judgements, 1):
                    req = (
                        j.get("request_changes", [])
                        if isinstance(j, dict)
                        else getattr(j, "request_changes", [])
                    )
                    if req:
                        changes_str = "\n- ".join(req)
                        all_requests.append(f"Iteration {i} requested changes:\n- {changes_str}")

                if all_requests:
                    history_str = "\n\n".join(all_requests)
                    judgement_history = (
                        f"\n\n[YOUR PREVIOUS FEEDBACK HISTORY TO REWRITER]\n"
                        f"You previously evaluated earlier versions and requested the following changes:\n{history_str}\n"
                        f"Please evaluate if the rewriter has addressed your feedback in the new 'Candidate Changed Resume'.\n"
                        f"If they have adequately addressed it or properly omitted skills they shouldn't hallucinate, do not keep requesting the same changes.\n"
                    )

            # Serialize changes to JSON
            changes_str = ""
            if changes:
                if hasattr(changes, "model_dump"):
                    changes_str = json.dumps(changes.model_dump(), indent=2)
                elif isinstance(changes, dict):
                    changes_str = json.dumps(changes, indent=2)
                else:
                    changes_str = str(changes)
            else:
                changes_str = "None (No changes have been generated yet)"

            # Serialize analysis to JSON
            analysis_str = ""
            if analysis:
                if hasattr(analysis, "model_dump"):
                    analysis_str = json.dumps(analysis.model_dump(), indent=2)
                elif isinstance(analysis, dict):
                    analysis_str = json.dumps(analysis, indent=2)
                else:
                    analysis_str = str(analysis)
            else:
                analysis_str = "None"

            current_date = datetime.now().strftime("%B %Y")
            messages = [
                SystemMessage(content=f"Current Date: {current_date}\n\n{judge_prompt}"),
                HumanMessage(
                    content=(
                        f"Job Description:\n{jd}\n\n"
                        f"Candidate Resume:\n{resume}{pc_str}"
                        f"{judgement_history}"
                        f"\n\nCandidate Changed Resume:\n{changes_str}"
                        f"\n\nCandidate Analysis:\n{analysis_str}"
                        f"\n\nRewrite Score: "
                    )
                ),
            ]

            llm = await self._get_llm(state, temperature=0.0)
            structured_llm = llm.with_structured_output(JudgeResume)
            try:
                response = await self._invoke_with_retry(
                    structured_llm, messages, provider=state.get("provider")
                )
            except Exception as e:
                logger.error(f"judge_rewrite structured output failed after retries: {e}")
                return {**state}

            new_judgements = judgements.copy()
            new_judgements.append(response)
            return {**state, "judgements": new_judgements}
        except Exception as e:
            logger.exception(f"Error in judge_rewrite node: {e}")
            raise

    async def latex_to_pdf(self, latex_string: str, filename: str) -> bytes:
        """
        Compile LaTeX locally using native pdflatex/tectonic if available,
        falling back to container compiler (Docker/Podman).
        """

        # Pre-process latex_string to escape '%' inside \href{...} to prevent LaTeX comment errors
        def escape_href_percent(latex_code: str) -> str:
            def repl(match):
                url = match.group(1)
                escaped_url = re.sub(r"(?<!\\)%", r"\%", url)
                return f"\\href{{{escaped_url}}}"

            return re.sub(r"\\href\{([^{}]+)\}", repl, latex_code)

        latex_string = escape_href_percent(latex_string)

        # 1. Check for native pdflatex binary on host PATH (fastest path, ~200ms)
        pdflatex_bin = shutil.which("pdflatex")
        if pdflatex_bin:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tex_file = os.path.join(tmpdir, "resume.tex")
                    pdf_file = os.path.join(tmpdir, "resume.pdf")
                    with open(tex_file, "w", encoding="utf-8") as f:
                        f.write(latex_string)

                    proc = await asyncio.create_subprocess_exec(
                        pdflatex_bin,
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        f"-output-directory={tmpdir}",
                        tex_file,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
                    if proc.returncode == 0 and os.path.exists(pdf_file):
                        with open(pdf_file, "rb") as f:
                            return f.read()
            except Exception as e:
                logger.warning(f"Native pdflatex compile failed, falling back to container: {e}")

        # 2. Container fallback (Docker/Podman)
        cmd = ["docker", "run", "-i", "--rm", "latex-compiler"]
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except Exception:
            cmd[0] = "podman"

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                pdf_bytes, stderr = await asyncio.wait_for(
                    process.communicate(input=latex_string.encode("utf-8")),
                    timeout=30.0,
                )
            except TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                raise Exception("LaTeX compilation timed out after 30.0 seconds")

            if process.returncode != 0:
                raise Exception(
                    f"Container compilation error: {stderr.decode('utf-8', errors='ignore')}"
                )
            return pdf_bytes
        except Exception as e:
            raise Exception(f"LaTeX compilation failed: {e}")

    async def rewrite_latex(self, state: ResumeState):
        suggesting_changes = state.get("changes_content")
        exclude_sections = state.get("exclude_sections", {})

        if suggesting_changes is None:
            return {**state, "latex_code": "Error: No resume content to convert"}

        try:
            # Convert schema to dict
            data_dict = suggesting_changes.model_dump()
            clean_data_dict = copy.deepcopy(data_dict)

            # Apply programmatic diff to inject ** and ~~ tags
            original_resume_text = state.get("resume", "")
            diff_data_dict = apply_diff_to_data(original_resume_text, data_dict)

            # Apply exclude_sections logic by zeroing out section lists/values safely
            if exclude_sections:
                for section in exclude_sections:
                    if section in clean_data_dict:
                        clean_data_dict[section] = (
                            [] if isinstance(clean_data_dict[section], list) else None
                        )
                    if section in diff_data_dict:
                        diff_data_dict[section] = (
                            [] if isinstance(diff_data_dict[section], list) else None
                        )

            # Inject Job Description for project skills optimization/relevance sorting
            jd_text = state.get("jd")
            if jd_text:
                clean_data_dict["jd"] = jd_text
                diff_data_dict["jd"] = jd_text

            template_source = state.get("template_source")
            if template_source and template_source.strip():
                latex_code = render_resume_template_from_string(
                    template_source, clean_data_dict, diff=False
                )
                diff_latex_code = render_resume_template_from_string(
                    template_source, diff_data_dict, diff=True
                )
            else:
                latex_code = render_resume_template("modern1.tex", clean_data_dict, diff=False)
                diff_latex_code = render_resume_template("modern1.tex", diff_data_dict, diff=True)

            try:
                filename = f"{suggesting_changes.details.name.replace(' ', '_')}_resume.pdf"
                diff_filename = (
                    f"{suggesting_changes.details.name.replace(' ', '_')}_resume_diff.pdf"
                )

                # Inject definitions for \added and \deleted macros before parallel compile
                diff_defs = (
                    "\n% Definitions for latexdiff-style tracking\n"
                    "\\usepackage[normalem]{ulem}\n"
                    "\\providecommand{\\added}[1]{{\\color{blue}#1}}\n"
                    "\\providecommand{\\deleted}[1]{{\\color{red}\\sout{#1}}}\n"
                )
                if "\\begin{document}" in diff_latex_code:
                    diff_latex_code = diff_latex_code.replace(
                        "\\begin{document}", f"{diff_defs}\\begin{{document}}"
                    )

                # Compile clean and diff PDFs in parallel to halve wait time
                logger.info("Compiling clean and diff PDFs in parallel...")
                clean_task = self.latex_to_pdf(latex_code, filename)
                diff_task = self.latex_to_pdf(diff_latex_code, diff_filename)
                results = await asyncio.gather(clean_task, diff_task, return_exceptions=True)

                pdf_bytes: bytes | None = results[0] if isinstance(results[0], bytes) else None
                diff_pdf_bytes: bytes | None = results[1] if isinstance(results[1], bytes) else None

                if isinstance(results[0], BaseException):
                    logger.error(f"Failed to compile clean resume: {results[0]}")
                if isinstance(results[1], BaseException):
                    logger.error(f"Failed to compile diff resume: {results[1]}")

                diff_pdf_base64_str = ""
                if diff_pdf_bytes and len(diff_pdf_bytes) >= 100:
                    diff_pdf_base64 = base64.b64encode(diff_pdf_bytes).decode("utf-8")
                    diff_pdf_base64_str = f"data:application/pdf;base64,{diff_pdf_base64}"

                if not pdf_bytes or len(pdf_bytes) < 100:
                    return {
                        **state,
                        "latex_code": latex_code,
                        "diff_latex_code": diff_latex_code,
                        "diff_pdf_base64": diff_pdf_base64_str,
                    }

                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                return {
                    **state,
                    "latex_code": latex_code,
                    "diff_latex_code": diff_latex_code,
                    "pdf_base64": f"data:application/pdf;base64,{pdf_base64}",
                    "diff_pdf_base64": diff_pdf_base64_str,
                }

            except Exception as pdf_error:
                logger.error(f"LaTeX Compilation PDF Error inside rewrite_latex: {pdf_error}")
                return {
                    **state,
                    "latex_code": latex_code,
                    "diff_latex_code": diff_latex_code,
                    "error": str(pdf_error),
                }

        except Exception as e:
            return {
                **state,
                "latex_code": "Error: Failed to generate LaTeX template",
                "error": str(e),
            }
