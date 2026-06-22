from pathlib import Path
import unittest
from unittest import mock

from nemovcs.backends.base import BackendChangeItem
from nemovcs.ui.stage_dialog import StageDialog, stage_phases


class StageDialogCommandTest(unittest.TestCase):
    def test_stage_phases_add_checked_paths_grouped_by_repository(self):
        root = Path("/tmp/example")
        other_root = Path("/tmp/other")

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True):
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

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True):
            self.assertEqual(stage_phases({root: []}), [])

    def test_default_selection_includes_untracked_but_excludes_conflicted(self):
        root = Path("/tmp/example")
        untracked = BackendChangeItem(
            backend_id="git",
            root=root,
            path="new.txt",
            status="untracked",
            tracked=False,
        )
        conflicted = BackendChangeItem(
            backend_id="git",
            root=root,
            path="conflict.txt",
            status="conflicted",
            conflicted=True,
        )

        self.assertTrue(StageDialog.default_selected(untracked))
        self.assertFalse(StageDialog.default_selected(conflicted))

    def test_file_diff_command_uses_item_repository(self):
        root = Path("/tmp/example")
        item = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
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

    def test_successful_stage_hides_dialog_until_logger_closes(self):
        class FakeDialog:
            def __init__(self):
                self.stage_completed = False
                self.hidden = False
                self.destroyed = False
                self.active_logger = object()

            def hide(self):
                self.hidden = True

            def destroy(self):
                self.destroyed = True

        dialog = FakeDialog()

        StageDialog.on_stage_logger_complete(dialog, True, [])

        self.assertTrue(dialog.stage_completed)
        self.assertTrue(dialog.hidden)
        self.assertFalse(dialog.destroyed)

        StageDialog.on_stage_logger_destroyed(dialog, object())

        self.assertIsNone(dialog.active_logger)
        self.assertTrue(dialog.destroyed)

    def test_failed_stage_keeps_dialog_open_and_refreshes(self):
        class FakeButton:
            def __init__(self):
                self.sensitive = None

            def set_sensitive(self, value):
                self.sensitive = value

        class FakeDialog:
            def __init__(self):
                self.stage_completed = False
                self.close_button = FakeButton()
                self.stage_button = FakeButton()
                self.deletable = None
                self.refreshed = False

            def set_deletable(self, value):
                self.deletable = value

            def load_items(self):
                self.refreshed = True

        dialog = FakeDialog()

        StageDialog.on_stage_logger_complete(dialog, False, [1])

        self.assertFalse(dialog.stage_completed)
        self.assertTrue(dialog.deletable)
        self.assertTrue(dialog.close_button.sensitive)
        self.assertTrue(dialog.stage_button.sensitive)
        self.assertTrue(dialog.refreshed)


if __name__ == "__main__":
    unittest.main()
