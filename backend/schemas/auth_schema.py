"""
auth_schema.py
--------------
Schemas for authentication and user profile endpoints.
"""

from pydantic import BaseModel


class SignupBody(BaseModel):
    username: str
    name: str
    email: str
    password: str


class LoginBody(BaseModel):
    email_or_username: str
    password: str


class GoogleExchangeBody(BaseModel):
    code: str


class ProfileUpdate(BaseModel):
    name: str
    email: str
    github: str | None = None
    linkedin: str | None = None
    website: str | None = None
    location: str | None = None
    phone: str | None = None
    raw_resume: str | None = None


class ProfileOut(BaseModel):
    id: int
    username: str
    name: str
    email: str
    github: str | None = None
    linkedin: str | None = None
    website: str | None = None
    location: str | None = None
    phone: str | None = None
    raw_resume: str | None = None


class API_KEY_REQUEST(BaseModel):
    api_provider: str
    api_key: str


class API_KEY_RESPONSE(BaseModel):
    provider: str
    encrypted_key: str
