"""
schema.py — backward-compatible re-export shim
------------------------------------------------
All schemas are now split into focused domain modules:
  - schemas.resume_schema   → AI workflow models (RewriteResume, Details, JudgeResume, …)
  - schemas.auth_schema     → Authentication & user profile models
  - schemas.resume_request_schema → Resume CRUD request/response models

This file re-exports everything so existing `from schemas.schema import X` imports
continue to work without modification.
"""

from schemas.auth_schema import (
    API_KEY_REQUEST,
    API_KEY_RESPONSE,
    GoogleExchangeBody,
    LoginBody,
    ProfileOut,
    ProfileUpdate,
    SignupBody,
)
from schemas.resume_request_schema import (
    AnalyzeRequest,
    CompileRequest,
    MaskDetails,
    ModifyRequest,
    PaginatedResume,
    PaginatedTemplateResponse,
    ResumeCreate,
    ResumeOut,
    ResumeUpdate,
    SyncContentRequest,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from schemas.resume_schema import (
    BatchedRewriteResponse,
    BulletRewriteOutput,
    Details,
    Education,
    Experience,
    JudgeResume,
    ProfileSummary,
    Project,
    ResumeAnalysis,
    ResumeState,
    RewriteResume,
    Skill,
)

__all__ = [
    # auth_schema
    "API_KEY_REQUEST",
    "API_KEY_RESPONSE",
    # resume_request_schema
    "AnalyzeRequest",
    # resume_schema
    "BatchedRewriteResponse",
    "BulletRewriteOutput",
    "CompileRequest",
    "Details",
    "Education",
    "Experience",
    "GoogleExchangeBody",
    "JudgeResume",
    "LoginBody",
    "MaskDetails",
    "ModifyRequest",
    "PaginatedResume",
    "PaginatedTemplateResponse",
    "ProfileOut",
    "ProfileSummary",
    "ProfileUpdate",
    "Project",
    "ResumeAnalysis",
    "ResumeCreate",
    "ResumeOut",
    "ResumeState",
    "ResumeUpdate",
    "RewriteResume",
    "SignupBody",
    "Skill",
    "SyncContentRequest",
    "TemplateCreate",
    "TemplateOut",
    "TemplateUpdate",
]
