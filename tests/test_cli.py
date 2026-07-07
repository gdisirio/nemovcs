import argparse
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nemovcs import git
from nemovcs.cli import (
    absolute_paths,
    build_parser,
    clone_target_visible,
    cmd_action_visible,
    cmd_commit,
    cmd_diff,
    cmd_diff_dialog,
    cmd_forge,
    cmd_init_dialog,
    cmd_log,
    cmd_publish_dialog,
    cmd_push,
    cmd_revert_dialog,
    cmd_rename_dialog,
    cmd_settings,
    cmd_settings_dialog,
    cmd_stage_dialog,
    cmd_status,
    cmd_status_dialog,
    cmd_svn_meld_diff,
    cmd_switch_branch_dialog,
    cmd_update,
    init_phases,
    log_phases,
    push_phases,
    switch_branch_phase,
    update_phases,
)


class FakeBackend:
    id = "fake"
    label = "Fake"

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []
        self.result = git.GitResult(("fake",), Path("/tmp/example"), 0, "ok\n", "")

    def status(self, paths):
        self.calls.append(("status", list(paths)))
        return [self.result]

    def log(self, paths, limit):
        self.calls.append(("log", list(paths), limit))
        return [self.result]

    def diff(self, paths):
        self.calls.append(("diff", list(paths)))
        return [self.result]

    def diff_commands(self, paths):
        self.calls.append(("diff_commands", list(paths)))
        return [self.result]

    def commit(self, paths, message):
        self.calls.append(("commit", list(paths), message))
        return [self.result]

    def update(self, paths):
        self.calls.append(("update", list(paths)))
        return [self.result]

    def push(self, paths):
        self.calls.append(("push", list(paths)))
        return [self.result]


