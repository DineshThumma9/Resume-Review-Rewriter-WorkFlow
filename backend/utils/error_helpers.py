"""
utils/error_helpers.py
-----------------------
Shared LLM/API error classification used for SSE error events.
Keeps error-message formatting consistent across all streaming endpoints.
"""


def classify_llm_error(error: Exception, dev_mode: bool = False, tb: str | None = None) -> str:
    """
    Map a raw exception from an LLM call to a user-facing error string.
    Checks standard attributes (like status_code or code) used by
    OpenAI, Mistral, Gemini, Groq, and HTTPX to provide accurate messages.
    """
    status_code = None

    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(error, "code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)

    # Convert status_code to integer if possible
    if status_code is not None:
        try:
            status_code = int(status_code)
        except (ValueError, TypeError):
            status_code = None

    if status_code == 429:
        err_msg = "API Error: You have exceeded your API quota or rate limit. Please check your billing or plan."
    elif status_code == 402:
        err_msg = "API Error: Payment is required. Please check your billing details on your provider's dashboard."
    elif status_code in (401, 403):
        err_msg = (
            "API Error: Invalid or unauthorized API key. Please check your API key in Settings."
        )
    else:
        # Fallback to string heuristics for cases where status code isn't easily extracted
        msg = str(error)
        if (
            "429" in msg
            or "RESOURCE_EXHAUSTED" in msg
            or "quota" in msg.lower()
            or "rate limit" in msg.lower()
        ):
            err_msg = "API Error: You have exceeded your API quota or rate limit. Please check your billing or plan."
        elif (
            "402" in msg or "payment required" in msg.lower() or "insufficient_quota" in msg.lower()
        ):
            err_msg = "API Error: Payment is required. Please check your billing details on your provider's dashboard."
        elif (
            "401" in msg
            or "403" in msg
            or "API_KEY" in msg
            or "unauthorized" in msg.lower()
            or "invalid api key" in msg.lower()
        ):
            err_msg = (
                "API Error: Invalid or unauthorized API key. Please check your API key in Settings."
            )
        else:
            err_msg = f"Internal Error: {msg}"
            if not dev_mode:
                err_msg += "\nPlease try again or contact support."

    if dev_mode and tb:
        err_msg += f"\nTraceback:\n{tb}"
    return err_msg
