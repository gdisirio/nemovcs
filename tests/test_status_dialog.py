from pathlib import Path
import unittest

from nemovcs import git
from nemovcs.ui.status_dialog import StatusDialog, format_status_output


class StatusDialogTest(unittest.TestCase):
    def test_format_status_output_preserves_raw_single_repo_output(self):
        result = git.GitResult(
            ("git",),
            Path("/tmp/example"),
            0,
            "## main...origin/main\n M src/app.py\n",
            "",
        )

        self.assertEqual(format_status_output([result]), result.stdout)

    def test_format_status_output_labels_multiple_repositories(self):
        results = [
            git.GitResult(("git",), Path("/tmp/one"), 0, " M one.py\n", ""),
            git.GitResult(("git",), Path("/tmp/two"), 0, " M two.py\n", ""),
        ]

        self.assertEqual(
            format_status_output(results),
            "# /tmp/one\n M one.py\n\n# /tmp/two\n M two.py\n",
        )

    def test_file_diff_command_compares_path_against_head_without_dir_diff(self):
        root = Path("/tmp/example")
        item = git.CommitItem(
            root=root,
            path="src/app.py",
            status="modified",
            index_status=".",
            worktree_status="M",
        )
        dialog = StatusDialog.__new__(StatusDialog)

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