class CliParserTest(unittest.TestCase):
    def test_run_terminal_keeps_nested_command_arguments(self):
        parser = build_parser()

        args = parser.parse_args(["run-terminal", "log", "-n", "3", "path with space"])

        self.assertEqual(args.command, "run-terminal")
        self.assertEqual(args.args, ["log", "-n", "3", "path with space"])

    def test_action_visible_accepts_clone_target_predicate(self):
        parser = build_parser()

        args = parser.parse_args(["action-visible", "clone-target", "/tmp/example"])

        self.assertEqual(args.command, "action-visible")
        self.assertEqual(args.predicate, "clone-target")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_inside_worktree_predicate_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["action-visible", "inside-worktree", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.detect_backend", return_value=object()):
            self.assertEqual(cmd_action_visible(args), 0)

    def test_inside_worktree_predicate_rejects_unknown_backend(self):
        parser = build_parser()
        args = parser.parse_args(["action-visible", "inside-worktree", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.detect_backend", return_value=None):
            self.assertEqual(cmd_action_visible(args), 1)

    def test_inside_worktree_predicate_rejects_missing_paths(self):
        parser = build_parser()
        args = parser.parse_args(["action-visible", "inside-worktree"])

        self.assertEqual(cmd_action_visible(args), 1)

    def test_inside_backend_predicate_uses_requested_backend(self):
        parser = build_parser()
        args = parser.parse_args(["action-visible", "inside-backend", "svn", "/tmp/wc"])

        with mock.patch(
            "nemovcs.cli.backends.is_backend_worktree",
            return_value=True,
        ) as is_backend_worktree:
            self.assertEqual(cmd_action_visible(args), 0)

        is_backend_worktree.assert_called_once_with("/tmp/wc", "svn")

    def test_inside_backend_predicate_rejects_missing_backend_or_paths(self):
        parser = build_parser()

        self.assertEqual(
            cmd_action_visible(parser.parse_args(["action-visible", "inside-backend"])),
            1,
        )
        self.assertEqual(
            cmd_action_visible(parser.parse_args(["action-visible", "inside-backend", "svn"])),
            1,
        )

    def test_clone_target_visible_accepts_non_worktree_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("nemovcs.cli.backends.detect_backend", return_value=None):
                self.assertTrue(clone_target_visible(tmp))

    def test_clone_target_visible_rejects_worktree_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("nemovcs.cli.backends.detect_backend", return_value=object()):
                self.assertFalse(clone_target_visible(tmp))

    def test_clone_target_visible_rejects_files_without_backend_check(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with mock.patch("nemovcs.cli.backends.detect_backend") as detect_backend:
                self.assertFalse(clone_target_visible(tmp.name))

        detect_backend.assert_not_called()

    def test_clone_target_predicate_rejects_missing_paths(self):
        parser = build_parser()
        args = parser.parse_args(["action-visible", "clone-target"])

        self.assertEqual(cmd_action_visible(args), 1)

    def test_update_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["update", "/tmp/example"])

        self.assertEqual(args.command, "update")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_update_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["update-dialog", "/tmp/example"])

        self.assertEqual(args.command, "update-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_push_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["push", "/tmp/example"])

        self.assertEqual(args.command, "push")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_push_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["push-dialog", "/tmp/example"])

        self.assertEqual(args.command, "push-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_switch_branch_dialog_accepts_optional_branch(self):
        parser = build_parser()

        args = parser.parse_args(["switch-branch-dialog", "/tmp/repo"])

        self.assertEqual(args.command, "switch-branch-dialog")
        self.assertEqual(args.path, "/tmp/repo")
        self.assertIsNone(args.branch)

        args = parser.parse_args(["switch-branch-dialog", "/tmp/repo", "feature/new"])

        self.assertEqual(args.branch, "feature/new")

    def test_status_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["status", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            self.assertEqual(cmd_status(args), 0)

        self.assertEqual(backend.calls, [("status", ["/tmp/example"])])
        self.assertEqual(stdout.getvalue(), "ok\n")

    def test_log_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["log", "-n", "7", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            self.assertEqual(cmd_log(args), 0)

        self.assertEqual(backend.calls, [("log", ["/tmp/example"], 7)])
        self.assertEqual(stdout.getvalue(), "ok\n")

    def test_diff_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["diff", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            self.assertEqual(cmd_diff(args), 0)

        self.assertEqual(backend.calls, [("diff", ["/tmp/example"])])
        self.assertEqual(stdout.getvalue(), "ok\n")

    def test_commit_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["commit", "-m", "message", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            self.assertEqual(cmd_commit(args), 0)

        self.assertEqual(backend.calls, [("commit", ["/tmp/example"], "message")])
        self.assertEqual(stdout.getvalue(), "ok\n")

    def test_commit_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["commit", "-m", "message", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend", return_value={}), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(cmd_commit(args), 1)

    def test_update_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["update", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(cmd_update(args), 0)

        self.assertEqual(backend.calls, [("update", ["/tmp/example"])])

    def test_push_uses_backend_registry(self):
        parser = build_parser()
        args = parser.parse_args(["push", "/tmp/example"])
        backend = FakeBackend()

        with mock.patch(
            "nemovcs.cli.backends.group_by_backend",
            return_value={backend: {Path("/tmp/example"): ["."]}},
        ), mock.patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(cmd_push(args), 0)

        self.assertEqual(backend.calls, [("push", ["/tmp/example"])])

    def test_status_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["status-dialog", "/tmp/example"])

        self.assertEqual(args.command, "status-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_diff_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["diff-dialog", "/tmp/example"])

        self.assertEqual(args.command, "diff-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_svn_meld_diff_accepts_path(self):
        parser = build_parser()

        args = parser.parse_args(["svn-meld-diff", "/tmp/example/file.txt"])

        self.assertEqual(args.command, "svn-meld-diff")
        self.assertEqual(args.path, "/tmp/example/file.txt")

    def test_diff_dialog_uses_backend_diff_commands(self):
        parser = build_parser()
        args = parser.parse_args(["diff-dialog", "/tmp/example"])
        command = git.GitResult(
            ("meld", "/tmp/example"),
            Path("/tmp/example"),
            0,
            "",
            "",
        )

        with mock.patch(
            "nemovcs.cli.backends.diff_commands",
            return_value=[command],
        ) as diff_commands, mock.patch("nemovcs.cli.subprocess.Popen") as popen:
            self.assertEqual(cmd_diff_dialog(args), 0)

        diff_commands.assert_called_once_with(["/tmp/example"])
        popen.assert_called_once_with(command.args, cwd=str(command.cwd))

    def test_svn_meld_diff_exports_base_then_launches_meld(self):
        parser = build_parser()
        args = parser.parse_args(["svn-meld-diff", "/tmp/example/file.txt"])
        export = subprocess.CompletedProcess(
            ["svn"],
            0,
            stdout="",
            stderr="",
        )

        with mock.patch("nemovcs.cli.shutil.which", return_value="/usr/bin/meld"), (
            mock.patch("nemovcs.cli.subprocess.run", return_value=export)
        ) as run, mock.patch("nemovcs.cli.subprocess.call", return_value=0) as call:
            self.assertEqual(cmd_svn_meld_diff(args), 0)

        export_command = run.call_args.args[0]
        self.assertEqual(
            export_command[:6],
            ["svn", "export", "--force", "-r", "BASE", "/tmp/example/file.txt"],
        )
        self.assertEqual(Path(export_command[6]).name, "file.txt")
        meld_command = call.call_args.args[0]
        self.assertEqual(meld_command[0], "/usr/bin/meld")
        self.assertEqual(Path(meld_command[1]).name, "file.txt")
        self.assertEqual(meld_command[2], "/tmp/example/file.txt")

    def test_log_dialog_accepts_limit_and_paths(self):
        parser = build_parser()

        args = parser.parse_args(["log-dialog", "-n", "7", "/tmp/example"])

        self.assertEqual(args.command, "log-dialog")
        self.assertEqual(args.limit, 7)
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_log_phases_run_log_in_each_grouped_repository(self):
        root = Path("/tmp/example")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}):
            phases = log_phases(["/tmp/example/src/app.py"], 7)

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Log example")
        self.assertEqual(phases[0].cwd, root)
        self.assertEqual(
            phases[0].command,
            (
                "git",
                "-C",
                str(root),
                "log",
                "--oneline",
                "--decorate",
                "-n7",
                "--",
                "src/app.py",
            ),
        )

    def test_push_phases_push_each_grouped_repository(self):
        root = Path("/tmp/example")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}):
            phases = push_phases(["/tmp/example/src/app.py"])

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Push example")
        self.assertEqual(phases[0].cwd, root)
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "push"),
        )

    def test_switch_branch_phase_runs_git_switch(self):
        root = Path("/tmp/example")

        phase = switch_branch_phase(root, "feature/new")

        self.assertEqual(phase.title, "Switch to feature/new")
        self.assertEqual(phase.cwd, root)
        self.assertEqual(
            phase.command,
            ("git", "-C", str(root), "switch", "feature/new"),
        )

    def test_switch_branch_dialog_rejects_dirty_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["switch-branch-dialog", "/tmp/repo", "feature/new"])

        with mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.worktree_dirty", return_value=True)
        ), mock.patch("nemovcs.ui.info_dialog.show_error") as show_error:
            self.assertEqual(cmd_switch_branch_dialog(args), 1)

        show_error.assert_called_once()

    def test_switch_branch_dialog_confirms_then_runs_logger(self):
        parser = build_parser()
        args = parser.parse_args(["switch-branch-dialog", "/tmp/repo", "feature/new"])

        with mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.worktree_dirty", return_value=False)
        ), mock.patch("nemovcs.git.current_branch", return_value="main"), (
            mock.patch("nemovcs.cli.confirm_switch_branch", return_value=True)
        ) as confirm, mock.patch("nemovcs.ui.logger.run", return_value=0) as run_logger:
            self.assertEqual(cmd_switch_branch_dialog(args), 0)

        confirm.assert_called_once_with(Path("/tmp/repo"), "main", "feature/new")
        run_logger.assert_called_once_with(
            "Switch Branch",
            [switch_branch_phase(Path("/tmp/repo"), "feature/new")],
        )

    def test_switch_branch_dialog_selects_branch_when_target_is_omitted(self):
        parser = build_parser()
        args = parser.parse_args(["switch-branch-dialog", "/tmp/repo"])

        with mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.worktree_dirty", return_value=False)
        ), mock.patch("nemovcs.git.current_branch", return_value="main"), (
            mock.patch("nemovcs.cli.select_switch_branch", return_value="feature/new")
        ) as select_branch, mock.patch(
            "nemovcs.cli.confirm_switch_branch",
            return_value=True,
        ), mock.patch("nemovcs.ui.logger.run", return_value=0):
            self.assertEqual(cmd_switch_branch_dialog(args), 0)

        select_branch.assert_called_once_with(Path("/tmp/repo"), "main")

    def test_update_phases_pull_each_grouped_repository(self):
        root = Path("/tmp/example")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}):
            phases = update_phases(["/tmp/example/src/app.py"])

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Update example")
        self.assertEqual(phases[0].cwd, root)
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "pull", "--ff-only"),
        )

    def test_settings_and_about_parse(self):
        parser = build_parser()

        self.assertEqual(parser.parse_args(["settings"]).command, "settings")
        self.assertEqual(parser.parse_args(["about"]).command, "about")
        self.assertEqual(parser.parse_args(["settings-dialog"]).command, "settings-dialog")
        self.assertEqual(parser.parse_args(["about-dialog"]).command, "about-dialog")

    def test_settings_commands_open_settings_dialog(self):
        parser = build_parser()

        with mock.patch("nemovcs.ui.settings_dialog.run", return_value=0) as run_dialog:
            self.assertEqual(cmd_settings(parser.parse_args(["settings"])), 0)
            self.assertEqual(cmd_settings_dialog(parser.parse_args(["settings-dialog"])), 0)

        self.assertEqual(run_dialog.call_count, 2)

    def test_status_cache_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["status-cache", "/tmp/example"])

        self.assertEqual(args.command, "status-cache")
        self.assertFalse(args.dbus)
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_status_cache_accepts_dbus_probe(self):
        parser = build_parser()

        args = parser.parse_args(["status-cache", "--dbus", "/tmp/example"])

        self.assertEqual(args.command, "status-cache")
        self.assertTrue(args.dbus)
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_statusd_parses(self):
        parser = build_parser()

        self.assertEqual(parser.parse_args(["statusd"]).command, "statusd")

    def test_status_watch_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["status-watch", "/tmp/example"])

        self.assertEqual(args.command, "status-watch")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_absolute_paths_resolves_relative_paths(self):
        paths = absolute_paths([".", "/tmp/example"])

        self.assertEqual(paths[0], str(Path.cwd()))
        self.assertEqual(paths[1], "/tmp/example")

    def test_commit_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["commit-dialog", "/tmp/example"])

        self.assertEqual(args.command, "commit-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_stage_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["stage-dialog", "--operation", "add", "/tmp/example"])

        self.assertEqual(args.command, "stage-dialog")
        self.assertEqual(args.operation, "add")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_revert_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["revert-dialog", "/tmp/example"])

        self.assertEqual(args.command, "revert-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_rename_dialog_accepts_single_path(self):
        parser = build_parser()

        args = parser.parse_args(["rename-dialog", "/tmp/example"])

        self.assertEqual(args.command, "rename-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_clone_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["clone-dialog", "--vcs", "svn", "/tmp/example"])

        self.assertEqual(args.command, "clone-dialog")
        self.assertEqual(args.vcs, "svn")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_clone_dialog_runs_dialog_for_clone_target(self):
        parser = build_parser()
        args = parser.parse_args(["clone-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.clone_target_visible", return_value=True), mock.patch(
            "nemovcs.ui.clone_dialog.run",
            return_value=0,
        ) as run_dialog:
            self.assertEqual(args.func(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"], vcs="git")

    def test_clone_dialog_rejects_non_clone_target(self):
        parser = build_parser()
        args = parser.parse_args(["clone-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.clone_target_visible", return_value=False), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(args.func(args), 1)

    def test_status_dialog_runs_dialog_inside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["status-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend") as group_by_backend, mock.patch(
            "nemovcs.ui.status_dialog.run",
            return_value=0,
        ) as run_dialog:
            group_by_backend.return_value = {object(): {Path("/tmp/example"): ["."]}}

            self.assertEqual(cmd_status_dialog(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"])

    def test_status_dialog_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["status-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend", return_value={}), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(cmd_status_dialog(args), 1)

    def test_stage_dialog_runs_dialog_inside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["stage-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend") as group_by_backend, mock.patch(
            "nemovcs.ui.stage_dialog.run",
            return_value=0,
        ) as run_dialog:
            group_by_backend.return_value = {object(): {Path("/tmp/example"): ["."]}}

            self.assertEqual(cmd_stage_dialog(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"], operation="stage")

    def test_stage_dialog_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["stage-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend", return_value={}), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(cmd_stage_dialog(args), 1)

    def test_revert_dialog_runs_dialog_inside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["revert-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend") as group_by_backend, mock.patch(
            "nemovcs.ui.revert_dialog.run",
            return_value=0,
        ) as run_dialog:
            group_by_backend.return_value = {object(): {Path("/tmp/example"): ["."]}}

            self.assertEqual(cmd_revert_dialog(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"])

    def test_revert_dialog_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["revert-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend", return_value={}), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(cmd_revert_dialog(args), 1)

    def test_rename_dialog_runs_dialog_inside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["rename-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend") as group_by_backend, (
            mock.patch(
                "nemovcs.ui.rename_dialog.run",
                return_value=0,
            )
        ) as run_dialog:
            group_by_backend.return_value = {object(): {Path("/tmp/example"): ["."]}}

            self.assertEqual(cmd_rename_dialog(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"])

    def test_rename_dialog_rejects_multiple_paths(self):
        parser = build_parser()
        args = parser.parse_args(["rename-dialog", "/tmp/one", "/tmp/two"])

        with mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(cmd_rename_dialog(args), 1)

    def test_rename_dialog_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["rename-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.backends.group_by_backend", return_value={}), (
            mock.patch("sys.stderr", new=io.StringIO())
        ):
            self.assertEqual(cmd_rename_dialog(args), 1)


class InitCommandTest(unittest.TestCase):
    def test_init_phases_builds_git_init_with_branch(self):
        phases = init_phases(["/tmp/newrepo"], "main")

        self.assertEqual(len(phases), 1)
        self.assertEqual(str(phases[0].cwd), "/tmp/newrepo")
        self.assertEqual(
            phases[0].command,
            ("git", "-C", "/tmp/newrepo", "init", "-b", "main"),
        )

    def test_cmd_init_dialog_runs_logger_with_init_phase(self):
        args = argparse.Namespace(paths=["/tmp/newrepo"], branch="trunk")

        with mock.patch("nemovcs.ui.logger.run", return_value=0) as run, mock.patch(
            "nemovcs.statusd_dbus.call_seen"
        ):
            self.assertEqual(cmd_init_dialog(args), 0)

        run.assert_called_once()
        title, phases = run.call_args[0]
        self.assertEqual(title, "Create Repository")
        self.assertEqual(
            phases[0].command,
            ("git", "-C", "/tmp/newrepo", "init", "-b", "trunk"),
        )

    def test_cmd_init_dialog_notifies_daemon_on_success(self):
        args = argparse.Namespace(paths=["/tmp/newrepo"], branch="main")

        with mock.patch("nemovcs.ui.logger.run", return_value=0), mock.patch(
            "nemovcs.statusd_dbus.call_seen"
        ) as seen:
            self.assertEqual(cmd_init_dialog(args), 0)

        seen.assert_called_once_with(["/tmp/newrepo"])

    def test_cmd_init_dialog_skips_notify_on_failure(self):
        args = argparse.Namespace(paths=["/tmp/newrepo"], branch="main")

        with mock.patch("nemovcs.ui.logger.run", return_value=1), mock.patch(
            "nemovcs.statusd_dbus.call_seen"
        ) as seen:
            self.assertEqual(cmd_init_dialog(args), 1)

        seen.assert_not_called()


class PublishCommandTest(unittest.TestCase):
    def test_cmd_publish_dialog_runs_dialog_and_notifies_on_success(self):
        args = argparse.Namespace(paths=["/tmp/repo"], forge="github")

        with mock.patch(
            "nemovcs.ui.publish_dialog.run", return_value=0
        ) as run, mock.patch("nemovcs.statusd_dbus.call_seen") as seen:
            self.assertEqual(cmd_publish_dialog(args), 0)

        run.assert_called_once_with(["/tmp/repo"], forge_id="github")
        seen.assert_called_once_with(["/tmp/repo"])

    def test_cmd_publish_dialog_skips_notify_on_failure(self):
        args = argparse.Namespace(paths=["/tmp/repo"], forge="github")

        with mock.patch(
            "nemovcs.ui.publish_dialog.run", return_value=1
        ), mock.patch("nemovcs.statusd_dbus.call_seen") as seen:
            self.assertEqual(cmd_publish_dialog(args), 1)

        seen.assert_not_called()


class ForgeCommandTest(unittest.TestCase):
    def _backend(self):
        backend = mock.Mock()
        backend.id = "git"
        return backend

    def test_runs_action_command_for_detected_forge(self):
        args = argparse.Namespace(action="open", paths=["/tmp/repo"])
        hosting = mock.Mock()
        hosting.is_available.return_value = True
        hosting.run.return_value = ["gh", "browse"]

        with mock.patch(
            "nemovcs.backends.detect_root",
            return_value=(self._backend(), Path("/tmp/repo")),
        ), mock.patch(
            "nemovcs.git.remote_url", return_value="git@github.com:o/r.git"
        ), mock.patch(
            "nemovcs.forge.detect_forge", return_value=hosting
        ), mock.patch(
            "nemovcs.cli.subprocess.Popen"
        ) as popen:
            self.assertEqual(cmd_forge(args), 0)

        hosting.run.assert_called_once_with("open", "/tmp/repo")
        popen.assert_called_once_with(["gh", "browse"], cwd="/tmp/repo")

    def test_reports_unknown_action(self):
        args = argparse.Namespace(action="mystery", paths=["/tmp/repo"])
        hosting = mock.Mock()
        hosting.is_available.return_value = True
        hosting.run.return_value = []

        with mock.patch(
            "nemovcs.backends.detect_root",
            return_value=(self._backend(), Path("/tmp/repo")),
        ), mock.patch(
            "nemovcs.git.remote_url", return_value="git@github.com:o/r.git"
        ), mock.patch(
            "nemovcs.forge.detect_forge", return_value=hosting
        ), mock.patch(
            "nemovcs.cli.subprocess.Popen"
        ) as popen, mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(cmd_forge(args), 1)

        popen.assert_not_called()

    def test_reports_when_no_forge_detected(self):
        args = argparse.Namespace(action="open", paths=["/tmp/repo"])

        with mock.patch(
            "nemovcs.backends.detect_root",
            return_value=(self._backend(), Path("/tmp/repo")),
        ), mock.patch(
            "nemovcs.git.remote_url", return_value="git@example.com:o/r.git"
        ), mock.patch(
            "nemovcs.forge.detect_forge", return_value=None
        ), mock.patch(
            "nemovcs.cli.subprocess.Popen"
        ) as popen, mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(cmd_forge(args), 1)

        popen.assert_not_called()

    def test_reports_when_not_a_worktree(self):
        args = argparse.Namespace(action="open", paths=["/tmp/plain"])

        with mock.patch(
            "nemovcs.backends.detect_root", return_value=None
        ), mock.patch(
            "nemovcs.cli.subprocess.Popen"
        ) as popen, mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(cmd_forge(args), 1)

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
