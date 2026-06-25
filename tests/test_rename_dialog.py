from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nemovcs.backends.base import BackendCommandPhase
from nemovcs.backends.git import GitBackend
from nemovcs.ui.rename_dialog import (
    RenameDialog,
    RenameSource,
    rename_phases,
    validate_rename_target,
)


class RenameDialogTest(unittest.TestCase):
    def test_validate_rename_target_accepts_new_sibling_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = RenameSource(
                backend=GitBackend(),
                root=root,
                path=root / "src" / "app.py",
                relpath="src/app.py",
            )

            self.assertEqual(validate_rename_target(source, "main.py"), "")

    def test_validate_rename_target_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "src" / "app.py"
            source_path.parent.mkdir()
            (source_path.parent / "existing.py").write_text("", encoding="utf-8")
            source = RenameSource(
                backend=GitBackend(),
                root=root,
                path=source_path,
                relpath="src/app.py",
            )

            cases = (
                ("", "Enter a new name."),
                ("/tmp/main.py", "relative"),
                ("../main.py", "single"),
                ("nested/main.py", "single"),
                (".", "Enter a new name."),
                ("app.py", "different"),
                ("existing.py", "already exists"),
            )

            for target, expected in cases:
                with self.subTest(target=target):
                    self.assertIn(expected, validate_rename_target(source, target))

    def test_rename_phases_build_relative_target_path(self):
        root = Path("/tmp/repo")
        source = RenameSource(
            backend=GitBackend(),
            root=root,
            path=root / "src" / "app.py",
            relpath="src/app.py",
        )
        phase = BackendCommandPhase(
            title="Rename app.py",
            cwd=root,
            command=("fake", "rename"),
        )

        with mock.patch(
            "nemovcs.ui.rename_dialog.backends.rename_phases",
            return_value=[phase],
        ) as backend_rename_phases:
            self.assertEqual(rename_phases(source, "main.py"), [phase])

        backend_rename_phases.assert_called_once_with(
            root,
            "src/app.py",
            "src/main.py",
        )

    def test_successful_rename_hides_dialog_until_logger_closes(self):
        class FakeDialog:
            def __init__(self):
                self.rename_completed = False
                self.hidden = False
                self.destroyed = False
                self.active_logger = object()

            def hide(self):
                self.hidden = True

            def destroy(self):
                self.destroyed = True

        dialog = FakeDialog()

        RenameDialog.on_rename_logger_complete(dialog, True, [])

        self.assertTrue(dialog.rename_completed)
        self.assertTrue(dialog.hidden)
        self.assertFalse(dialog.destroyed)

        RenameDialog.on_rename_logger_destroyed(dialog, object())

        self.assertIsNone(dialog.active_logger)
        self.assertTrue(dialog.destroyed)


if __name__ == "__main__":
    unittest.main()
