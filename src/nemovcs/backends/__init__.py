"""VCS backend registry."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .base import Backend
from .git import GitBackend


BACKENDS: tuple[Backend, ...] = (GitBackend(),)


def registered_backends() -> tuple[Backend, ...]:
    return BACKENDS


def detect_backend(path: str | Path) -> Backend | None:
    for backend in BACKENDS:
        if backend.is_worktree(path):
            return backend
    return None


def detect_root(path: str | Path) -> tuple[Backend, Path] | None:
    for backend in BACKENDS:
        root = backend.root(path)
        if root is not None:
            return backend, root
    return None


def group_by_backend(
    paths: Iterable[str | Path],
) -> dict[Backend, dict[Path, list[str]]]:
    grouped: dict[Backend, dict[Path, list[str]]] = {}
    for backend in BACKENDS:
        roots = backend.group(paths)
        if roots:
            grouped[backend] = roots
    return grouped
