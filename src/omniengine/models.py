"""Download and verify model folders pinned to an exact Hugging Face revision.

A model folder counts as verified only when every file of the pinned revision is present and
identical: large Git LFS files (the weights) are compared by SHA-256, small files by their git
blob hash. The folder may be shared with other projects, so files are only ever added, never
changed or deleted.

Run from the repo root (the Makefile does this):
    uv run --env-file .env python -m omniengine.models pull     # download if missing, then verify
    uv run --env-file .env python -m omniengine.models verify   # verify only, never download
"""

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from huggingface_hub import HfApi, snapshot_download

# Git bookkeeping file in every Hugging Face repo; vLLM never reads it and copies often lack it.
IGNORED_FILES = frozenset({".gitattributes"})

# Files are hashed 1 MiB at a time, so multi-gigabyte weights never have to fit in memory.
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class RemoteFile:
    """One file of the pinned revision and the hashes it must match."""

    path: str
    size: int
    git_sha1: str
    sha256: str | None  # only Git LFS files (the weights) have one


class _Digest(Protocol):
    """What the hash helpers need from a hashlib object."""

    def update(self, data: bytes, /) -> None: ...
    def hexdigest(self) -> str: ...


def _hash_file(path: Path, digest: _Digest) -> str:
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """Hash a file the way git does: SHA-1 of 'blob <size>', a zero byte, then the content."""
    header = f"blob {path.stat().st_size}\0".encode()
    return _hash_file(path, hashlib.sha1(header))


def sha256_of(path: Path) -> str:
    """Plain SHA-256 of a file's content, the hash Git LFS records for large files."""
    return _hash_file(path, hashlib.sha256())


def remote_files(repo_id: str, revision: str, token: str | None) -> list[RemoteFile]:
    """List every file of the pinned revision with its size and hashes (no download)."""
    info = HfApi(token=token).model_info(repo_id, revision=revision, files_metadata=True)
    files = []
    for sibling in info.siblings or []:
        if sibling.rfilename in IGNORED_FILES:
            continue
        if sibling.size is None or sibling.blob_id is None:
            raise RuntimeError(f"Hugging Face returned no hashes for {sibling.rfilename}")
        files.append(
            RemoteFile(
                path=sibling.rfilename,
                size=sibling.size,
                git_sha1=sibling.blob_id,
                sha256=sibling.lfs.sha256 if sibling.lfs else None,
            )
        )
    return files


def _content_matches(local: Path, remote: RemoteFile) -> bool:
    """LFS files (the weights) are checked by SHA-256, every other file by its git blob hash."""
    if remote.sha256 is not None:
        return sha256_of(local) == remote.sha256
    return git_blob_sha1(local) == remote.git_sha1


def verify(folder: Path, files: list[RemoteFile]) -> list[str]:
    """Return one line per file that is missing or different; an empty list means identical."""
    problems = []
    for remote in files:
        local = folder / remote.path
        if not local.is_file():
            problems.append(f"missing: {remote.path}")
        elif local.stat().st_size != remote.size:
            problems.append(f"different size: {remote.path}")
        elif not _content_matches(local, remote):
            problems.append(f"different content: {remote.path}")
    return problems


def _downloaded_here(folder: Path) -> bool:
    """True when huggingface_hub started a download into this folder (so resuming it is safe)."""
    return (folder / ".cache" / "huggingface").is_dir()


def _setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set; copy .env.example to .env and fill it in.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m omniengine.models",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,  # keep the docstring's line breaks
    )
    parser.add_argument("action", choices=["pull", "verify"])
    args = parser.parse_args(argv)

    folder = Path(_setting("OMNIENGINE_MODELS_DIR")) / _setting("OMNIENGINE_MODEL_DIR_NAME")
    repo_id = _setting("OMNIENGINE_MODEL_ID")
    revision = _setting("OMNIENGINE_MODEL_REVISION")
    token = os.environ.get("HF_TOKEN") or None
    label = f"{repo_id}@{revision[:8]}"

    files = remote_files(repo_id, revision, token)

    # Download only into a new folder, or resume a download huggingface_hub itself started.
    # A folder made any other way may belong to another project, so it is never written to.
    if args.action == "pull" and (not folder.exists() or _downloaded_here(folder)):
        print(f"Downloading {label} into {folder} ...")
        snapshot_download(repo_id=repo_id, revision=revision, local_dir=folder, token=token)

    print(f"Verifying {len(files)} files in {folder} against {label} ...")
    problems = verify(folder, files)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"{folder} does not match {label}.", file=sys.stderr)
        return 1
    print(f"OK: {folder} matches {label}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
