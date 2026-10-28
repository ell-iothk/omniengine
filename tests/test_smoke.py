"""Tests for `omniengine smoke` against the fake vLLM server from conftest.py."""

import socket

import pytest

from conftest import FakeVLLM
from omniengine.settings import ServerSettings
from omniengine.smoke import check_health, check_models, make_client, run

# A made-up key; detect-secrets flags literals next to "api_key", so it is marked once here.
FAKE_KEY = "smoke-test-key"  # pragma: allowlist secret


def _settings(fake: FakeVLLM, api_key: str | None = None) -> ServerSettings:
    return ServerSettings(base_url=fake.base_url, model="local-llm", api_key=api_key)


def test_every_check_passes_against_a_healthy_server(
    fake_vllm: FakeVLLM, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(_settings(fake_vllm)) == 0
    assert "2 of 2 checks passed" in capsys.readouterr().out


def test_health_fails_while_the_server_is_not_ready(fake_vllm: FakeVLLM) -> None:
    fake_vllm.health_status = 503
    result = check_health(_settings(fake_vllm))
    assert not result.passed
    assert "returned 503" in result.detail


def test_models_fails_when_the_alias_is_not_served(fake_vllm: FakeVLLM) -> None:
    # The classic mistake: the real model name is served instead of the alias.
    fake_vllm.model_ids = ["/models/Qwen3-4B-AWQ"]
    settings = _settings(fake_vllm)
    result = check_models(make_client(settings), settings)
    assert not result.passed
    assert "/models/Qwen3-4B-AWQ" in result.detail


def test_the_api_key_is_sent_as_a_bearer_token(fake_vllm: FakeVLLM) -> None:
    settings = _settings(fake_vllm, api_key=FAKE_KEY)
    check_models(make_client(settings), settings)
    assert fake_vllm.auth_headers == [f"Bearer {FAKE_KEY}"]


def _unused_port() -> int:
    # Bind to port 0 to get a free port, then close it, so nothing listens there.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def test_every_check_fails_when_no_server_listens(capsys: pytest.CaptureFixture[str]) -> None:
    settings = ServerSettings(
        base_url=f"http://127.0.0.1:{_unused_port()}/v1", model="local-llm", api_key=None
    )
    assert run(settings) == 1
    assert "0 of 2 checks passed" in capsys.readouterr().out
