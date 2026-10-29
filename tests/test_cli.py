"""Tests for the `omniengine` command line: argument parsing only, no server or model needed."""

import pytest

from omniengine import __version__, chat, models, smoke
from omniengine.cli import main
from omniengine.settings import ServerSettings


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse handles --version itself: it prints the text, then exits with code 0.
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"omniengine {__version__}\n"


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    # Without a command argparse prints usage to stderr and exits with code 2 (wrong usage).
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
    assert "required: COMMAND" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["pull", "verify"])
def test_models_actions_reach_models_run(action: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Replace models.run so the test checks only the wiring: no settings, network or files.
    received: list[str] = []

    def fake_run(requested: str) -> int:
        received.append(requested)
        return 0

    monkeypatch.setattr(models, "run", fake_run)
    assert main(["models", action]) == 0
    assert received == [action]


def test_smoke_passes_the_base_url_to_the_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[ServerSettings] = []

    def fake_run(settings: ServerSettings) -> int:
        received.append(settings)
        return 0

    monkeypatch.setattr(smoke, "run", fake_run)
    assert main(["smoke", "--base-url", "http://gpu-box:8000/v1/"]) == 0
    assert received[0].base_url == "http://gpu-box:8000/v1"


def test_chat_passes_the_base_url_and_show_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[tuple[ServerSettings, bool]] = []

    def fake_run(settings: ServerSettings, show_thinking: bool = False) -> int:
        received.append((settings, show_thinking))
        return 0

    monkeypatch.setattr(chat, "run", fake_run)
    assert main(["chat", "--base-url", "http://gpu-box:8000/v1", "--show-thinking"]) == 0
    assert received[0][0].base_url == "http://gpu-box:8000/v1"
    assert received[0][1] is True
