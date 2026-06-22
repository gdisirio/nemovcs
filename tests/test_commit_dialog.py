from pathlib import Path
import unittest
from unittest import mock

from nemovcs.backends.base import BackendChangeItem
from nemovcs.ui.commit_dialog import CommitDialog


class CommitDialogCommandTest(unittest.TestCase):
    def test_file_diff_command_compares_path_against_head_without_dir_diff(self):
        root = Path("/tmp/example")
        item = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
        )
        dialog = CommitDialog.__new__(CommitDialog)
        dialog.root = root

        command = dialog.file_diff_command(item)

        self.assertEqual(
            command,
            [
                "git",
                "-C",
                str(root),
                "difftool",
                "--tool=meld",
                "--no-prompt",
                "HEAD",
                "--",
                "src/app.py",
            ],
        )
        self.assertNotIn("--dir-diff", command)

    def test_commit_phases_are_reusable_logger_phases(self):
        root = Path("/tmp/example")
        dialog = CommitDialog.__new__(CommitDialog)
        dialog.root = root

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True):
            phases = dialog.commit_phases(["src/app.py"], "message")

        self.assertEqual([phase.title for phase in phases], [
            "Stage selected files",
            "Create commit",
        ])
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "add", "--", "src/app.py"),
        )
        self.assertEqual(
            phases[1].command,
            (
                "git",
                "-C",
                str(root),
                "commit",
                "-m",
                "message",
                "--",
                "src/app.py",
            ),
        )

    def test_successful_commit_hides_dialog_until_logger_closes(self):
        class FakeDialog:
            def __init__(self):
                self.commit_completed = False
                self.hidden = False
                self.destroyed = False
                self.active_logger = object()

            def hide(self):
                self.hidden = True

            def destroy(self):
                self.destroyed = True

        dialog = FakeDialog()

        CommitDialog.on_commit_logger_complete(dialog, True, [])

        self.assertTrue(dialog.commit_completed)
        self.assertTrue(dialog.hidden)
        self.assertFalse(dialog.destroyed)

        CommitDialog.on_commit_logger_destroyed(dialog, object())

        self.assertIsNone(dialog.active_logger)
        self.assertTrue(dialog.destroyed)


if __name__ == "__main__":
    unittest.main()
