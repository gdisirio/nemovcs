from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from nemovcs import git


def have_git() -> bool:
    return shutil.which("git") is not None


@unittest.skipUnless(have_git(), "git executable is required")
class GitHelpersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "NemoVCS Test"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_inside_worktree(self):
        self.assertTrue(git.is_inside_worktree(self.root))
        self.assertFalse(git.is_inside_worktree(self.root.parent))

    def test_repo_root_from_child(self):
        child = self.root / "src"
        child.mkdir()
        self.assertEqual(git.repo_root(child), self.root)

    def test_status_reports_untracked_file(self):
        path = self.root / "new.txt"
        path.write_text("hello\n", encoding="utf-8")

        results = git.status([path])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertIn("?? new.txt", results[0].stdout)

    def test_diff_uses_meld_difftool(self):
        fake_result = git.GitResult(("git",), self.root, 0, "", "")
        with mock.patch("nemovcs.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {self.root: ["tracked.txt"]}
            with mock.patch("nemovcs.git.shutil.which", return_value="/usr/bin/meld"):
                with mock.patch(
                    "nemovcs.git.run_git", return_value=fake_result
                ) as run_git:
                    results = git.diff([self.root / "tracked.txt"])

        self.assertEqual(results, [fake_result])
        run_git.assert_called_once_with(
            self.root,
            [
                "difftool",
                "--tool=meld",
                "--dir-diff",
                "--no-prompt",
                "--",
                "tracked.txt",
            ],
            timeout=3600,
        )

    def test_diff_reports_missing_meld(self):
        with mock.patch("nemovcs.git.shutil.which", return_value=None):
            results = git.diff([self.root])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 127)
        self.assertIn(git.MELD_MISSING_MESSAGE, results[0].stderr)


if __name__ == "__main__":
    unittest.main()
