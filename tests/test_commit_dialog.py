from pathlib import Path
import unittest

from nemovcs import git
from nemovcs.ui.commit_dialog import CommitDialog


class CommitDialogCommandTest(unittest.TestCase):
    def test_file_diff_command_compares_path_against_head_without_dir_diff(self):
        root = Path("/tmp/example")
        item = git.CommitItem(
            root=root,
            path="src/app.py",
            status="modified",
            index_status=".",
            worktree_status="M",
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


if __name__ == "__main__":
    unittest.main()
