import logging

from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import DB, get_session
from models.models import APIKEYS, UserLLMConfig
from schemas.schema import API_KEY_REQUEST, API_KEY_RESPONSE
from services.auth_service import AuthService, CryptoService
from services.resume_service import CurrentUser
from utils.constants import VALID_PROVIDERS

logger = logging.getLogger(__name__)

load_dotenv()
router = APIRouter(prefix="/setup", tags=["setup"])
crypto = CryptoService()


@router.post("/init")
async def set_api_provider(
    req: API_KEY_REQUEST,
    current_user: CurrentUser,
    db: DB,
):
    api_provider = req.api_provider.strip().lower().replace(" ", "_")
    api_key = req.api_key.strip()

    if api_provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="api provider doesnt exists")

    auth_service = AuthService(db)
    await auth_service.save_api_key(api_provider, api_key, current_user)
    return {"message": "Successfully key added"}


@router.post("/providers")
async def choose_llm_provider(
    current_user: CurrentUser,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_session),
):
    provider = body.get("provider")

    logger.info(f"provider is {provider}")
    if not provider:
        raise HTTPException(status_code=400, detail="Provider is required")

    provider = provider.strip().lower()
    if not provider:
        raise HTTPException(status_code=400, detail="Provider cannot be empty")

    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not supported")

    # PostgreSQL UPSERT — atomic, handles both insert and update correctly.
    stmt = (
        pg_insert(UserLLMConfig)
        .values(
            user_id=current_user.id,
            provider=provider,
            model="",
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "provider": provider,
                "model": "",
            },  # Reset model when switching providers
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": f"Provider set to {provider}"}


@router.post("/models")
async def choose_llm_model(
    request: Request,
    current_user: CurrentUser,
    body: dict = Body(...),
    db: AsyncSession = Depends(get_session),
):
    model = body.get("model")
    provider = body.get("provider")
    logger.info(f"model is {model}, provider is {provider}")

    if not model:
        raise HTTPException(status_code=400, detail="Model is required")
    if not provider:
        raise HTTPException(status_code=400, detail="Provider is required")

    model = model.strip()
    provider = provider.strip().lower()

    if not model:
        raise HTTPException(status_code=400, detail="Model cannot be empty")
    if provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail="Provider not supported")

    # UPSERT: update the single user config row
    stmt = (
        pg_insert(UserLLMConfig)
        .values(
            user_id=current_user.id,
            provider=provider,
            model=model,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={"provider": provider, "model": model},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": f"Model set to {model} for {provider}"}


@router.get("/api-config", response_model=list[API_KEY_RESPONSE])
async def api_config(current_user: CurrentUser, db: AsyncSession = Depends(get_session)):
    api_configs_result = await db.execute(
        select(APIKEYS).where(APIKEYS.user_id == current_user.id)  # type: ignore
    )
    api_configs = api_configs_result.scalars().all()
    return api_configs


@router.get("/api-models")
async def valid_models(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    return await AuthService(db).get_valid_models(current_user)


@router.get("/current-model")
async def current_model(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(UserLLMConfig).where(UserLLMConfig.user_id == current_user.id)  # type: ignore
    )
    config = result.scalars().first()
    if config:
        return {"provider": config.provider, "model": config.model}
    return {"provider": "", "model": ""}
