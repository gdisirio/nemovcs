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
    cmd_log,
    cmd_push,
    cmd_stage_dialog,
    cmd_status,
    cmd_status_dialog,
    cmd_svn_meld_diff,
    cmd_update,
    log_phases,
    push_phases,
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


if __name__ == "__main__":
    unittest.main()
