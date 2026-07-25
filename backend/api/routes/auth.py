import logging
import secrets
from typing import Any

from fastapi import (
    APIRouter,
    Cookie,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse, Response
from sqlmodel import select

from core.config import settings
from core.database import DB
from core.rate_limit import limiter
from core.security import (
    create_access_token,
    exchange_google_code,
    google_auth_url,
    hash_password,
    verify_password,
)
from models import User
from models.models import OAuthCode, naive_utcnow
from schemas.schema import (
    GoogleExchangeBody,
    LoginBody,
    ProfileOut,
    ProfileUpdate,
    SignupBody,
)
from services.resume_service import CurrentUser, autofill_resume_profile
from utils.pdf_extractor import extract_resume_text_and_links

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(request: Request, response: Response, body: SignupBody, db: DB):
    existing = await db.execute(
        select(User).where((User.email == body.email) | (User.username == body.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already taken")

    user = User(
        username=body.username,
        name=body.name,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(user.id) if user.id is not None else ""
    if not access_token:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to generate access token"
        )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax" if settings.dev_mode else "none",
        secure=not settings.dev_mode,
        max_age=3600 * 24 * 7,
    )
    return {"message": "Signup successful"}


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, body: LoginBody, db: DB):
    result = await db.execute(
        select(User).where(
            (User.email == body.email_or_username) | (User.username == body.email_or_username)
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password) or user.id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    access_token = create_access_token(user.id)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax" if settings.dev_mode else "none",
        secure=not settings.dev_mode,
        max_age=3600 * 24 * 7,
    )

    return {"new": False}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(
        key="access_token",
        httponly=True,
        samesite="lax" if settings.dev_mode else "none",
        secure=not settings.dev_mode,
    )
    return {"message": "Logged out successfully"}


@router.get("/google")
async def google_login(response: Response):
    """Redirect browser to Google consent screen with a CSRF-protecting state cookie."""
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(google_auth_url(state=state))
    # HttpOnly + SameSite=Lax keeps the state out of JS and prevents CSRF
    redirect.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        secure=not settings.dev_mode,
        max_age=300,  # 5 minutes — enough time to complete the OAuth flow
    )
    return redirect


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: DB,
    oauth_state: str | None = Cookie(default=None),
):
    """
    Google redirects here with ?code=...&state=...
    Validate the CSRF state before exchanging the code.
    """
    # --- CSRF validation ---
    if not oauth_state or not secrets.compare_digest(state, oauth_state):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid OAuth state — possible CSRF attempt"
        )
    try:
        profile = await exchange_google_code(code)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Failed to exchange Google code")

    result = await db.execute(select(User).where(User.email == profile["email"]))
    user = result.scalar_one_or_none()

    is_new = False
    if not user:
        is_new = True
        user = User(
            username=profile["email"].split("@")[0],
            name=profile["name"],
            email=profile["email"],
            # Hash a random credential so hashed_password is never empty.
            # Google-authed users cannot log in via password; this is intentional.
            hashed_password=hash_password(secrets.token_hex(32)),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate user ID",
        )

    exchange_code = secrets.token_urlsafe(32)
    db.add(OAuthCode(code=exchange_code, user_id=user.id, is_new=is_new))
    await db.commit()

    return RedirectResponse(url=f"{settings.frontend_url}/login?code={exchange_code}")


@router.post("/google/exchange")
@limiter.limit("5/minute")
async def exchange_google(request: Request, response: Response, body: GoogleExchangeBody, db: DB):
    result = await db.execute(select(OAuthCode).where(OAuthCode.code == body.code))
    oauth_code = result.scalar_one_or_none()
    if not oauth_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired authorization code")

    # Check expiration (e.g. 1 minute)
    age = (naive_utcnow() - oauth_code.created_at).total_seconds()
    if age > 60:
        await db.delete(oauth_code)
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Authorization code expired")

    access_token = create_access_token(oauth_code.user_id)
    is_new = oauth_code.is_new

    # Delete code to prevent reuse
    await db.delete(oauth_code)
    await db.commit()

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax" if settings.dev_mode else "none",
        secure=not settings.dev_mode,
        max_age=3600 * 24 * 7,
    )

    return {"new": is_new}


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: CurrentUser):
    return user


@router.put("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: DB):
    user.name = body.name
    user.email = body.email
    user.github = body.github
    user.linkedin = body.linkedin
    user.website = body.website
    user.location = body.location
    user.phone = body.phone
    user.raw_resume = body.raw_resume

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/profile/autofill", response_model=dict[str, Any])
async def autofill_profile(
    user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
):
    try:
        resume_text, _ = await extract_resume_text_and_links(file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not resume_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded PDF is empty or could not be parsed.",
        )

    try:
        return await autofill_resume_profile(resume_text, user=user, db=db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse resume details: {e!s}",
        )
