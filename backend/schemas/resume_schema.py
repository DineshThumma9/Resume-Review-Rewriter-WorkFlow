"""
resume_schema.py
----------------
Schemas directly related to the AI resume workflow: parsing, rewriting, judging.
"""

import re
from typing import Any, TypedDict

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)


class ResumeAnalysis(BaseModel):
    score: int = Field(
        description="How well resume scores against job description (0-100)",
        ge=0,
        le=100,
    )
    match: bool = Field(
        description="Does user's skill set justify or align with the job description domain"
    )
    match_explanation: str = Field(
        description="Detailed explanation of how the resume matches the job description",
        default="",
    )
    missing_keywords: list[str] = Field(
        description="Flat list of simple keyword strings included in job description but missing in resume.",
        default_factory=list,
    )
    negative_points: list[str] = Field(
        description=(
            "List of specific weaknesses holding the resume back. "
            "Each item must be a flat, single-level text block. "
            "DO NOT use nested lists, sub-bullets, or multi-level indentation. "
            "Format sub-points as flat paragraphs or inline text."
        ),
        default_factory=list,
    )
    potential_improvements: list[str] = Field(
        description=(
            "List of specific suggestions to improve the resume. "
            "Each item must be a flat, single-level text block. "
            "DO NOT use nested lists, sub-bullets, or multi-level indentation. "
            "Format examples, rewrites, or sub-points as flat paragraphs or inline text, or use blockquotes (starting with '>') for code/rewrites."
        ),
        default_factory=list,
    )
    resume_quality: str = Field(
        description="Overall quality of the resume in terms of structure, readability, and ATS-friendliness",
        default="",
    )
    urgency: str | None = Field(
        description="If deadline is mentioned, urgency to submit from current date and time",
        default=None,
    )
    company_name: str | None = Field(
        description="Extract the target company name from the job description if present, otherwise default to 'Company'",
        default="Company",
    )

    @model_validator(mode="before")
    @classmethod
    def clean_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pi = data.get("potential_improvements")
            if isinstance(pi, list):
                cleaned = []
                for item in pi:
                    val = ""
                    if isinstance(item, dict):
                        val = (
                            item.get("action")
                            or item.get("improvement")
                            or item.get("text")
                            or (next(iter(item.values())) if item.values() else "")
                        )
                    else:
                        val = str(item)

                    val_str = str(val).strip()
                    # Detect misplaced resume_quality block
                    if (
                        val_str.startswith("resume_quality:")
                        or "Structure & Readability" in val_str
                    ):
                        if not data.get("resume_quality"):
                            # Strip the "resume_quality:" prefix and quotes if any
                            cleaned_quality = re.sub(r"^resume_quality:\s*['\"]?\s*", "", val_str)
                            if (
                                cleaned_quality.startswith("'") and cleaned_quality.endswith("'")
                            ) or (
                                cleaned_quality.startswith('"') and cleaned_quality.endswith('"')
                            ):
                                cleaned_quality = cleaned_quality[1:-1]
                            data["resume_quality"] = cleaned_quality.strip()
                        continue
                    cleaned.append(val_str)
                data["potential_improvements"] = cleaned
            np = data.get("negative_points")
            if isinstance(np, list):
                cleaned = []
                for item in np:
                    val = ""
                    if isinstance(item, dict):
                        val = (
                            item.get("point")
                            or item.get("issue")
                            or item.get("text")
                            or (next(iter(item.values())) if item.values() else "")
                        )
                    else:
                        val = str(item)
                    cleaned.append(str(val).strip())
                data["negative_points"] = cleaned
        return data


class Project(BaseModel):
    """Individual project details"""

    name: str | None = Field(description="Project name/title", default="")
    description: str | None = Field(description="Brief project description", default="")
    date: str | None = Field(description="Date or duration of the project", default="")
    link: str | None = Field(description="URL or link to the project", default="")
    technologies: list[str] = Field(
        description="Technologies/tools used in the project", default_factory=list
    )
    highlights: list[str] = Field(
        description="Key achievements or bullet points", default_factory=list
    )


class Education(BaseModel):
    institution: str | None = Field(default="", description="Institution name")
    location: str | None = Field(default="", description="Location of the institution")
    year: str | None = Field(default="", description="Year of education")
    gpa: str | None = Field(default="", description="GPA of education")
    course: str | None = Field(default="", description="Course name")


