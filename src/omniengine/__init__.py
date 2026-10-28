"""OmniEngine tooling: smoke tests, benchmarks and evals for an OpenAI-compatible LLM server.

vLLM itself runs in a container; this package only talks to it over HTTP.
"""

from importlib.metadata import version

# Read the version from the installed package metadata (set in pyproject.toml),
# so the version number is defined in exactly one place.
__version__ = version("omniengine")
