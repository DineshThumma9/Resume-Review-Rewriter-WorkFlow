import logging

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models.models import User, UserLLMConfig
from services.auth_service import AuthService
from utils.constants import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER

logger = logging.getLogger(__name__)


async def get_llm_client(
    db: AsyncSession | None = None,
    user: User | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """
    Initializes and returns a LangChain chat model.
    If provider/model are not provided, it will attempt to fetch them from the user's config
    or fallback to defaults.
    If api_key is not provided, it will attempt to fetch the user's custom key or fallback
    to system settings.
    """

    # 1. Resolve Provider and Model
    if db and user and (not provider or not model):
        result = await db.execute(select(UserLLMConfig).where(UserLLMConfig.user_id == user.id))
        config = result.scalars().first()
        if config:
            provider = provider or config.provider
            model = model or config.model

    resolved_provider = provider or DEFAULT_LLM_PROVIDER
    resolved_model = model or DEFAULT_LLM_MODEL

    # 2. Resolve API Key
    resolved_api_key = api_key
    if not resolved_api_key and db and user:
        try:
            auth_service = AuthService(db)
            resolved_api_key = await auth_service.get_api_key(resolved_provider, user)
        except Exception as e:
            logger.debug(f"Could not fetch user API key for {resolved_provider}: {e}")

    if not resolved_api_key:
        provider_keys = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "google_genai": settings.google_api_key,
            "groq": settings.groq_api_key,
            "mistralai": settings.mistral_api_key,
            "openrouter": settings.openrouter_api_key,
            "huggingface": settings.huggingface_api_key,
        }
        resolved_api_key = provider_keys.get(resolved_provider)

    # 3. Initialize Model
    llm_kwargs = {}
    if resolved_api_key:
        llm_kwargs["api_key"] = resolved_api_key
    if temperature is not None:
        llm_kwargs["temperature"] = temperature

    try:
        llm = init_chat_model(resolved_model, model_provider=resolved_provider, **llm_kwargs)
        return llm
    except Exception as e:
        logger.error(
            f"Failed to initialize model '{resolved_model}' with provider '{resolved_provider}': {e}"
        )
        raise
