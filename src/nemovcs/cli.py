"""Command-line entry point for NemoVCS."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Protocol, Sequence

from . import __version__
from . import backends
from .backends.base import BackendCommandPhase


class CommandResult(Protocol):
    cwd: Path
    returncode: int
    stdout: str
    stderr: str
    ok: bool


def _print_results(results: Sequence[CommandResult]) -> int:
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


def _backend_results(paths: Sequence[str | Path], operation: str) -> list[Any]:
    selected_paths = paths or [Path.cwd()]
    results: list[Any] = []
    for backend in backends.group_by_backend(selected_paths):
        results.extend(getattr(backend, operation)(selected_paths))
    return results


def cmd_action_visible(args: argparse.Namespace) -> int:
    if args.predicate == "inside-worktree":
        if not args.paths:
            return 1
        return 0 if all(backends.detect_backend(path) for path in args.paths) else 1

    if args.predicate == "inside-backend":
        if len(args.paths) < 2:
            return 1
        backend_id = args.paths[0]
        paths = args.paths[1:]
        return (
            0
            if all(backends.is_backend_worktree(path, backend_id) for path in paths)
            else 1
        )

    if args.predicate == "clone-target":
        if not args.paths:
            return 1
        return 0 if all(clone_target_visible(path) for path in args.paths) else 1

    print(f"unknown visibility predicate: {args.predicate}", file=sys.stderr)
    return 2


def clone_target_visible(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve(strict=False)
    return candidate.is_dir() and backends.detect_backend(candidate) is None


def cmd_status(args: argparse.Namespace) -> int:
    return _print_results(_backend_results(args.paths, "status"))


def cmd_status_dialog(args: argparse.Namespace) -> int:
    from .ui import status_dialog

    if not backends.group_by_backend(args.paths or [Path.cwd()]):
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return status_dialog.run(args.paths or ["."])


def cmd_diff(args: argparse.Namespace) -> int:
    return _print_results(backends.raw_diff(args.paths))


def cmd_diff_dialog(args: argparse.Namespace) -> int:
    from .ui import info_dialog
    from .ui import logger

    commands = backends.diff_commands(args.paths)
    if not commands:
        print("not inside a versioned working tree", file=sys.stderr)
        return 1

    text_phases: list[BackendCommandPhase] = []
    exit_code = 0
    for command in commands:
        if not command.ok:
            info_dialog.show_error(
                "Unable to open diff",
                command.stderr.strip() or "Diff command could not be built.",
            )
            exit_code = command.returncode or 1
            continue
        if command.args and command.args[0] == "svn":
            text_phases.append(
                BackendCommandPhase(
                    title=f"Diff {command.cwd.name}",
                    cwd=command.cwd,
                    command=command.args,
                )
            )
            continue
        try:
            subprocess.Popen(command.args, cwd=str(command.cwd))
        except OSError as exc:
            info_dialog.show_error("Unable to open diff", str(exc))
            exit_code = 127
    if text_phases:
        logger_exit = logger.run("Diff", text_phases)
        if logger_exit:
            exit_code = logger_exit
    return exit_code


def cmd_svn_meld_diff(args: argparse.Namespace) -> int:
    meld = shutil.which("meld")
    if meld is None:
        print("meld is required for visual diffs", file=sys.stderr)
        return 127

    target = Path(args.path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve(strict=False)

    with tempfile.TemporaryDirectory(prefix="nemovcs-svn-diff-") as temp_dir:
        base_path = Path(temp_dir) / (target.name or "working-copy")
        export = subprocess.run(
            ["svn", "export", "--force", "-r", "BASE", str(target), str(base_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if export.returncode:
            if export.stdout:
                print(export.stdout, end="")
            if export.stderr:
                print(export.stderr, end="", file=sys.stderr)
            return export.returncode

        try:
            return subprocess.call([meld, str(base_path), str(target)])
        except OSError as exc:
            print(str(exc), file=sys.stderr)
            return 127


def cmd_log(args: argparse.Namespace) -> int:
    return _print_results(backends.raw_log(args.paths, args.limit))


def log_phases(paths: Sequence[str], limit: int):
    return backends.log_phases(paths, limit)


def cmd_log_dialog(args: argparse.Namespace) -> int:
    from .ui import logger

    phases = log_phases(args.paths, args.limit)
    if not phases:
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return logger.run("Log", phases)


def cmd_update(args: argparse.Namespace) -> int:
    return _print_results(_backend_results(args.paths, "update"))


def update_phases(paths: Sequence[str]):
    return backends.update_phases(paths)


def cmd_update_dialog(args: argparse.Namespace) -> int:
    from .ui import logger

    phases = update_phases(args.paths)
    if not phases:
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return logger.run("Update", phases)


def cmd_push(args: argparse.Namespace) -> int:
    return _print_results(_backend_results(args.paths, "push"))


def push_phases(paths: Sequence[str]):
    return backends.push_phases(paths)


def cmd_push_dialog(args: argparse.Namespace) -> int:
    from .ui import logger

    phases = push_phases(args.paths)
    if not phases:
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return logger.run("Push", phases)


def switch_branch_phase(root: str | Path, branch: str) -> BackendCommandPhase:
    root_path = Path(root).expanduser().resolve(strict=False)
    return BackendCommandPhase(
        title=f"Switch to {branch}",
        cwd=root_path,
        command=("git", "-C", str(root_path), "switch", branch),
    )


def cmd_switch_branch_dialog(args: argparse.Namespace) -> int:
    from . import git
    from .ui import info_dialog
    from .ui import logger

    root = git.repo_root(args.path)
    if root is None:
        print("not inside a Git working tree", file=sys.stderr)
        return 1

    if git.worktree_dirty(root):
        info_dialog.show_error(
            "Cannot switch branch",
            "The Git working tree has changes. Commit, revert, or clean it first.",
        )
        return 1

    current = git.current_branch(root)
    target = args.branch or select_switch_branch(root, current)
    if target is None:
        return 0

    if current == target:
        return 0

    if not confirm_switch_branch(root, current, target):
        return 0

    return logger.run("Switch Branch", [switch_branch_phase(root, target)])


def select_switch_branch(root: str | Path, current: str) -> str | None:
    import gi

    from . import git

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Pango  # noqa: E402

    branches = git.recent_branches(root, limit=1000)
    if current not in branches:
        branches.insert(0, current)
    if not branches:
        return None
    branch_locations = git.worktree_branch_locations(root)
    current_root = Path(root).resolve(strict=False)

    dialog = Gtk.Dialog(
        title="Switch Git Branch",
        flags=Gtk.DialogFlags.MODAL,
    )
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    switch_button = dialog.add_button("Switch...", Gtk.ResponseType.OK)
    dialog.set_default_size(520, 420)

    branch_list = Gtk.ListBox()
    branch_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
    branch_list.set_activate_on_single_click(False)

    first_selectable_row = None
    for branch in branches:
        branch_location = branch_locations.get(branch)
        checked_out_elsewhere = (
            branch_location is not None
            and branch_location.resolve(strict=False) != current_root
        )
        row = Gtk.ListBoxRow()
        row.nemovcs_branch = branch
        row.nemovcs_selectable = branch != current and not checked_out_elsewhere
        row.set_activatable(row.nemovcs_selectable)
        row.set_selectable(row.nemovcs_selectable)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_border_width(6)
        row.add(box)

        image = Gtk.Image.new_from_icon_name(
            "object-select-symbolic",
            Gtk.IconSize.MENU,
        )
        if branch != current:
            image.set_opacity(0)
        box.pack_start(image, False, False, 0)

        label = Gtk.Label(label=branch)
        label.set_xalign(0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(label, True, True, 0)

        if checked_out_elsewhere:
            row.set_tooltip_text(f"Checked out at {branch_location}")
            label.set_sensitive(False)
            image.set_sensitive(False)

        branch_list.add(row)
        if first_selectable_row is None and row.nemovcs_selectable:
            first_selectable_row = row

    def selected_branch() -> str | None:
        row = branch_list.get_selected_row()
        return getattr(row, "nemovcs_branch", None) if row is not None else None

    def update_switch_button(*_args) -> None:
        row = branch_list.get_selected_row()
        switch_button.set_sensitive(
            bool(row is not None and getattr(row, "nemovcs_selectable", False))
        )

    def on_row_activated(_list, row) -> None:
        if getattr(row, "nemovcs_selectable", False):
            dialog.response(Gtk.ResponseType.OK)

    branch_list.connect("row-selected", update_switch_button)
    branch_list.connect("row-activated", on_row_activated)
    if first_selectable_row is not None:
        branch_list.select_row(first_selectable_row)
    update_switch_button()

    scroll = Gtk.ScrolledWindow()
    scroll.set_shadow_type(Gtk.ShadowType.IN)
    scroll.add(branch_list)
    content = dialog.get_content_area()
    content.set_spacing(8)
    content.pack_start(scroll, True, True, 0)
    dialog.show_all()

    selected = None
    response = dialog.run()
    if response == Gtk.ResponseType.OK:
        branch = selected_branch()
        if branch != current:
            selected = branch
    dialog.destroy()
    return selected


def confirm_switch_branch(root: str | Path, current: str, target: str) -> bool:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: E402

    dialog = Gtk.MessageDialog(
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.CANCEL,
        text="Switch Git branch?",
    )
    dialog.add_button("Switch", Gtk.ResponseType.OK)
    dialog.format_secondary_text(
        f"Repository: {Path(root)}\nCurrent branch: {current}\nTarget branch: {target}"
    )
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def cmd_commit(args: argparse.Namespace) -> int:
    results = backends.commit(args.paths, args.message)
    if not results:
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return _print_results(results)


def cmd_commit_dialog(args: argparse.Namespace) -> int:
    from .ui import commit_dialog

    return commit_dialog.run(args.paths or ["."])


def cmd_stage_dialog(args: argparse.Namespace) -> int:
    from .ui import stage_dialog

    if not backends.group_by_backend(args.paths or [Path.cwd()]):
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return stage_dialog.run(args.paths or ["."], operation=args.operation)


def cmd_revert_dialog(args: argparse.Namespace) -> int:
    from .ui import revert_dialog

    if not backends.group_by_backend(args.paths or [Path.cwd()]):
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return revert_dialog.run(args.paths or ["."])


def cmd_rename_dialog(args: argparse.Namespace) -> int:
    from .ui import rename_dialog

    if len(args.paths) != 1:
        print("select exactly one path to rename", file=sys.stderr)
        return 1
    if not backends.group_by_backend(args.paths):
        print("not inside a versioned working tree", file=sys.stderr)
        return 1
    return rename_dialog.run(args.paths)


def cmd_clone_dialog(args: argparse.Namespace) -> int:
    from .ui import clone_dialog

    paths = args.paths or ["."]
    if not all(clone_target_visible(path) for path in paths):
        print("not a clone target", file=sys.stderr)
        return 1
    return clone_dialog.run(paths, vcs=args.vcs)


def cmd_settings(args: argparse.Namespace) -> int:
    return cmd_settings_dialog(args)


def cmd_settings_dialog(args: argparse.Namespace) -> int:
    from .ui import settings_dialog

    return settings_dialog.run()


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

        paths = absolute_paths(args.paths or [Path.cwd()])
        try:
            statusd_dbus.call_seen(paths)
            records = statusd_dbus.call_get_status(paths)
        except Exception as exc:
            print(f"status daemon DBus call failed: {exc}", file=sys.stderr)
            return 1

        for record in records:
            print(
                f"{record['path']}: {record['status']} "
                f"backend={record.get('backend', '')} "
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


def absolute_paths(paths: Sequence[str | Path]) -> list[str]:
    return [str(Path(path).expanduser().resolve(strict=False)) for path in paths]


def print_status_record(record: dict[str, str]) -> None:
    print(
        f"{record['path']}: {record['status']} "
        f"backend={record.get('backend', '')} "
        f"worktree={record['worktree_id']}"
    )
    if record.get("error"):
        print(f"  error: {record['error']}")


def cmd_status_watch(args: argparse.Namespace) -> int:
    import dbus.mainloop.glib
    from gi.repository import GLib

    from . import status_client
    from . import statusd_dbus

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    watched_paths = absolute_paths(args.paths or [Path.cwd()])
    cache = status_client.StatusClientCache()

    def refresh() -> None:
        records = cache.refresh(
            watched_paths,
            statusd_dbus.call_seen,
            statusd_dbus.call_get_status,
        )
        for record in records:
            print_status_record(record)
        sys.stdout.flush()

    def on_changed(worktree_id, paths) -> None:
        changed_paths = [str(path) for path in paths]
        removed = cache.invalidate(str(worktree_id), changed_paths)
        print(
            f"StatusChanged worktree={worktree_id} "
            f"paths={','.join(changed_paths) or '*'} "
            f"invalidated={len(removed)}"
        )
        refresh()

    try:
        statusd_dbus.subscribe_status_changed(on_changed)
        refresh()
    except Exception as exc:
        print(f"status daemon DBus watch failed: {exc}", file=sys.stderr)
        return 1

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("status watch stopped.")
    return 0


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
    action_visible.add_argument(
        "predicate",
        choices=["inside-worktree", "inside-backend", "clone-target"],
    )
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

    diff_dialog = subparsers.add_parser("diff-dialog", help="show VCS diff in Meld")
    diff_dialog.add_argument("paths", nargs="*")
    diff_dialog.set_defaults(func=cmd_diff_dialog)

    svn_meld_diff = subparsers.add_parser(
        "svn-meld-diff",
        help="compare SVN BASE against the working copy in Meld",
    )
    svn_meld_diff.add_argument("path")
    svn_meld_diff.set_defaults(func=cmd_svn_meld_diff)

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

    push = subparsers.add_parser("push", help="push the current Git repository")
    push.add_argument("paths", nargs="*")
    push.set_defaults(func=cmd_push)

    push_dialog = subparsers.add_parser(
        "push-dialog",
        help="push the current Git repository in a GTK logger",
    )
    push_dialog.add_argument("paths", nargs="*")
    push_dialog.set_defaults(func=cmd_push_dialog)

    switch_branch_dialog = subparsers.add_parser(
        "switch-branch-dialog",
        help="confirm and switch the current Git branch",
    )
    switch_branch_dialog.add_argument("path")
    switch_branch_dialog.add_argument("branch", nargs="?")
    switch_branch_dialog.set_defaults(func=cmd_switch_branch_dialog)

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

    stage_dialog = subparsers.add_parser(
        "stage-dialog",
        help="open the GTK stage dialog",
    )
    stage_dialog.add_argument("--operation", choices=["stage", "add"], default="stage")
    stage_dialog.add_argument("paths", nargs="*")
    stage_dialog.set_defaults(func=cmd_stage_dialog)

    revert_dialog = subparsers.add_parser(
        "revert-dialog",
        help="open the GTK revert dialog",
    )
    revert_dialog.add_argument("paths", nargs="*")
    revert_dialog.set_defaults(func=cmd_revert_dialog)

    rename_dialog = subparsers.add_parser(
        "rename-dialog",
        help="open the GTK rename dialog",
    )
    rename_dialog.add_argument("paths", nargs="*")
    rename_dialog.set_defaults(func=cmd_rename_dialog)

    clone_dialog = subparsers.add_parser(
        "clone-dialog",
        help="open the GTK clone dialog",
    )
    clone_dialog.add_argument("--vcs", choices=["git", "svn"], default="git")
    clone_dialog.add_argument("paths", nargs="*")
    clone_dialog.set_defaults(func=cmd_clone_dialog)

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

    status_watch = subparsers.add_parser(
        "status-watch",
        help="watch status daemon invalidation signals",
    )
    status_watch.add_argument("paths", nargs="*")
    status_watch.set_defaults(func=cmd_status_watch)

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