class Experience(BaseModel):
    company: str | None = Field(default="", description="Company name")
    location: str | None = Field(default="", description="Location of the company")
    role: str | None = Field(default="", description="Role/Position held")
    duration: str | None = Field(default="", description="Duration of employment")
    responsibilities: list[str] = Field(
        description="Key responsibilities and achievements", default_factory=list
    )


class Skill(BaseModel):
    category: str | None = Field(
        default="",
        description="Skill category name (e.g., 'Programming Languages', 'Frameworks', 'Tools')",
    )
    skills: list[str] = Field(
        description="List of specific skills in this category (e.g., ['Python', 'Java', 'C++'])"
    )


class ProfileSummary(BaseModel):
    profile_summary: str | None = Field(
        default="",
        description=(
            "Professional summary/objective. Rewrite to be ATS-optimized and concise. "
            "MUST be shorter than or equal to the original in word count. "
            "Do NOT expand it into multiple sentences if the original was one sentence."
        ),
    )


class Details(BaseModel):
    name: str = Field(description="Full name of the candidate")
    profile_links: dict[str, str | None] = Field(
        description=(
            "Dictionary of ALL links and contact info found in the resume. "
            "Keys should be the platform name (e.g., 'github', 'linkedin', 'phone', 'email', "
            "'gitlab', 'medium', 'hackerrank', 'portfolio', 'website', 'location'). "
            "Values are FULL URLs or raw values (e.g., '+91XXXXXXXXXX', 'user@email.com', "
            "'https://github.com/username'). "
            "Scan the ENTIRE resume text for any profile links (GitHub, LinkedIn, GitLab, LeetCode, etc), "
            "mailto:, http/https links, phone numbers, and email addresses. "
            "If a field is not found, set it to null — do NOT omit the key. "
            "NEVER leave this dict empty if the resume has any links or contact info."
        ),
        default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def extract_links_fallback(cls, data: Any) -> Any:
        """If LLM left profile_links empty/incomplete, regex-scan any raw text fields to fill gaps."""
        if not isinstance(data, dict):
            return data
        links: dict[str, str | None] = data.get("profile_links") or {}
        normalized_links: dict[str, str | None] = {}
        for k, v in links.items():
            if not v:
                continue
            k_lower = k.lower()
            if k_lower.startswith("http") or "." in k_lower:
                m = re.search(r"https?://(?:www\.)?([\w\-\.]+)", v)
                if m:
                    domain = m.group(1).lower()
                    for ext in (".com", ".org", ".net", ".io"):
                        domain = domain.removesuffix(ext)
                    normalized_links[domain] = v
                else:
                    normalized_links[k_lower] = v
            else:
                normalized_links[k_lower] = v
        links = normalized_links
        raw_text = " ".join(str(v) for v in data.values() if isinstance(v, str))

        def _first(pattern: str, text: str) -> str | None:
            m = re.search(pattern, text, re.IGNORECASE)
            return m.group(0) if m else None

        urls = re.findall(r"https?://(?:www\.)?([\w\-\.]+)[/\w\-\.\?\=\&\%]*", raw_text)
        for domain in urls:
            for ext in (".com", ".org", ".net", ".io"):
                domain = domain.removesuffix(ext)
            key = domain.lower()
            if key not in links:
                match = re.search(
                    r"https?://(?:www\.)?" + re.escape(domain) + r"[a-zA-Z]{0,4}[/\w\-\.\?\=\&\%]*",
                    raw_text,
                )
                if match:
                    links[key] = match.group(0)
        if not links.get("phone"):
            phone = _first(r"(?:\+91[\s\-]?)?[6-9]\d{9}|\+?\d[\d\s\-\.]{8,14}\d", raw_text)
            if phone:
                links["phone"] = phone.strip()
        if not links.get("email"):
            email = _first(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", raw_text)
            if email:
                links["email"] = email
        data["profile_links"] = links
        return data

    @property
    def contact(self) -> str | None:
        return self.profile_links.get("phone") or ""

    @contact.setter
    def contact(self, val: str | None):
        self.profile_links["phone"] = val

    @property
    def email(self) -> str | None:
        return self.profile_links.get("email") or ""

    @email.setter
    def email(self, val: str | None):
        self.profile_links["email"] = val

    @property
    def other_links(self) -> dict[str, str]:
        return {
            k: v
            for k, v in self.profile_links.items()
            if v and k.lower() not in ["email", "phone", "location", "contact"]
        }

    @property
    def github(self) -> str | None:
        return self.profile_links.get("github") or ""

    @github.setter
    def github(self, val: str | None):
        self.profile_links["github"] = val

    @property
    def linkedin(self) -> str | None:
        return self.profile_links.get("linkedin") or ""

    @linkedin.setter
    def linkedin(self, val: str | None):
        self.profile_links["linkedin"] = val

    @property
    def leetcode(self) -> str | None:
        return self.profile_links.get("leetcode") or ""

    @leetcode.setter
    def leetcode(self, val: str | None):
        self.profile_links["leetcode"] = val

    @property
    def codechef(self) -> str | None:
        return self.profile_links.get("codechef") or ""

    @codechef.setter
    def codechef(self, val: str | None):
        self.profile_links["codechef"] = val

    @property
    def portfolio(self) -> str | None:
        return self.profile_links.get("portfolio") or self.profile_links.get("website") or ""

    @portfolio.setter
    def portfolio(self, val: str | None):
        self.profile_links["portfolio"] = val

    @property
    def location(self) -> str | None:
        return self.profile_links.get("location") or ""

    @location.setter
    def location(self, val: str | None):
        self.profile_links["location"] = val

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "profile_links": self.profile_links,
            "contact": self.contact,
            "email": self.email,
            "github": self.github,
            "linkedin": self.linkedin,
            "leetcode": self.leetcode,
            "codechef": self.codechef,
            "portfolio": self.portfolio,
            "location": self.location,
        }


class RewriteResume(BaseModel):
    """Structured content for rewritten resume"""

    profile_summary: ProfileSummary | None = Field(description="Professional Summary")
    details: Details | None = Field(description="Personal details")
    education: list[Education] | None = Field(
        description="List of education entries (must match Education schema precisely)",
        default=None,
    )
    experience: list[Experience] | None = Field(
        description="List of work experiences (must match Experience schema precisely)",
        default=None,
    )
    technical_skills: list[Skill] | None = Field(
        description="List of technical skills categorized (e.g., 'Languages: Python, Java')",
        default=None,
    )
    projects: list[Project] | None = Field(
        description="List of projects (must match Project schema precisely)",
        default=None,
    )
    coursework: list[str] | None = Field(
        description="List of relevant coursework or academic projects as strings",
        default=None,
    )
    achievements: list[str] | None = Field(
        description=(
            "Achievements, awards, competitive programming stats, and certifications. Do NOT include open source contributions here — those go in open_source. Do NOT include hackathons — those go in hackathons."
        ),
        default=None,
        validation_alias=AliasChoices("achievements", "achivements"),
    )
    open_source: list[str] | None = Field(
        description=(
            "Open source contributions ONLY — merged PRs, filed issues, maintainer credits. Each entry is one contribution as a string. Do NOT include hackathons, certificates, or LeetCode stats here."
        ),
        default=None,
    )
    internships: list[Experience] | None = Field(
        description="List of internships (must match Experience schema precisely)",
        default=None,
    )
    hackathons: list[str] | None = Field(
        description="List of hackathons participated as strings", default=None
    )
    certifications: list[str] | None = Field(
        description="List of certifications obtained as strings", default=None
    )
    extracurricular_activities: list[str] | None = Field(
        description="List of extracurricular activities as strings",
        default=None,
        validation_alias=AliasChoices("extracurricular_activities", "extracircular_activities"),
    )

    @property
    def achivements(self) -> list[str] | None:
        return self.achievements

    @achivements.setter
    def achivements(self, value: list[str] | None) -> None:
        self.achievements = value

    @property
    def extracircular_activities(self) -> list[str] | None:
        return self.extracurricular_activities

    @extracircular_activities.setter
    def extracircular_activities(self, value: list[str] | None) -> None:
        self.extracurricular_activities = value

    @field_validator("profile_summary", mode="before")
    @classmethod
    def clean_profile_summary(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"profile_summary": data}
        return data

    @field_validator("technical_skills", mode="before")
    @classmethod
    def clean_technical_skills(cls, ts: Any) -> Any:
        if ts is None:
            return ts
        if isinstance(ts, dict):
            if "technical_skills" in ts:
                ts = ts["technical_skills"]
            elif "skills" in ts:
                ts = ts["skills"]
            else:
                ts = [
                    {
                        "category": str(k),
                        "skills": val if isinstance(val, list) else [str(val)],
                    }
                    for k, val in ts.items()
                ]
        if isinstance(ts, list):
            cleaned_ts = []
            for item in ts:
                if isinstance(item, dict):
                    category = item.get("category") or item.get("name") or ""
                    skills = item.get("skills") or item.get("values") or []
                    if isinstance(skills, str):
                        skills = [s.strip() for s in skills.split(",") if s.strip()]
                    elif not isinstance(skills, list):
                        skills = [str(skills)]
                    cleaned_ts.append(
                        {"category": str(category), "skills": [str(s) for s in skills]}
                    )
                else:
                    cleaned_ts.append({"category": "Skills", "skills": [str(item)]})
            return cleaned_ts
        return ts

    @field_validator(
        "open_source",
        "coursework",
        "achievements",
        "hackathons",
        "certifications",
        "extracurricular_activities",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def clean_list_of_strings(cls, val: Any) -> Any:
        if val is None:
            return val
        if isinstance(val, dict):
            for sub_val in val.values():
                if isinstance(sub_val, list):
                    val = sub_val
                    break
            else:
                val = list(val.values())
        if isinstance(val, list):
            cleaned_list = []
            for item in val:
                if isinstance(item, dict):
                    name = (
                        item.get("name")
                        or item.get("title")
                        or item.get("description")
                        or item.get("project")
                    )
                    if name:
                        cleaned_list.append(str(name))
                    else:
                        parts = []
                        for sub_item_val in item.values():
                            if isinstance(sub_item_val, list):
                                parts.extend(str(x) for x in sub_item_val)
                            else:
                                parts.append(str(sub_item_val))
                        cleaned_list.append(" - ".join(parts))
                elif isinstance(item, list):
                    cleaned_list.append(", ".join(str(x) for x in item))
                else:
                    cleaned_list.append(str(item))
            return cleaned_list
        elif isinstance(val, str):
            return [val]
        return val

    @model_validator(mode="after")
    def deduplicate_achievements(self) -> "RewriteResume":
        if self.open_source and self.achivements:
            os_set = {str(item).lower().strip() for item in self.open_source}
            self.achivements = [
                ach for ach in self.achivements if str(ach).lower().strip() not in os_set
            ]
        return self


class JudgeResume(BaseModel):
    request_changes: list[str] = Field(
        description="If should_rewrite is true, list the specific, actionable changes the rewriter must make. If should_rewrite is false, this must be an empty list."
    )
    should_rewrite: bool = Field(
        description="True if the rewritten resume has false info, forced keywords, or still has significant room for improvement. False if it is optimal and ready."
    )

    @model_validator(mode="before")
    @classmethod
    def fix_typos(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "should_rewite" in data and "should_rewrite" not in data:
                data["should_rewrite"] = data.pop("should_rewite")
            if "request_changes" in data:
                req_changes = data["request_changes"]
                if isinstance(req_changes, list):
                    cleaned = []
                    for item in req_changes:
                        if isinstance(item, list):
                            cleaned.extend([str(x) for x in item])
                        elif isinstance(item, bool):
                            continue
                        elif item is not None:
                            cleaned.append(str(item))
                    data["request_changes"] = cleaned
                elif isinstance(req_changes, str):
                    data["request_changes"] = [req_changes]
        return data


class ResumeState(TypedDict, total=False):
    jd: str
    resume: str
    page_count: int | None
    analysis: Any | None
    changes_content: Any | None
    latex_code: str
    diff_latex_code: str
    tone: str
    model: str
    provider: str
    api_key: str
    exclude_sections: dict[str, bool]
    output_path: str
    judgements: list[Any]
    pdf_base64: str
    diff_pdf_base64: str
    template_source: str
    template_id: int | None
    error: str | None
    iteration: int


class BulletRewriteOutput(BaseModel):
    id: str = Field(description="The unique ID matching the input bullet point (e.g. 'exp_0_1')")
    rewritten_text: str = Field(
        description="Optimized, ATS-friendly text incorporating keywords naturally"
    )


class BatchedRewriteResponse(BaseModel):
    rewritten_bullets: list[BulletRewriteOutput] = Field(default_factory=list)
    rewritten_summary: str | None = Field(
        default=None,
        description="Optimized profile summary/objective. Null if summary was not provided in input.",
    )
    optimized_skills: list[Skill] | None = Field(
        default=None, description="Optimized skills list. Null if not provided."
    )
