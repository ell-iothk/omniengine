"""Shared test fixtures; pytest loads this file automatically before the tests.

fake_vllm starts a tiny stand-in for vLLM's HTTP API on a free local port, so CI can test the
smoke checks over real HTTP without a GPU. Tests change its fields to simulate failures.
"""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


@dataclass
class FakeVLLM:
    """What the fake server answers, and what it saw."""

    base_url: str = ""
    health_status: int = 200
    model_ids: list[str] = field(default_factory=lambda: ["local-llm"])
    # Answer to every chat request; the defaults look like vLLM with both parsers on.
    chat_content: str = "\n\n5"
    chat_reasoning: str | None = "2 plus 3 is 5."
    finish_reason: str = "stop"
    # The Authorization header of every request, or None when a request had none.
    auth_headers: list[str | None] = field(default_factory=list)
    # The JSON body of every POST request, in order.
    requests: list[dict[str, Any]] = field(default_factory=list)


def _handler_for(fake: FakeVLLM) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class that answers from the given FakeVLLM."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            fake.auth_headers.append(self.headers.get("Authorization"))
            if self.path == "/health":
                self._send(fake.health_status, {})
            elif self.path == "/v1/models":
                models = [
                    {"id": model_id, "object": "model", "created": 0, "owned_by": "vllm"}
                    for model_id in fake.model_ids
                ]
                self._send(200, {"object": "list", "data": models})
            else:
                self._send(404, {"error": f"no route for {self.path}"})

        def do_POST(self) -> None:
            fake.auth_headers.append(self.headers.get("Authorization"))
            length = int(self.headers.get("Content-Length", "0"))
            fake.requests.append(json.loads(self.rfile.read(length)))
            if self.path == "/v1/chat/completions":
                self._send(200, _chat_completion(fake))
            else:
                self._send(404, {"error": f"no route for {self.path}"})

        def _send(self, status: int, body: dict[str, object]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            """Silence the default one-line-per-request log, so test output stays readable."""

    return Handler


def _chat_completion(fake: FakeVLLM) -> dict[str, object]:
    """A response shaped like vLLM's, including its extra "reasoning" field."""
    message = {"role": "assistant", "content": fake.chat_content, "reasoning": fake.chat_reasoning}
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 0,
        "model": "local-llm",
        "choices": [{"index": 0, "message": message, "finish_reason": fake.finish_reason}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 12, "total_tokens": 32},
    }


@pytest.fixture
def fake_vllm() -> Iterator[FakeVLLM]:
    fake = FakeVLLM()
    # Port 0 asks the operating system for any free port, so tests never clash with vLLM.
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(fake))
    fake.base_url = f"http://127.0.0.1:{server.server_port}/v1"
    # A background thread answers requests while the test runs; daemon=True never blocks exit.
    # poll_interval is how often it checks for shutdown: 0.05 s instead of 0.5 s per test.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    yield fake
    server.shutdown()
    server.server_close()
