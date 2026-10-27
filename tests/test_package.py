"""Sanity checks that the omniengine package is installed and its CLI entry point works."""

import pytest

import omniengine


def test_version_is_set() -> None:
    # An empty version means the package metadata was not installed correctly.
    assert omniengine.__version__


def test_main_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    # capsys is a built-in pytest fixture that captures what the code prints.
    omniengine.main()
    assert capsys.readouterr().out == f"omniengine {omniengine.__version__}\n"
