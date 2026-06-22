"""VCS backend registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from .base import (
    Backend,
    BackendChangeItem,
    BackendCommandPhase,
    BackendWorktreeIdentity,
)
from .git import GitBackend
from .svn import SvnBackend


BACKENDS: tuple[Backend, ...] = (GitBackend(), SvnBackend())


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


def is_backend_worktree(path: str | Path, backend_id: str) -> bool:
    backend = backend_by_id(backend_id)
    return bool(backend is not None and backend.is_worktree(path))


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


def raw_status(paths: Sequence[str | Path]) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in group_by_backend(selected_paths):
        results.extend(backend.status(selected_paths))
    return results


def raw_log(paths: Sequence[str | Path], limit: int) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in group_by_backend(selected_paths):
        results.extend(backend.log(selected_paths, limit))
    return results


def raw_diff(paths: Sequence[str | Path]) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in group_by_backend(selected_paths):
        results.extend(backend.diff(selected_paths))
    return results


def diff_commands(paths: Sequence[str | Path]) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in group_by_backend(selected_paths):
        results.extend(backend.diff_commands(selected_paths))
    return results


def commit(paths: Sequence[str | Path], message: str | None) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in group_by_backend(selected_paths):
        results.extend(backend.commit(selected_paths, message))
    return results


def current_branch(root: str | Path) -> str:
    backend = detect_backend(root)
    if backend is None:
        return "unknown"
    return backend.current_branch(root)


def stage_phases(
    paths_by_root: dict[Path, Sequence[str]],
) -> list[BackendCommandPhase]:
    phases: list[BackendCommandPhase] = []
    for root, relpaths in paths_by_root.items():
        if not relpaths:
            continue
        backend = detect_backend(root)
        if backend is None:
            continue
        phases.extend(backend.stage_phases({root: relpaths}))
    return phases


def commit_phases(
    root: str | Path,
    relpaths: Sequence[str],
    message: str,
) -> list[BackendCommandPhase]:
    if not relpaths:
        return []
    backend = detect_backend(root)
    if backend is None:
        return []
    return backend.commit_phases(root, relpaths, message)


def log_phases(paths: Sequence[str | Path], limit: int) -> list[BackendCommandPhase]:
    selected_paths = paths or [Path.cwd()]
    phases: list[BackendCommandPhase] = []
    for backend, grouped_paths in group_by_backend(selected_paths).items():
        phases.extend(backend.log_phases(grouped_paths, limit))
    return phases


def update_phases(paths: Sequence[str | Path]) -> list[BackendCommandPhase]:
    selected_paths = paths or [Path.cwd()]
    phases: list[BackendCommandPhase] = []
    for backend, grouped_paths in group_by_backend(selected_paths).items():
        phases.extend(backend.update_phases(grouped_paths))
    return phases


def push_phases(paths: Sequence[str | Path]) -> list[BackendCommandPhase]:
    selected_paths = paths or [Path.cwd()]
    phases: list[BackendCommandPhase] = []
    for backend, grouped_paths in group_by_backend(selected_paths).items():
        phases.extend(backend.push_phases(grouped_paths))
    return phases


def revert_phases(
    paths_by_root: dict[Path, Sequence[str]],
) -> list[BackendCommandPhase]:
    phases: list[BackendCommandPhase] = []
    for root, relpaths in paths_by_root.items():
        if not relpaths:
            continue
        backend = detect_backend(root)
        if backend is None:
            continue
        phases.extend(backend.revert_phases({root: relpaths}))
    return phases


def file_diff_command(item: BackendChangeItem) -> list[str]:
    backend = backend_by_id(item.backend_id)
    if backend is None:
        return []
    return backend.file_diff_command(item)
