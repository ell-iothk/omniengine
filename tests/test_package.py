"""Sanity check that the omniengine package is installed with its metadata."""

import omniengine


def test_version_is_set() -> None:
    # An empty version means the package metadata was not installed correctly.
    assert omniengine.__version__
