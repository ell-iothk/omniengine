"""Shared test fixtures; pytest loads this file automatically before the tests.

fake_vllm starts a tiny stand-in for vLLM's HTTP API on a free local port, so CI can test the
smoke checks over real HTTP without a GPU. Tests change its fields to simulate failures.
"""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@dataclass
class FakeVLLM:
    """What the fake server answers, and what it saw."""

    base_url: str = ""
    health_status: int = 200
    model_ids: list[str] = field(default_factory=lambda: ["local-llm"])
    # The Authorization header of every request, or None when a request had none.
    auth_headers: list[str | None] = field(default_factory=list)


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
