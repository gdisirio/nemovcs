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


@dataclass(frozen=True)
class BackendChangeItem:
    backend_id: str
    root: Path
    path: str
    status: str
    old_path: str | None = None
    tracked: bool = True
    conflicted: bool = False

    @property
    def default_selected(self) -> bool:
        return self.tracked and not self.conflicted

    @property
    def stage_paths(self) -> tuple[str, ...]:
        if self.old_path:
            return (self.old_path, self.path)
        return (self.path,)


@dataclass(frozen=True)
class BackendCommandPhase:
    title: str
    cwd: Path
    command: tuple[str, ...]


class Backend(Protocol):
    id: str
    label: str

    def is_worktree(self, path: str | Path) -> bool: ...

    def identity(self, path: str | Path) -> BackendWorktreeIdentity | None: ...

    def root(self, path: str | Path) -> Path | None: ...

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]: ...

    def status(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def scan_status(self, root: str | Path) -> BackendStatusScan: ...

    def commit_items(
        self,
        paths: Sequence[str | Path],
    ) -> dict[Path, list[BackendChangeItem]]: ...

    def current_branch(self, root: str | Path) -> str: ...

    def stage_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]: ...

    def commit_phases(
        self,
        root: str | Path,
        relpaths: Sequence[str],
        message: str,
    ) -> list[BackendCommandPhase]: ...

    def log_phases(
        self,
        grouped_paths: dict[Path, list[str]],
        limit: int,
    ) -> list[BackendCommandPhase]: ...

    def update_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]: ...

    def push_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]: ...

    def file_diff_command(self, item: BackendChangeItem) -> list[str]: ...

    def update(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def push(self, paths: Sequence[str | Path]) -> list[Any]: ...
