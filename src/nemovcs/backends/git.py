"""Git backend adapter.

This adapter intentionally delegates to the existing ``nemovcs.git`` module.
Keeping the public helper module in place lets the first backend migration
introduce discovery without changing current callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from nemovcs import git
from nemovcs.backends.base import (
    BackendStatusItem,
    BackendStatusScan,
    BackendWorktreeIdentity,
)


class GitBackend:
    id = "git"
    label = "Git"

    def is_worktree(self, path: str | Path) -> bool:
        return git.is_inside_worktree(path)

    def identity(self, path: str | Path) -> BackendWorktreeIdentity | None:
        probe = git.run_git(
            path,
            [
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-dir",
                "--git-common-dir",
            ],
        )
        if not probe.ok:
            return None

        lines = [line.strip() for line in probe.stdout.splitlines()]
        if len(lines) < 3:
            return None

        return BackendWorktreeIdentity(
            root=Path(lines[0]).resolve(strict=False),
            vcs_dir=Path(lines[1]).resolve(strict=False),
            common_dir=Path(lines[2]).resolve(strict=False),
            head_label=self._head_label(path),
        )

    def root(self, path: str | Path) -> Path | None:
        return git.repo_root(path)

    def group(self, paths: Iterable[str | Path]) -> dict[Path, list[str]]:
        return git.group_by_repo(paths)

    def status(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.status(paths)

    def scan_status(self, root: str | Path) -> BackendStatusScan:
        result = git.run_git(root, ["status", "--porcelain=v2", "-z"])
        if not result.ok:
            return BackendStatusScan(
                ok=False,
                error=result.stderr.strip() or result.stdout.strip(),
            )

        items = git.parse_status_porcelain_v2_z(
            root,
            result.stdout.encode("utf-8", errors="surrogateescape"),
        )
        return BackendStatusScan(
            ok=True,
            items=tuple(
                BackendStatusItem(
                    path=item.path,
                    old_path=item.old_path,
                    conflicted=item.conflicted or item.status == "conflicted",
                )
                for item in items
            ),
        )

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

    def _head_label(self, path: str | Path) -> str:
        branch = git.run_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        if branch.ok:
            name = branch.stdout.strip()
            if name:
                return name

        commit = git.run_git(path, ["rev-parse", "--short", "HEAD"])
        if commit.ok:
            sha = commit.stdout.strip()
            if sha:
                return f"detached at {sha}"

        return "unknown"
