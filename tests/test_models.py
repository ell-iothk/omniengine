"""Tests for model folder verification; they run offline, with no Hugging Face calls."""

import hashlib
from pathlib import Path

import pytest
from huggingface_hub.hf_api import BlobLfsInfo, RepoSibling

from omniengine import models
from omniengine.models import RemoteFile, git_blob_sha1, main, remote_files, sha256_of, verify

# `printf 'hello\n' | git hash-object --stdin` prints this blob id. It is a public hash, not a
# secret, so the pragma tells detect-secrets to skip it.
HELLO_GIT_SHA1 = "ce013625030ba8dba906f756967f9e9ca394464a"  # pragma: allowlist secret


def _write(folder: Path, name: str, content: bytes) -> Path:
    path = folder / name
    path.write_bytes(content)
    return path


def test_git_blob_sha1_matches_git(tmp_path: Path) -> None:
    assert git_blob_sha1(_write(tmp_path, "a.txt", b"hello\n")) == HELLO_GIT_SHA1


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    content = b"weights" * 1000
    path = _write(tmp_path, "w.bin", content)
    assert sha256_of(path) == hashlib.sha256(content).hexdigest()


def _remote_files(weights: bytes) -> list[RemoteFile]:
    # One small file checked by git blob hash, one "LFS" file checked by SHA-256.
    return [
        RemoteFile(path="config.json", size=6, git_sha1=HELLO_GIT_SHA1, sha256=None),
        RemoteFile(
            path="model.safetensors",
            size=len(weights),
            git_sha1="pointer-blob-id-is-not-compared",
            sha256=hashlib.sha256(weights).hexdigest(),
        ),
    ]


def test_verify_accepts_identical_folder(tmp_path: Path) -> None:
    weights = b"\x00\x01" * 512
    _write(tmp_path, "config.json", b"hello\n")
    _write(tmp_path, "model.safetensors", weights)
    _write(tmp_path, "extra-file-from-another-project.txt", b"ignored")
    assert verify(tmp_path, _remote_files(weights)) == []


def test_verify_reports_missing_resized_and_changed_files(tmp_path: Path) -> None:
    weights = b"\x00\x01" * 512
    _write(tmp_path, "config.json", b"HELLO\n")  # same size, different content
    _write(tmp_path, "model.safetensors", weights[:-1])  # one byte short
    problems = verify(tmp_path, _remote_files(weights))
    assert problems == [
        "different content: config.json",
        "different size: model.safetensors",
    ]
    assert verify(tmp_path / "empty", _remote_files(weights)) == [
        "missing: config.json",
        "missing: model.safetensors",
    ]


class _FakeInfo:
    siblings = [
        RepoSibling(rfilename=".gitattributes", size=1, blob_id="a"),
        RepoSibling(rfilename="config.json", size=6, blob_id=HELLO_GIT_SHA1),
        RepoSibling(
            rfilename="model.safetensors",
            size=1024,
            blob_id="pointer",
            lfs=BlobLfsInfo(size=1024, sha256="f" * 64, pointer_size=134),
        ),
    ]


class _FakeApi:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def model_info(self, repo_id: str, revision: str, files_metadata: bool) -> _FakeInfo:
        assert files_metadata, "hashes are only returned when files_metadata=True"
        return _FakeInfo()


def test_remote_files_reads_hashes_and_skips_gitattributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Replace the Hugging Face client so the test needs no network.
    monkeypatch.setattr(models, "HfApi", _FakeApi)
    assert remote_files("org/model", "abc123", token=None) == [
        RemoteFile(path="config.json", size=6, git_sha1=HELLO_GIT_SHA1, sha256=None),
        RemoteFile(path="model.safetensors", size=1024, git_sha1="pointer", sha256="f" * 64),
    ]


def test_main_stops_when_a_setting_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIENGINE_MODELS_DIR", raising=False)
    with pytest.raises(SystemExit, match="OMNIENGINE_MODELS_DIR is not set"):
        main(["verify"])
