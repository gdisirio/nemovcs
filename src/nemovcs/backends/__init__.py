"""VCS backend registry."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .base import Backend, BackendChangeItem, BackendWorktreeIdentity
from .git import GitBackend


BACKENDS: tuple[Backend, ...] = (GitBackend(),)


def registered_backends() -> tuple[Backend, ...]:
    return BACKENDS


def backend_by_id(backend_id: str) -> Backend | None:
    for backend in BACKENDS:
        if backend.id == backend_id:
            return backend
    return None


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


def detect_worktree_identity(
    path: str | Path,
) -> tuple[Backend, BackendWorktreeIdentity] | None:
    for backend in BACKENDS:
        identity = backend.identity(path)
        if identity is not None:
            return backend, identity
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


def commit_items(paths: Sequence[str | Path]) -> dict[Path, list[BackendChangeItem]]:
    selected_paths = paths or [Path.cwd()]
    items_by_root: dict[Path, list[BackendChangeItem]] = {}
    for backend in BACKENDS:
        items_by_root.update(backend.commit_items(selected_paths))
    return items_by_root


def current_branch(root: str | Path) -> str:
    backend = detect_backend(root)
    if backend is None:
        return "unknown"
    return backend.current_branch(root)
