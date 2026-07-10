from pathlib import Path
import unittest
from unittest import mock

from nemovcs.forge.base import ForgeAccount
from nemovcs.ui import publish_dialog
from nemovcs.ui.publish_dialog import (
    active_account_name,
    default_repo_name,
    publish_phases,
    publish_root,
    validate_repo_name,
)


class FakeForge:
    label = "GitHub"

    def publish_command(self, root, name, private):
        return ["gh", "repo", "create", name, "--source", root, "--push",
                "--private" if private else "--public"]


class PublishDialogHelpersTest(unittest.TestCase):
    def test_publish_root_resolves_repo_root(self):
        with mock.patch("nemovcs.git.repo_root", return_value="/tmp/repo"):
            self.assertEqual(publish_root(["/tmp/repo/src"]), Path("/tmp/repo"))

    def test_publish_root_none_outside_repo(self):
        with mock.patch("nemovcs.git.repo_root", return_value=None):
            self.assertIsNone(publish_root(["/tmp/plain"]))

    def test_default_repo_name_uses_directory_name(self):
        self.assertEqual(default_repo_name(Path("/tmp/my-project")), "my-project")
        self.assertEqual(default_repo_name(None), "")

    def test_validate_repo_name(self):
        self.assertEqual(validate_repo_name("good-name"), "")
        self.assertNotEqual(validate_repo_name(""), "")
        self.assertNotEqual(validate_repo_name("has space"), "")

    def test_publish_phases_wraps_forge_command(self):
        phases = publish_phases(FakeForge(), Path("/tmp/repo"), "myrepo", True)

        self.assertEqual(len(phases), 1)
        self.assertEqual(str(phases[0].cwd), "/tmp/repo")
        self.assertEqual(
            phases[0].command,
            (
                "gh", "repo", "create", "myrepo",
                "--source", "/tmp/repo", "--push", "--private",
            ),
        )

    def test_active_account_name(self):
        accounts = [
            ForgeAccount("gdisirio", active=True),
            ForgeAccount("chibios-sheriff", active=False),
        ]
        self.assertEqual(active_account_name(accounts), "gdisirio")
        self.assertIsNone(active_account_name([]))

    def test_publish_phases_is_a_single_publish_command(self):
        phases = publish_phases(FakeForge(), Path("/tmp/repo"), "myrepo", False)

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].command[-1], "--public")


if __name__ == "__main__":
    unittest.main()
