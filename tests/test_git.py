from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
