"""Backend interfaces for VCS implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


class Backend(Protocol):
    id: str
    label: str

    def is_worktree(self, path: str | Path) -> bool: ...

    def root(self, path: str | Path) -> Path | None: ...

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]: ...

    def status(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def commit_items(self, paths: Sequence[str | Path]) -> dict[Path, list[Any]]: ...

    def current_branch(self, root: str | Path) -> str: ...

    def update(self, paths: Sequence[str | Path]) -> list[Any]: ...

    def push(self, paths: Sequence[str | Path]) -> list[Any]: ...
