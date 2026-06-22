import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nemovcs.cli import (
    absolute_paths,
    build_parser,
    clone_target_visible,
    cmd_action_visible,
    cmd_stage_dialog,
    log_phases,
    push_phases,
)


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

    def test_clone_target_visible_accepts_non_worktree_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("nemovcs.cli.git.is_inside_worktree", return_value=False):
                self.assertTrue(clone_target_visible(tmp))

    def test_clone_target_visible_rejects_worktree_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("nemovcs.cli.git.is_inside_worktree", return_value=True):
                self.assertFalse(clone_target_visible(tmp))

    def test_clone_target_visible_rejects_files_without_git_check(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with mock.patch("nemovcs.cli.git.is_inside_worktree") as is_inside_worktree:
                self.assertFalse(clone_target_visible(tmp.name))

        is_inside_worktree.assert_not_called()

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

    def test_log_dialog_accepts_limit_and_paths(self):
        parser = build_parser()

        args = parser.parse_args(["log-dialog", "-n", "7", "/tmp/example"])

        self.assertEqual(args.command, "log-dialog")
        self.assertEqual(args.limit, 7)
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_log_phases_run_log_in_each_grouped_repository(self):
        root = Path("/tmp/example")

        with mock.patch("nemovcs.cli.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {root: ["src/app.py"]}
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

        with mock.patch("nemovcs.cli.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {root: ["src/app.py"]}
            phases = push_phases(["/tmp/example/src/app.py"])

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Push example")
        self.assertEqual(phases[0].cwd, root)
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "push"),
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

        args = parser.parse_args(["stage-dialog", "/tmp/example"])

        self.assertEqual(args.command, "stage-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_clone_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["clone-dialog", "/tmp/example"])

        self.assertEqual(args.command, "clone-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])

    def test_clone_dialog_runs_dialog_for_clone_target(self):
        parser = build_parser()
        args = parser.parse_args(["clone-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.clone_target_visible", return_value=True), mock.patch(
            "nemovcs.ui.clone_dialog.run",
            return_value=0,
        ) as run_dialog:
            self.assertEqual(args.func(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"])

    def test_clone_dialog_rejects_non_clone_target(self):
        parser = build_parser()
        args = parser.parse_args(["clone-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.clone_target_visible", return_value=False), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(args.func(args), 1)

    def test_stage_dialog_runs_dialog_inside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["stage-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.git.group_by_repo") as group_by_repo, mock.patch(
            "nemovcs.ui.stage_dialog.run",
            return_value=0,
        ) as run_dialog:
            group_by_repo.return_value = {Path("/tmp/example"): ["."]}

            self.assertEqual(cmd_stage_dialog(args), 0)

        run_dialog.assert_called_once_with(["/tmp/example"])

    def test_stage_dialog_rejects_paths_outside_worktree(self):
        parser = build_parser()
        args = parser.parse_args(["stage-dialog", "/tmp/example"])

        with mock.patch("nemovcs.cli.git.group_by_repo", return_value={}), mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            self.assertEqual(cmd_stage_dialog(args), 1)


if __name__ == "__main__":
    unittest.main()
