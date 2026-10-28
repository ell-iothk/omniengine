"""Tests against the real vLLM server: run `make up`, then `make test-gpu`.

They carry the gpu marker, so `make test` and CI (pytest -m "not gpu") leave them out.
"""

import pytest

from omniengine.settings import server_settings
from omniengine.smoke import run


@pytest.mark.gpu
def test_the_running_server_passes_every_smoke_check(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run(server_settings())
    # On failure pytest shows the message after the comma: here, the full smoke report.
    assert exit_code == 0, capsys.readouterr().out
