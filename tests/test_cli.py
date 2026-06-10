import unittest

from nemovcs.cli import build_parser


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

    def test_settings_and_about_parse(self):
        parser = build_parser()

        self.assertEqual(parser.parse_args(["settings"]).command, "settings")
        self.assertEqual(parser.parse_args(["about"]).command, "about")


if __name__ == "__main__":
    unittest.main()
