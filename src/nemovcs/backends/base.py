"""Backend interfaces for VCS implementations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


@dataclass(frozen=True)
class BackendWorktreeIdentity:
    root: Path
    vcs_dir: Path
    common_dir: Path
    head_label: str


@dataclass(frozen=True)
class BackendStatusItem:
    path: str
    old_path: str | None = None
    conflicted: bool = False


@dataclass(frozen=True)
class BackendStatusScan:
    ok: bool
    items: tuple[BackendStatusItem, ...] = ()
    error: str = ""


class Backend(Protocol):
    id: str
    label: str

    def is_worktree(self, path: str | Path) -> bool: ...

    def identity(self, path: str | Path) -> BackendWorktreeIdentity | None: ...

    def root(self, path: str | Path) -> Path | None: ...

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]: ...

    def status(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def scan_status(self, root: str | Path) -> BackendStatusScan: ...

    def commit_items(self, paths: Sequence[str | Path]) -> dict[Path, list[Any]]: ...

    def current_branch(self, root: str | Path) -> str: ...

    def update(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def push(self, paths: Sequence[str | Path]) -> list[Any]: ...
