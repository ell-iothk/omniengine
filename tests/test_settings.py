"""Tests for reading server settings from the environment."""

import pytest

from omniengine.settings import ServerSettings, server_settings

SETTINGS = ("OMNIENGINE_PORT", "OMNIENGINE_MODEL_ALIAS", "OMNIENGINE_API_KEY")
# A made-up key for the tests. detect-secrets flags any literal next to "api_key", so the
# value lives here once, marked as a known false positive.
FAKE_KEY = "test-key"  # pragma: allowlist secret


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Remove the settings, so values exported in the developer's shell cannot leak in."""
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults_match_compose(clean_env: pytest.MonkeyPatch) -> None:
    assert server_settings() == ServerSettings(
        base_url="http://localhost:8000/v1", model="local-llm", api_key=None
    )


def test_values_come_from_the_environment(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("OMNIENGINE_PORT", "9000")
    clean_env.setenv("OMNIENGINE_MODEL_ALIAS", "team-llm")
    clean_env.setenv("OMNIENGINE_API_KEY", FAKE_KEY)
    assert server_settings() == ServerSettings(
        base_url="http://localhost:9000/v1", model="team-llm", api_key=FAKE_KEY
    )


def test_empty_values_count_as_unset(clean_env: pytest.MonkeyPatch) -> None:
    # .env.example ships OMNIENGINE_API_KEY= (empty), which must mean "no key", not "".
    clean_env.setenv("OMNIENGINE_API_KEY", "")
    clean_env.setenv("OMNIENGINE_PORT", "")
    settings = server_settings()
    assert settings.api_key is None
    assert settings.base_url == "http://localhost:8000/v1"


def test_given_base_url_wins_and_loses_its_trailing_slash(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("OMNIENGINE_PORT", "9000")
    settings = server_settings("http://gpu-box:8000/v1/")
    assert settings.base_url == "http://gpu-box:8000/v1"
