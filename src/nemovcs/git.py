"""Small Git command helpers for NemoVCS.

This module deliberately shells out to the user's `git` executable. That keeps
runtime dependencies low and delegates repository edge cases to Git itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Iterable, Sequence


DEFAULT_TIMEOUT_SECONDS = 15


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
) -> GitResult:
    """Run `git` in `cwd` and return captured text output."""

    resolved_cwd = path_for_git(cwd)
    command = ("git", "-C", str(resolved_cwd), *args)
    proc = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
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
        args = ["diff", "--", *relpaths]
        results.append(run_git(root, args))
    return results


def update(paths: Sequence[str | Path]) -> list[GitResult]:
    grouped = group_by_repo(paths or [Path.cwd()])
    results: list[GitResult] = []
    for root in grouped:
        results.append(run_git(root, ["pull", "--ff-only"], timeout=300))
    return results
