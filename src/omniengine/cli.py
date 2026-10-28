"""The `omniengine` command: one entry point with a subcommand per task.

Examples, run from the repo root:
    uv run --env-file .env omniengine models pull     # download the model if missing, then verify
    uv run --env-file .env omniengine models verify   # verify only, never download
    uv run --env-file .env omniengine smoke           # check the running server like an agent
"""

import argparse

from omniengine import __version__, models, smoke
from omniengine.settings import server_settings


def build_parser() -> argparse.ArgumentParser:
    """Describe every command and option; argparse also builds --help from this."""
    parser = argparse.ArgumentParser(
        prog="omniengine",
        description="Tooling around a vLLM server: model files and smoke tests now; "
        "benchmarks and evals in later steps.",
    )
    # argparse prints the text and exits with code 0, so main() never sees this flag.
    parser.add_argument("--version", action="version", version=f"omniengine {__version__}")

    # required=True: running `omniengine` with no command prints usage and exits with code 2.
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    models_parser = commands.add_parser("models", help="download and verify model folders")
    actions = models_parser.add_subparsers(dest="action", required=True, metavar="ACTION")
    actions.add_parser("pull", help="download the model set in .env if missing, then verify it")
    actions.add_parser("verify", help="check the model folder against the pinned revision")

    smoke_parser = commands.add_parser("smoke", help="check the running server like an agent")
    smoke_parser.add_argument(
        "--base-url",
        help="server to check, ending in /v1 (default: http://localhost:$OMNIENGINE_PORT/v1)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point of the `omniengine` command; the return value becomes the exit code.

    argv defaults to the real command line; tests pass a list instead.
    """
    args = build_parser().parse_args(argv)
    if args.command == "models":
        return models.run(args.action)
    if args.command == "smoke":
        return smoke.run(server_settings(args.base_url))
    # argparse already rejects unknown commands, so reaching this line is a bug in this file.
    raise AssertionError(f"command {args.command!r} has no handler")
