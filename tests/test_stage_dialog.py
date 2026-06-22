from pathlib import Path
import unittest

from nemovcs import git
from nemovcs.ui.stage_dialog import StageDialog, stage_phases


class StageDialogCommandTest(unittest.TestCase):
    def test_stage_phases_add_checked_paths_grouped_by_repository(self):
        root = Path("/tmp/example")
        other_root = Path("/tmp/other")

        phases = stage_phases(
            {
                root: ["src/app.py", "README.md"],
                other_root: ["lib/tool.py"],
            }
        )

        self.assertEqual([phase.title for phase in phases], ["Stage example", "Stage other"])
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "add", "--", "src/app.py", "README.md"),
        )
        self.assertEqual(
            phases[1].command,
            ("git", "-C", str(other_root), "add", "--", "lib/tool.py"),
        )

    def test_stage_phases_skip_empty_repositories(self):
        root = Path("/tmp/example")

        self.assertEqual(stage_phases({root: []}), [])

    def test_default_selection_includes_untracked_but_excludes_conflicted(self):
        root = Path("/tmp/example")
        untracked = git.CommitItem(
            root=root,
            path="new.txt",
            status="untracked",
            index_status="?",
            worktree_status="?",
            tracked=False,
        )
        conflicted = git.CommitItem(
            root=root,
            path="conflict.txt",
            status="conflicted",
            index_status="U",
            worktree_status="U",
            conflicted=True,
        )

        self.assertTrue(StageDialog.default_selected(untracked))
        self.assertFalse(StageDialog.default_selected(conflicted))

    def test_file_diff_command_uses_item_repository(self):
        root = Path("/tmp/example")
        item = git.CommitItem(
            root=root,
            path="src/app.py",
            status="modified",
            index_status=".",
            worktree_status="M",
        )

        command = StageDialog.file_diff_command(StageDialog.__new__(StageDialog), item)

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


if __name__ == "__main__":
    unittest.main()
