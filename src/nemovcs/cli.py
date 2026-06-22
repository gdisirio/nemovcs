"""Command-line entry point for NemoVCS."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Callable, Sequence

from . import __version__
from . import git


def _print_results(results: list[git.GitResult]) -> int:
    exit_code = 0
    for idx, result in enumerate(results):
        if idx:
            print()
        if len(results) > 1:
            print(f"# {result.cwd}")
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if not result.ok:
            exit_code = result.returncode or 1
    return exit_code


def cmd_action_visible(args: argparse.Namespace) -> int:
    if args.predicate == "inside-worktree":
        if not args.paths:
            return 1
        return 0 if all(git.is_inside_worktree(path) for path in args.paths) else 1

    print(f"unknown visibility predicate: {args.predicate}", file=sys.stderr)
    return 2


def cmd_status(args: argparse.Namespace) -> int:
    return _print_results(git.status(args.paths))


def cmd_status_dialog(args: argparse.Namespace) -> int:
    from .ui import status_dialog

    if not git.group_by_repo(args.paths or [Path.cwd()]):
        print("not inside a Git working tree", file=sys.stderr)
        return 1
    return status_dialog.run(args.paths or ["."])


def cmd_diff(args: argparse.Namespace) -> int:
    return _print_results(git.diff(args.paths))


def cmd_diff_dialog(args: argparse.Namespace) -> int:
    from .ui import info_dialog

    commands = git.diff_commands(args.paths)
    if not commands:
        print("not inside a Git working tree", file=sys.stderr)
        return 1

    exit_code = 0
    for command in commands:
        if not command.ok:
            info_dialog.show_error(
                "Unable to open diff",
                command.stderr.strip() or "Git difftool command could not be built.",
            )
            exit_code = command.returncode or 1
            continue
        try:
            subprocess.Popen(command.args, cwd=str(command.cwd))
        except OSError as exc:
            info_dialog.show_error("Unable to open diff", str(exc))
            exit_code = 127
    return exit_code


def cmd_log(args: argparse.Namespace) -> int:
    return _print_results(git.log(args.paths, limit=args.limit))


def log_phases(paths: Sequence[str], limit: int):
    from .ui import logger

    grouped = git.group_by_repo(paths or [Path.cwd()])
    return [
        logger.CommandPhase.git(
            f"Log {root.name}",
            root,
            ["log", "--oneline", "--decorate", f"-n{limit}", "--", *relpaths],
        )
        for root, relpaths in grouped.items()
    ]


def cmd_log_dialog(args: argparse.Namespace) -> int:
    from .ui import logger

    phases = log_phases(args.paths, args.limit)
    if not phases:
        print("not inside a Git working tree", file=sys.stderr)
        return 1
    return logger.run("Log", phases)


def cmd_update(args: argparse.Namespace) -> int:
    return _print_results(git.update(args.paths))


def update_phases(paths: Sequence[str]):
    from .ui import logger

    grouped = git.group_by_repo(paths or [Path.cwd()])
    return [
        logger.CommandPhase.git(f"Update {root.name}", root, ["pull", "--ff-only"])
        for root in grouped
    ]


def cmd_update_dialog(args: argparse.Namespace) -> int:
    from .ui import logger

    phases = update_phases(args.paths)
    if not phases:
        print("not inside a Git working tree", file=sys.stderr)
        return 1
    return logger.run("Update", phases)


def cmd_commit(args: argparse.Namespace) -> int:
    paths = args.paths or ["."]
    grouped = git.group_by_repo(paths)
    if not grouped:
        print("not inside a Git working tree", file=sys.stderr)
        return 1

    exit_code = 0
    for root, relpaths in grouped.items():
        add_result = git.run_git(root, ["add", "--", *relpaths])
        if not add_result.ok:
            _print_results([add_result])
            exit_code = add_result.returncode or 1
            continue

        commit_args = ["commit"]
        if args.message:
            commit_args.extend(["-m", args.message])
        result = git.run_git(root, commit_args, timeout=3600)
        rc = _print_results([result])
        if rc:
            exit_code = rc
    return exit_code


def cmd_commit_dialog(args: argparse.Namespace) -> int:
    from .ui import commit_dialog

    return commit_dialog.run(args.paths or ["."])


def cmd_settings(args: argparse.Namespace) -> int:
    print("NemoVCS settings are not implemented yet.")
    print("This placeholder is installed to validate the Nemo menu layout.")
    return 0


def cmd_settings_dialog(args: argparse.Namespace) -> int:
    from .ui import info_dialog

    return info_dialog.run_settings_placeholder()


def cmd_about(args: argparse.Namespace) -> int:
    print(f"NemoVCS {__version__}")
    print("Git integration for the Nemo file manager.")
    print("Project: https://github.com/gdisirio/nemovcs")
    return 0


def cmd_about_dialog(args: argparse.Namespace) -> int:
    from .ui import info_dialog

    return info_dialog.run_about()


def cmd_status_cache(args: argparse.Namespace) -> int:
    from . import statusd

    if args.dbus:
        from . import statusd_dbus

        try:
            statusd_dbus.call_seen([str(path) for path in args.paths or [Path.cwd()]])
            records = statusd_dbus.call_get_status(
                [str(path) for path in args.paths or [Path.cwd()]]
            )
        except Exception as exc:
            print(f"status daemon DBus call failed: {exc}", file=sys.stderr)
            return 1

        for record in records:
            print(
                f"{record['path']}: {record['status']} "
                f"worktree={record['worktree_id']}"
            )
            if record.get("error"):
                print(f"  error: {record['error']}")
        return 0

    exit_code, stdout, stderr = statusd.format_cache_probe(args.paths or [Path.cwd()])
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    return exit_code


def cmd_statusd(args: argparse.Namespace) -> int:
    from . import statusd_dbus

    return statusd_dbus.run_foreground()


def cmd_run_terminal(args: argparse.Namespace) -> int:
    nested_args = list(args.args)
    if not nested_args:
        print("missing command for run-terminal", file=sys.stderr)
        return 2

    try:
        rc = main(nested_args)
    finally:
        try:
            input("\nPress Enter to close this window...")
        except EOFError:
            pass
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nemovcs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    action_visible = subparsers.add_parser(
        "action-visible",
        help="check whether a Nemo action should be visible",
    )
    action_visible.add_argument("predicate", choices=["inside-worktree"])
    action_visible.add_argument("paths", nargs="*")
    action_visible.set_defaults(func=cmd_action_visible)

    status = subparsers.add_parser("status", help="show Git status")
    status.add_argument("paths", nargs="*")
    status.set_defaults(func=cmd_status)

    status_dialog = subparsers.add_parser(
        "status-dialog",
        help="show Git status in a GTK dialog",
    )
    status_dialog.add_argument("paths", nargs="*")
    status_dialog.set_defaults(func=cmd_status_dialog)

    diff = subparsers.add_parser("diff", help="show Git diff")
    diff.add_argument("paths", nargs="*")
    diff.set_defaults(func=cmd_diff)

    diff_dialog = subparsers.add_parser("diff-dialog", help="show Git diff in Meld")
    diff_dialog.add_argument("paths", nargs="*")
    diff_dialog.set_defaults(func=cmd_diff_dialog)

    log = subparsers.add_parser("log", help="show Git log")
    log.add_argument("-n", "--limit", type=int, default=50)
    log.add_argument("paths", nargs="*")
    log.set_defaults(func=cmd_log)

    log_dialog = subparsers.add_parser("log-dialog", help="show Git log in a GTK logger")
    log_dialog.add_argument("-n", "--limit", type=int, default=50)
    log_dialog.add_argument("paths", nargs="*")
    log_dialog.set_defaults(func=cmd_log_dialog)

    update = subparsers.add_parser("update", help="update the current Git repository")
    update.add_argument("paths", nargs="*")
    update.set_defaults(func=cmd_update)

    update_dialog = subparsers.add_parser(
        "update-dialog",
        help="update the current Git repository in a GTK logger",
    )
    update_dialog.add_argument("paths", nargs="*")
    update_dialog.set_defaults(func=cmd_update_dialog)

    commit = subparsers.add_parser("commit", help="stage selected paths and commit")
    commit.add_argument("-m", "--message")
    commit.add_argument("paths", nargs="*")
    commit.set_defaults(func=cmd_commit)

    commit_dialog = subparsers.add_parser(
        "commit-dialog",
        help="open the GTK commit dialog",
    )
    commit_dialog.add_argument("paths", nargs="*")
    commit_dialog.set_defaults(func=cmd_commit_dialog)

    settings = subparsers.add_parser("settings", help="show NemoVCS settings")
    settings.set_defaults(func=cmd_settings)

    settings_dialog = subparsers.add_parser(
        "settings-dialog",
        help="show NemoVCS settings in a GTK dialog",
    )
    settings_dialog.set_defaults(func=cmd_settings_dialog)

    about = subparsers.add_parser("about", help="show NemoVCS information")
    about.set_defaults(func=cmd_about)

    about_dialog = subparsers.add_parser(
        "about-dialog",
        help="show NemoVCS information in a GTK dialog",
    )
    about_dialog.set_defaults(func=cmd_about_dialog)

    status_cache = subparsers.add_parser(
        "status-cache",
        help="inspect the status daemon cache model",
    )
    status_cache.add_argument(
        "--dbus",
        action="store_true",
        help="query a running status daemon over DBus",
    )
    status_cache.add_argument("paths", nargs="*")
    status_cache.set_defaults(func=cmd_status_cache)

    statusd_parser = subparsers.add_parser(
        "statusd",
        help="run the foreground status daemon prototype",
    )
    statusd_parser.set_defaults(func=cmd_statusd)

    run_terminal = subparsers.add_parser(
        "run-terminal",
        help="run a NemoVCS command and pause before the terminal closes",
    )
    run_terminal.add_argument("args", nargs=argparse.REMAINDER)
    run_terminal.set_defaults(func=cmd_run_terminal)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.func
    try:
        return handler(args)
    except subprocess.TimeoutExpired as exc:
        print(f"git command timed out: {exc}", file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
