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


if __name__ == "__main__":
    unittest.main()
