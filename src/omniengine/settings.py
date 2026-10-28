"""Where the OpenAI-compatible server is and how to call it, read from the environment.

The values come from the same .env that docker compose reads, so a check always talks to the
server this repo starts. Agents keep their own LLM_BASE_URL; OmniEngine never reads it.
"""

import os
from dataclasses import dataclass

# Same fallbacks as compose.yaml, so an unset variable means the same thing in both places.
DEFAULT_PORT = "8000"
DEFAULT_ALIAS = "local-llm"


@dataclass(frozen=True)
class ServerSettings:
    """Everything a client needs to call the server, like an agent would."""

    base_url: str  # ends in /v1, the same form agents put in LLM_BASE_URL
    model: str  # the alias agents send as "model"
    api_key: str | None  # None when the server checks no key


def server_settings(base_url: str | None = None) -> ServerSettings:
    """Read the settings from the environment; a given base_url replaces the local default."""
    port = os.environ.get("OMNIENGINE_PORT") or DEFAULT_PORT
    url = base_url or f"http://localhost:{port}/v1"
    return ServerSettings(
        # "http://host/v1/" and "http://host/v1" must build the same endpoint URLs later.
        base_url=url.rstrip("/"),
        model=os.environ.get("OMNIENGINE_MODEL_ALIAS") or DEFAULT_ALIAS,
        api_key=os.environ.get("OMNIENGINE_API_KEY") or None,
    )
