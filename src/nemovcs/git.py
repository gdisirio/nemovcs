"""Small Git command helpers for NemoVCS.

This module deliberately shells out to the user's `git` executable. That keeps
runtime dependencies low and delegates repository edge cases to Git itself.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable, Mapping, Sequence


DEFAULT_TIMEOUT_SECONDS = 15
MELD_MISSING_MESSAGE = "meld is required for visual diffs"
DEFAULT_RECENT_BRANCH_LIMIT = 10


@dataclass(frozen=True)
class GitResult:
    args: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class CommitItem:
    root: Path
    path: str
    status: str
    index_status: str
    worktree_status: str
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


class GitError(RuntimeError):
    """Raised when a Git command fails and the caller requested checking."""

    def __init__(self, result: GitResult):
        self.result = result
        message = result.stderr.strip() or result.stdout.strip()
        super().__init__(message or f"git exited with status {result.returncode}")


def path_for_git(path: str | Path) -> Path:
    """Return an existing directory suitable for `git -C`.

    For files, Git commands should run from the parent directory. Missing paths
    can happen from stale file-manager selections; in that case, walk upward to
    the nearest existing parent.
    """

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    candidate = candidate.resolve(strict=False)
    if candidate.is_dir():
        return candidate

    parent = candidate.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent


def run_git(
    cwd: str | Path,
    args: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    check: bool = False,
    env: Mapping[str, str] | None = None,
) -> GitResult:
    """Run `git` in `cwd` and return captured text output."""

    resolved_cwd = path_for_git(cwd)
    command = ("git", "-C", str(resolved_cwd), *args)
    process_env = None
    if env is not None:
        process_env = os.environ.copy()
        process_env.update(env)
    try:
        proc = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=process_env,
        )
    except FileNotFoundError:
        result = GitResult(command, resolved_cwd, 127, "", "git executable not found\n")
        if check:
            raise GitError(result)
        return result
    result = GitResult(command, resolved_cwd, proc.returncode, proc.stdout, proc.stderr)
    if check and not result.ok:
        raise GitError(result)
    return result


def is_inside_worktree(path: str | Path) -> bool:
    result = run_git(path, ["rev-parse", "--is-inside-work-tree"])
    return result.ok and result.stdout.strip() == "true"


def repo_root(path: str | Path) -> Path | None:
    result = run_git(path, ["rev-parse", "--show-toplevel"])
    if not result.ok:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    return Path(output)


def relative_to_repo(path: str | Path, root: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    root_path = Path(root).resolve(strict=False)

    try:
        rel = candidate.relative_to(root_path)
    except ValueError:
        return "."

    return "." if str(rel) == "." else rel.as_posix()


def group_by_repo(paths: Iterable[str | Path]) -> dict[Path, list[str]]:
    grouped: dict[Path, list[str]] = {}
    for path in paths:
        root = repo_root(path)
        if root is None:
            continue
        grouped.setdefault(root, []).append(relative_to_repo(path, root))
    return grouped


def status(paths: Sequence[str | Path]) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root, relpaths in grouped.items():
        args = ["status", "--short", "--branch", "--", *relpaths]
        results.append(run_git(root, args))
    return results


def _status_label(
    index_status: str,
    worktree_status: str,
    *,
    tracked: bool,
    conflicted: bool,
    old_path: str | None,
) -> str:
    if conflicted:
        return "conflicted"
    if not tracked:
        return "untracked"
    if old_path or index_status in {"R", "C"}:
        return "renamed"
    if index_status == "A":
        return "added"
    if index_status == "D" or worktree_status == "D":
        return "deleted"
    if index_status == "M" or worktree_status == "M":
        return "modified"
    return "changed"


def parse_status_porcelain_v2_z(root: str | Path, data: bytes) -> list[CommitItem]:
    """Parse `git status --porcelain=v2 -z` output for commit selection."""

    root_path = Path(root)
    records = data.split(b"\0")
    items: list[CommitItem] = []
    idx = 0
    while idx < len(records):
        record = records[idx]
        idx += 1
        if not record or record.startswith(b"# "):
            continue

        kind = chr(record[0])
        text = record.decode("utf-8", errors="surrogateescape")

        if kind == "?":
            path = text[2:]
            items.append(
                CommitItem(
                    root=root_path,
                    path=path,
                    status="untracked",
                    index_status="?",
                    worktree_status="?",
                    tracked=False,
                )
            )
            continue

        if kind == "!":
            continue

        if kind == "u":
            fields = text.split(" ", 10)
            if len(fields) < 11:
                continue
            xy = fields[1]
            items.append(
                CommitItem(
                    root=root_path,
                    path=fields[10],
                    status="conflicted",
                    index_status=xy[0],
                    worktree_status=xy[1],
                    conflicted=True,
                )
            )
            continue

        if kind == "1":
            fields = text.split(" ", 8)
            if len(fields) < 9:
                continue
            xy = fields[1]
            items.append(
                CommitItem(
                    root=root_path,
                    path=fields[8],
                    status=_status_label(
                        xy[0], xy[1], tracked=True, conflicted=False, old_path=None
                    ),
                    index_status=xy[0],
                    worktree_status=xy[1],
                )
            )
            continue

        if kind == "2":
            fields = text.split(" ", 9)
            if len(fields) < 10:
                continue
            old_path = None
            if idx < len(records):
                old_record = records[idx]
                idx += 1
                old_path = old_record.decode("utf-8", errors="surrogateescape")
            xy = fields[1]
            items.append(
                CommitItem(
                    root=root_path,
                    path=fields[9],
                    old_path=old_path,
                    status=_status_label(
                        xy[0], xy[1], tracked=True, conflicted=False, old_path=old_path
                    ),
                    index_status=xy[0],
                    worktree_status=xy[1],
                )
            )

    return items


def commit_items(paths: Sequence[str | Path]) -> dict[Path, list[CommitItem]]:
    grouped = group_by_repo(paths or [Path.cwd()])
    items_by_root: dict[Path, list[CommitItem]] = {}
    for root, relpaths in grouped.items():
        result = run_git(
            root,
            ["status", "--porcelain=v2", "-z", "--", *relpaths],
        )
        if not result.ok:
            items_by_root[root] = []
            continue
        items_by_root[root] = parse_status_porcelain_v2_z(
            root,
            result.stdout.encode("utf-8", errors="surrogateescape"),
        )
    return items_by_root


def current_branch(root: str | Path) -> str:
    branch = current_branch_name(root)
    if branch:
        return branch

    result = run_git(root, ["rev-parse", "--short", "HEAD"])
    commit = result.stdout.strip()
    if result.ok and commit:
        return f"detached at {commit}"
    return "unknown"


def current_branch_name(root: str | Path) -> str | None:
    result = run_git(root, ["branch", "--show-current"])
    branch = result.stdout.strip()
    if result.ok and branch:
        return branch
    return None


def remote_url(root: str | Path) -> str | None:
    """Return a display remote URL for a worktree, or None when none is set.

    Follows the repository context bar rule: prefer the current branch's
    upstream remote URL, fall back to `origin`, and give up otherwise so the
    caller can show the local worktree path instead.
    """
    remote_names: list[str] = []

    branch = current_branch_name(root)
    if branch is not None:
        result = run_git(root, ["config", "--get", f"branch.{branch}.remote"])
        upstream = result.stdout.strip()
        if result.ok and upstream:
            remote_names.append(upstream)

    if "origin" not in remote_names:
        remote_names.append("origin")

    for name in remote_names:
        result = run_git(root, ["config", "--get", f"remote.{name}.url"])
        url = result.stdout.strip()
        if result.ok and url:
            return url

    return None


def recent_branches(
    root: str | Path,
    *,
    limit: int = DEFAULT_RECENT_BRANCH_LIMIT,
) -> list[str]:
    result = run_git(
        root,
        [
            "for-each-ref",
            "--sort=-committerdate",
            "--format=%(refname:short)",
            "refs/heads",
        ],
    )
    if not result.ok:
        return []

    branches: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        branch = line.strip()
        if not branch or branch in seen:
            continue
        branches.append(branch)
        seen.add(branch)
        if len(branches) >= limit:
            break
    return branches


def worktree_dirty(root: str | Path) -> bool:
    result = run_git(root, ["status", "--porcelain=v1", "-uall"])
    return (not result.ok) or bool(result.stdout.strip())


def parse_worktree_branch_locations(data: str) -> dict[str, Path]:
    locations: dict[str, Path] = {}
    worktree: Path | None = None
    for line in data.splitlines():
        if not line:
            worktree = None
            continue
        if line.startswith("worktree "):
            worktree = Path(line.removeprefix("worktree "))
            continue
        if line.startswith("branch refs/heads/") and worktree is not None:
            branch = line.removeprefix("branch refs/heads/")
            locations[branch] = worktree
    return locations


def worktree_branch_locations(root: str | Path) -> dict[str, Path]:
    result = run_git(root, ["worktree", "list", "--porcelain"])
    if not result.ok:
        return {}
    return parse_worktree_branch_locations(result.stdout)


def log(paths: Sequence[str | Path], limit: int = 50) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root, relpaths in grouped.items():
        args = ["log", "--oneline", "--decorate", f"-n{limit}", "--", *relpaths]
        results.append(run_git(root, args))
    return results


def diff(paths: Sequence[str | Path]) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root, relpaths in grouped.items():
        args = diff_tool_args(root, relpaths)
        if shutil.which("meld") is None:
            command = ("git", "-C", str(root), *args)
            results.append(
                GitResult(command, root, 127, "", f"{MELD_MISSING_MESSAGE}\n")
            )
            continue
        results.append(run_git(root, args, timeout=3600))
    return results


def diff_commands(paths: Sequence[str | Path]) -> list[GitResult]:
    """Return Git difftool commands for selected paths without running them."""

    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root, relpaths in grouped.items():
        args = diff_tool_args(root, relpaths)
        command = ("git", "-C", str(root), *args)
        if shutil.which("meld") is None:
            results.append(
                GitResult(command, root, 127, "", f"{MELD_MISSING_MESSAGE}\n")
            )
            continue
        results.append(GitResult(command, root, 0, "", ""))
    return results


def diff_tool_args(root: str | Path, relpaths: Sequence[str]) -> list[str]:
    args = ["difftool", "--tool=meld"]
    if diff_uses_dir_mode(root, relpaths):
        args.append("--dir-diff")
    args.extend(["--no-prompt", "--", *relpaths])
    return args


def diff_uses_dir_mode(root: str | Path, relpaths: Sequence[str]) -> bool:
    if not relpaths:
        return True
    root_path = Path(root)
    return any(
        relpath in {"", "."} or (root_path / relpath).is_dir()
        for relpath in relpaths
    )


def update(paths: Sequence[str | Path]) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root in grouped:
        results.append(run_git(root, ["pull", "--ff-only"], timeout=300))
    return results


def push(paths: Sequence[str | Path]) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root in grouped:
        results.append(run_git(root, ["push"], timeout=300))
    return results
