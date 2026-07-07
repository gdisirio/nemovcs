from pathlib import Path
import unittest
from unittest import mock

from nemovcs.ui import change_request_dialog
from nemovcs.ui.change_request_dialog import (
    change_request_root,
    create_phases,
    validate_title,
)


class FakeForge:
    change_request_label = "Pull Request"

    def change_request_create_command(self, root, *, title, body, base=None):
        command = ["gh", "pr", "create", "--title", title, "--body", body]
        if base:
            command += ["--base", base]
        return command


class ChangeRequestHelpersTest(unittest.TestCase):
    def test_change_request_root_resolves_repo_root(self):
        with mock.patch("nemovcs.git.repo_root", return_value="/tmp/repo"):
            self.assertEqual(
                change_request_root(["/tmp/repo/src"]), Path("/tmp/repo")
            )

    def test_change_request_root_none_outside_repo(self):
        with mock.patch("nemovcs.git.repo_root", return_value=None):
            self.assertIsNone(change_request_root(["/tmp/plain"]))

    def test_validate_title(self):
        self.assertEqual(validate_title("Fix the bug"), "")
        self.assertNotEqual(validate_title(""), "")
        self.assertNotEqual(validate_title("   "), "")

    def test_create_phases_wraps_forge_command(self):
        phases = create_phases(
            FakeForge(),
            Path("/tmp/repo"),
            title="Fix",
            body="Details",
            base="main",
        )

        self.assertEqual(len(phases), 1)
        self.assertEqual(str(phases[0].cwd), "/tmp/repo")
        self.assertEqual(phases[0].title, "Create Pull Request")
        self.assertEqual(
            phases[0].command,
            ("gh", "pr", "create", "--title", "Fix", "--body", "Details",
             "--base", "main"),
        )

    def test_create_phases_omits_empty_base(self):
        phases = create_phases(
            FakeForge(), Path("/tmp/repo"), title="Fix", body="", base=""
        )
        self.assertEqual(
            phases[0].command,
            ("gh", "pr", "create", "--title", "Fix", "--body", ""),
        )

    def test_run_rejects_unknown_action(self):
        forge = FakeForge()
        with mock.patch(
            "nemovcs.ui.change_request_dialog.forge_by_id", return_value=forge
        ), mock.patch("sys.stderr"):
            self.assertEqual(
                change_request_dialog.run(["/tmp/repo"], forge_id="github", action="bogus"),
                1,
            )

    def test_run_rejects_unknown_forge(self):
        with mock.patch(
            "nemovcs.ui.change_request_dialog.forge_by_id", return_value=None
        ), mock.patch("sys.stderr"):
            self.assertEqual(
                change_request_dialog.run(["/tmp/repo"], forge_id="nope", action="cr-create"),
                1,
            )


if __name__ == "__main__":
    unittest.main()
