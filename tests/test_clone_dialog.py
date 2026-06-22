from pathlib import Path
import tempfile
import unittest

from nemovcs.ui.clone_dialog import (
    CloneDialog,
    clone_phases,
    derive_target_name,
    validate_clone_target,
)


class CloneDialogTest(unittest.TestCase):
    def test_derive_target_name_from_common_git_urls(self):
        cases = {
            "https://github.com/gdisirio/nemovcs.git": "nemovcs",
            "git@github.com:gdisirio/nemovcs.git": "nemovcs",
            "ssh://git@github.com/gdisirio/nemovcs.git": "nemovcs",
            "https://example.invalid/group/repo/": "repo",
            "repo name.git": "repo-name",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(derive_target_name(url), expected)

    def test_validate_clone_target_accepts_new_relative_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                validate_clone_target(Path(tmp), "https://example.invalid/repo.git", "repo"),
                "",
            )

    def test_validate_clone_target_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "existing").mkdir()

            cases = (
                ("", "repo", "Enter a repository URL."),
                ("https://example.invalid/repo.git", "", "Enter a target folder."),
                ("https://example.invalid/repo.git", "/tmp/repo", "relative"),
                ("https://example.invalid/repo.git", "../repo", "single folder"),
                ("https://example.invalid/repo.git", "nested/repo", "single folder"),
                ("https://example.invalid/repo.git", "existing", "already exists"),
            )

            for url, target, expected in cases:
                with self.subTest(url=url, target=target):
                    self.assertIn(expected, validate_clone_target(base, url, target))

    def test_clone_phases_build_git_clone_command(self):
        base = Path("/tmp")

        phases = clone_phases(base, "https://example.invalid/repo.git", "repo")

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Clone repository")
        self.assertEqual(phases[0].cwd, base)
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(base), "clone", "https://example.invalid/repo.git", "repo"),
        )

    def test_clone_phases_can_recurse_submodules(self):
        base = Path("/tmp")

        phases = clone_phases(
            base,
            "https://example.invalid/repo.git",
            "repo",
            recurse_submodules=True,
        )

        self.assertEqual(
            phases[0].command,
            (
                "git",
                "-C",
                str(base),
                "clone",
                "--recurse-submodules",
                "https://example.invalid/repo.git",
                "repo",
            ),
        )

    def test_successful_clone_hides_dialog_until_logger_closes(self):
        class FakeDialog:
            def __init__(self):
                self.clone_completed = False
                self.hidden = False
                self.destroyed = False
                self.active_logger = object()

            def hide(self):
                self.hidden = True

            def destroy(self):
                self.destroyed = True

        dialog = FakeDialog()

        CloneDialog.on_clone_logger_complete(dialog, True, [])

        self.assertTrue(dialog.clone_completed)
        self.assertTrue(dialog.hidden)
        self.assertFalse(dialog.destroyed)

        CloneDialog.on_clone_logger_destroyed(dialog, object())

        self.assertIsNone(dialog.active_logger)
        self.assertTrue(dialog.destroyed)


if __name__ == "__main__":
    unittest.main()
