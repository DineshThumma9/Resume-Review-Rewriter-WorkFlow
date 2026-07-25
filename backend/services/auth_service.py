import logging
from collections import defaultdict

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models.models import APIKEYS, User
from utils.constants import _VALIDATION_URLS, STATIC_MODELS
from utils.http_client import get_http_client

logger = logging.getLogger(__name__)


class CryptoService:
    def __init__(self):
        self.fernet = Fernet(settings.fernet_key)

    def encrypt(self, key: str) -> str:
        return self.fernet.encrypt(key.encode()).decode()

    def decrypt(self, key: str) -> str:
        return self.fernet.decrypt(key.encode()).decode()


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.crypto = CryptoService()

    async def get_api_key(self, provider: str, user: User) -> str:
        result = await self.db.execute(
            select(APIKEYS).where(
                APIKEYS.user_id == user.id,
                APIKEYS.provider == provider,
            )
        )
        api_key = result.scalars().first()
        if not api_key:
            raise HTTPException(status_code=404, detail=f"API KEY NOT FOUND: {provider}")
        return self.crypto.decrypt(api_key.encrypted_key)

    async def _validate_api_key(self, provider: str, api_key: str) -> tuple[bool, str]:

        url = _VALIDATION_URLS.get(provider)
        if not url:
            return True, ""  # Unknown provider — don't block

        client = get_http_client()
        try:
            if provider == "google_genai":
                r = await client.get(f"{url}?key={api_key}")
            elif provider == "anthropic":
                r = await client.get(
                    url,
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
            else:
                r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.TimeoutException:
            logger.warning(f"Key validation timeout for {provider} (5s)")
            return True, ""
        except Exception as e:
            logger.warning(f"Key validation network error for {provider}: {e}")
            return True, ""

        if r.status_code in (401, 403):
            return False, f"API key rejected by {provider} (HTTP {r.status_code})"
        return True, ""

    async def save_api_key(self, provider: str, api_key: str, user: User):
        is_valid, err_msg = await self._validate_api_key(provider, api_key)
        if not is_valid:
            logger.warning(f"Invalid API key rejected for {provider}: {err_msg}")
            raise HTTPException(
                status_code=422,
                detail={"error_type": "invalid_api_key", "message": err_msg},
            )

        encrypted_key = self.crypto.encrypt(api_key)

        existing_result = await self.db.execute(
            select(APIKEYS).where(
                APIKEYS.user_id == user.id,
                APIKEYS.provider == provider,
            )
        )
        existing = existing_result.scalars().first()

        if existing:
            existing.encrypted_key = encrypted_key
        else:
            new_key = APIKEYS(
                user_id=int(user.id),  # type: ignore
                provider=provider,
                encrypted_key=encrypted_key,
            )
            self.db.add(new_key)
            logger.info(f"Added new key for {provider}")
        await self.db.commit()

    async def get_all_api_keys(self, user: User) -> dict[str, str]:
        result = await self.db.execute(select(APIKEYS).where(APIKEYS.user_id == user.id))
        return {
            entry.provider: self.crypto.decrypt(entry.encrypted_key)
            for entry in result.scalars().all()
        }

    async def get_valid_models(self, user: User) -> dict[str, list[str]]:
        """Return available models by fetching them dynamically from provider endpoints."""
        valid_models: dict[str, list[str]] = defaultdict(list)

        # Check centralized environment keys
        provider_keys = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "google_genai": settings.google_api_key,
            "groq": settings.groq_api_key,
            "mistralai": settings.mistral_api_key,
            "openrouter": settings.openrouter_api_key,
            "huggingface": settings.huggingface_api_key,
        }

        # Retrieve user configured database keys
        user_keys = await self.get_all_api_keys(user)

        async with httpx.AsyncClient(timeout=4.0) as client:
            for provider in STATIC_MODELS:
                key = provider_keys.get(provider) or user_keys.get(provider)
                if not key:
                    continue

                url = _VALIDATION_URLS.get(provider)
                if not url:
                    valid_models[provider] = STATIC_MODELS[provider]
                    continue

                try:
                    if provider == "google_genai":
                        r = await client.get(f"{url}?key={key}")
                        if r.status_code == 200:
                            data = r.json()
                            models_list = [m["name"].split("/")[-1] for m in data.get("models", [])]
                            if models_list:
                                valid_models[provider] = [
                                    m for m in models_list if "gemini" in m.lower()
                                ]
                            else:
                                valid_models[provider] = STATIC_MODELS[provider]
                        else:
                            valid_models[provider] = STATIC_MODELS[provider]
                    elif provider == "anthropic":
                        valid_models[provider] = STATIC_MODELS[provider]
                    else:
                        headers = {"Authorization": f"Bearer {key}"}
                        r = await client.get(url, headers=headers)
                        if r.status_code == 200:
                            data = r.json()
                            models_list = [m["id"] for m in data.get("data", [])]
                            if models_list:
                                valid_models[provider] = models_list[:15]  # Cap list size
                            else:
                                valid_models[provider] = STATIC_MODELS[provider]
                        else:
                            valid_models[provider] = STATIC_MODELS[provider]
                except Exception as e:
                    logger.warning(f"Failed to dynamically fetch models for {provider}: {e}")
                    valid_models[provider] = STATIC_MODELS[provider]

        if not valid_models:
            valid_models["google_genai"] = STATIC_MODELS["google_genai"]

        return dict(valid_models)
