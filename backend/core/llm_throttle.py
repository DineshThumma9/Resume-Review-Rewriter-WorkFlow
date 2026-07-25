import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Minimum interval (in seconds) between requests per provider.
# Providers with high rate limits (google_genai, mistralai, openai, anthropic) are omitted (0s delay).
PROVIDER_THROTTLE_INTERVALS: dict[str, float] = {
    "groq": 2.5,  # Groq free tier has strict RPM/TPM limits
    "huggingface": 2.0,
}

_provider_last_call: dict[str, float] = {}
_provider_locks: dict[str, asyncio.Lock] = {}


def _get_lock(provider: str) -> asyncio.Lock:
    if provider not in _provider_locks:
        _provider_locks[provider] = asyncio.Lock()
    return _provider_locks[provider]


async def throttle_provider(provider: str | None) -> None:
    """
    Applies selective rate-limiting delay for providers with strict rate limits (e.g. Groq).
    Providers with high limits (Google, Mistral, OpenAI, Anthropic) execute immediately without delay.
    """
    if not provider:
        return

    provider_clean = provider.lower().strip()
    interval = PROVIDER_THROTTLE_INTERVALS.get(provider_clean, 0.0)

    if interval <= 0.0:
        return

    lock = _get_lock(provider_clean)
    async with lock:
        now = time.monotonic()
        last_call = _provider_last_call.get(provider_clean, 0.0)
        elapsed = now - last_call

        if elapsed < interval:
            wait_time = interval - elapsed
            logger.info(
                "Throttling request for '%s': pausing for %.2fs to respect rate limits...",
                provider_clean,
                wait_time,
            )
            await asyncio.sleep(wait_time)

        _provider_last_call[provider_clean] = time.monotonic()
