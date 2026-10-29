"""Tests for `omniengine chat` against the fake vLLM server from conftest.py."""

import io
import socket
from collections.abc import Callable, Iterator

from conftest import FakeVLLM
from omniengine.chat import run
from omniengine.settings import ServerSettings


def _settings(fake: FakeVLLM) -> ServerSettings:
    return ServerSettings(base_url=fake.base_url, model="local-llm", api_key=None)


def _typed(*lines: str) -> Callable[[str], str]:
    """Stand in for input(): return the given lines one by one, then act like Ctrl+D."""
    answers: Iterator[str] = iter(lines)

    def read(prompt: str) -> str:
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    return read


def test_an_answer_streams_without_the_leading_blank_lines(fake_vllm: FakeVLLM) -> None:
    out = io.StringIO()
    assert run(_settings(fake_vllm), read=_typed("What is 2 + 3?", "/exit"), out=out) == 0
    assert "local-llm> 5\n" in out.getvalue()
    assert fake_vllm.requests[-1]["stream"] is True


def test_thinking_is_hidden_unless_asked_for(fake_vllm: FakeVLLM) -> None:
    hidden, shown = io.StringIO(), io.StringIO()
    run(_settings(fake_vllm), read=_typed("What is 2 + 3?"), out=hidden)
    run(_settings(fake_vllm), show_thinking=True, read=_typed("What is 2 + 3?"), out=shown)
    assert "2 plus 3 is 5." not in hidden.getvalue()
    assert "local-llm> 2 plus 3 is 5.\n5\n" in shown.getvalue()  # the answer on its own line


def test_follow_up_questions_carry_the_conversation(fake_vllm: FakeVLLM) -> None:
    run(_settings(fake_vllm), read=_typed("What is 2 + 3?", "And times 2?"), out=io.StringIO())
    assert fake_vllm.requests[-1]["messages"] == [
        {"role": "user", "content": "What is 2 + 3?"},
        {"role": "assistant", "content": "5"},  # the answer only, without the thinking
        {"role": "user", "content": "And times 2?"},
    ]


def test_empty_lines_send_nothing(fake_vllm: FakeVLLM) -> None:
    run(_settings(fake_vllm), read=_typed("", "   ", "/exit"), out=io.StringIO())
    assert fake_vllm.requests == []


def _unused_port() -> int:
    # Bind to port 0 to get a free port, then close it, so nothing listens there.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def test_a_failed_request_is_reported_and_the_chat_goes_on() -> None:
    url = f"http://127.0.0.1:{_unused_port()}/v1"
    settings = ServerSettings(base_url=url, model="local-llm", api_key=None)
    out = io.StringIO()
    assert run(settings, read=_typed("hello", "/exit"), out=out) == 0
    assert "request failed" in out.getvalue()
