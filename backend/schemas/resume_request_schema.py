"""
resume_request_schema.py
------------------------
Schemas for resume CRUD API request/response bodies.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from utils.constants import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER


class ResumeCreate(BaseModel):
    label: str
    tex_source: str
    jd_snippet: str | None = None
    template_id: int | None = None
    pdf_url: str | None = None
    content: dict | None = None


class SyncContentRequest(BaseModel):
    latex_code: str
    pdf_url: str | None = None


class ResumeUpdate(BaseModel):
    label: str | None = None
    tex_source: str | None = None
    pdf_url: str | None = None


class ResumeOut(BaseModel):
    id: int
    label: str
    jd_snippet: str | None = None
    template_id: int | None = None
    tex_source: str | None = None
    pdf_url: str | None = None
    preview_url: str | None = None
    created_at: datetime = Field(default=datetime.now())
    updated_at: datetime = Field(default=datetime.now())
    content: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class PaginatedResume(BaseModel):
    resumes: list[ResumeOut]
    skip: int
    limit: int
    total_count: int

    class Config:
        from_attributes = True


class AnalyzeRequest(BaseModel):
    jd: str
    tone: str = Field(default="Professional")
    exclude_sections: dict[str, bool] = Field(default_factory=dict)
    template_id: str = Field(default="jake")
    label: str | None = None


class CompileRequest(BaseModel):
    latex_code: str
    id: int | None = None


class ModifyRequest(BaseModel):
    latex_code: str
    instruction: str
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL


class MaskDetails(BaseModel):
    name: bool | None = True
    email: bool | None = True
    phone: bool | None = True
    location: bool | None = True
    github: bool | None = True
    linkedin: bool | None = True
    leetcode: bool | None = True
    portfolio: bool | None = True
    project_name: bool | None = True
    company_name: bool | None = True
    education: bool | None = True
    latex_code: str | None = None


class TemplateOut(BaseModel):
    id: int
    name: str
    tex_source: str
    preview_url: str | None = None
    is_builtin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedTemplateResponse(BaseModel):
    templates: list[TemplateOut]
    skip: int
    limit: int
    total_count: int

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str
    tex_source: str


class TemplateUpdate(BaseModel):
    name: str
    tex_source: str
