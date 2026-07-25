import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import bcrypt
import httpx
from jose import JWTError, jwt

from .config import settings

logger = logging.getLogger(__name__)


def hash_password(plain: str) -> str:
    password_bytes = plain.encode("utf-8")
    # Truncate if it exceeds bcrypt's maximum input size of 72 bytes
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        password_bytes = plain.encode("utf-8")
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        return bcrypt.checkpw(password_bytes, hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as e:
        logger.error(f"Error :{e}")
        return None


def google_auth_url(state: str = "") -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
    }
    return f"{settings.google_auth_url}?{urlencode(params)}"


async def exchange_google_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            settings.google_token_url,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            logger.error(f"Google exchange failed: {token_resp.text}")
            token_resp.raise_for_status()
        tokens = token_resp.json()

        user_resp = await client.get(
            settings.google_user_url,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_resp.raise_for_status()
        profile = user_resp.json()

    return {
        "email": profile.get("email"),
        "name": profile.get("name", ""),
        "google_id": profile.get("sub"),
        "picture": profile.get("picture"),
    }
