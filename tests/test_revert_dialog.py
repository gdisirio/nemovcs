from pathlib import Path
import unittest
from unittest import mock

from nemovcs.backends.base import BackendChangeItem
from nemovcs.ui.revert_dialog import RevertDialog, revert_phases


class RevertDialogCommandTest(unittest.TestCase):
    def test_revert_phases_discard_git_index_and_worktree_changes(self):
        root = Path("/tmp/example")

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True):
            phases = revert_phases({root: ["src/app.py"]})

        self.assertEqual(
            phases[0].command,
            (
                "git",
                "-C",
                str(root),
                "restore",
                "--staged",
                "--worktree",
                "--",
                "src/app.py",
            ),
        )

    def test_default_selection_excludes_untracked_files(self):
        root = Path("/tmp/example")
        tracked = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
        )
        untracked = BackendChangeItem(
            backend_id="git",
            root=root,
            path="new.txt",
            status="untracked",
            tracked=False,
        )

        self.assertTrue(RevertDialog.default_selected(tracked))
        self.assertFalse(RevertDialog.default_selected(untracked))


if __name__ == "__main__":
    unittest.main()
