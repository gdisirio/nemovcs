import unittest
from pathlib import Path
from unittest import mock

from nemovcs.cli import build_parser, log_phases


class CliParserTest(unittest.TestCase):
    def test_run_terminal_keeps_nested_command_arguments(self):
        parser = build_parser()

        args = parser.parse_args(["run-terminal", "log", "-n", "3", "path with space"])

        self.assertEqual(args.command, "run-terminal")
        self.assertEqual(args.args, ["log", "-n", "3", "path with space"])

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

    def test_commit_dialog_accepts_paths(self):
        parser = build_parser()

        args = parser.parse_args(["commit-dialog", "/tmp/example"])

        self.assertEqual(args.command, "commit-dialog")
        self.assertEqual(args.paths, ["/tmp/example"])


if __name__ == "__main__":
    unittest.main()
