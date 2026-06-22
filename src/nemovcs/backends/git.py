"""Git backend adapter.

This adapter intentionally delegates to the existing ``nemovcs.git`` module.
Keeping the public helper module in place lets the first backend migration
introduce discovery without changing current callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from nemovcs import git


class GitBackend:
    id = "git"
    label = "Git"

    def is_worktree(self, path: str | Path) -> bool:
        return git.is_inside_worktree(path)

    def root(self, path: str | Path) -> Path | None:
        return git.repo_root(path)

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]:
        return git.group_by_repo(paths)

    def status(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.status(paths)

    def commit_items(
        self,
        paths: Sequence[str | Path],
    ) -> dict[Path, list[git.CommitItem]]:
        return git.commit_items(paths)

    def current_branch(self, root: str | Path) -> str:
        return git.current_branch(root)

    def update(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.update(paths)

    def push(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.push(paths)
