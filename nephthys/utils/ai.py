from openai import AsyncOpenAI

from nephthys.utils.env import get_environ

DEFAULT_BASE_URL = "https://ai.hackclub.com/proxy/v1"

# HACK_CLUB_AI_* are the old names, still read so existing deployments keep working
api_key = get_environ("AI_API_KEY") or get_environ("HACK_CLUB_AI_API_KEY")
base_url = (
    get_environ("AI_BASE_URL")
    or get_environ("HACK_CLUB_AI_BASE_URL")
    or DEFAULT_BASE_URL
)

ai_client: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=api_key, base_url=base_url) if api_key else None
)
