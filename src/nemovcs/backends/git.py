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
    BackendChangeItem,
    BackendCommandPhase,
    BackendStatusItem,
    BackendStatusScan,
    BackendWorktreeIdentity,
)


class GitBackend:
    id = "git"
    label = "Git"
    scan_env = {"GIT_OPTIONAL_LOCKS": "0"}

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

    def log(self, paths: Sequence[str | Path], limit: int) -> list[git.GitResult]:
        return git.log(paths, limit=limit)

    def diff(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.diff(paths)

    def diff_commands(self, paths: Sequence[str | Path]) -> list[git.GitResult]:
        return git.diff_commands(paths)

    def commit(
        self,
        paths: Sequence[str | Path],
        message: str | None,
    ) -> list[git.GitResult]:
        results: list[git.GitResult] = []
        for root, relpaths in git.group_by_repo(paths or [Path.cwd()]).items():
            add_result = git.run_git(root, ["add", "--", *relpaths])
            results.append(add_result)
            if not add_result.ok:
                continue

            commit_args = ["commit"]
            if message:
                commit_args.extend(["-m", message])
            results.append(git.run_git(root, commit_args, timeout=3600))
        return results

    def scan_status(self, root: str | Path) -> BackendStatusScan:
        result = git.run_git(
            root,
            ["status", "--porcelain=v2", "-z", "-uall"],
            env=self.scan_env,
        )
        if not result.ok:
            return BackendStatusScan(
                ok=False,
                error=result.stderr.strip() or result.stdout.strip(),
            )
        tracked = git.run_git(root, ["ls-files", "-z"], env=self.scan_env)
        if not tracked.ok:
            return BackendStatusScan(
                ok=False,
                error=tracked.stderr.strip() or tracked.stdout.strip(),
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
                    status="unversioned" if not item.tracked else "modified",
                    old_path=item.old_path,
                    conflicted=item.conflicted or item.status == "conflicted",
                )
                for item in items
            ),
            tracked_paths=tuple(parse_ls_files_z(tracked.stdout)),
        )

    def commit_items(
        self,
        paths: Sequence[str | Path],
    ) -> dict[Path, list[BackendChangeItem]]:
        return {
            root: [self._change_item(item) for item in items]
            for root, items in git.commit_items(paths).items()
        }

    def current_branch(self, root: str | Path) -> str:
        return git.current_branch(root)

    def stage_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(
                f"Stage {root.name}",
                root,
                ["add", "--", *relpaths],
            )
            for root, relpaths in paths_by_root.items()
            if relpaths
        ]

    def commit_phases(
        self,
        root: str | Path,
        relpaths: Sequence[str],
        message: str,
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(
                "Stage selected files",
                root,
                ["add", "--", *relpaths],
            ),
            self._git_phase(
                "Create commit",
                root,
                ["commit", "-m", message, "--", *relpaths],
            ),
        ]

    def log_phases(
        self,
        grouped_paths: dict[Path, list[str]],
        limit: int,
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(
                f"Log {root.name}",
                root,
                ["log", "--oneline", "--decorate", f"-n{limit}", "--", *relpaths],
            )
            for root, relpaths in grouped_paths.items()
        ]

    def update_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(f"Update {root.name}", root, ["pull", "--ff-only"])
            for root in grouped_paths
        ]

    def push_phases(
        self,
        grouped_paths: dict[Path, list[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(f"Push {root.name}", root, ["push"])
            for root in grouped_paths
        ]

    def revert_phases(
        self,
        paths_by_root: dict[Path, Sequence[str]],
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(
                f"Revert {root.name}",
                root,
                ["restore", "--staged", "--worktree", "--", *relpaths],
            )
            for root, relpaths in paths_by_root.items()
            if relpaths
        ]

    def rename_phases(
        self,
        root: str | Path,
        source_relpath: str,
        target_relpath: str,
    ) -> list[BackendCommandPhase]:
        return [
            self._git_phase(
                f"Rename {Path(source_relpath).name}",
                root,
                ["mv", "--", source_relpath, target_relpath],
            )
        ]

    def file_diff_command(self, item: BackendChangeItem) -> list[str]:
        return [
            "git",
            "-C",
            str(item.root),
            "difftool",
            "--tool=meld",
            "--no-prompt",
            "HEAD",
            "--",
            item.path,
        ]

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

    def _git_phase(
        self,
        title: str,
        cwd: str | Path,
        args: Sequence[str],
    ) -> BackendCommandPhase:
        cwd_path = Path(cwd)
        return BackendCommandPhase(
            title=title,
            cwd=cwd_path,
            command=("git", "-C", str(cwd_path), *args),
        )

    def _change_item(self, item: git.CommitItem) -> BackendChangeItem:
        return BackendChangeItem(
            backend_id=self.id,
            root=item.root,
            path=item.path,
            status=item.status,
            old_path=item.old_path,
            tracked=item.tracked,
            conflicted=item.conflicted,
        )


def parse_ls_files_z(data: str) -> list[str]:
    return [path for path in data.split("\0") if path]
