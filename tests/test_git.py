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

    def test_parse_status_porcelain_v2_for_commit_items(self):
        data = (
            b"1 .M N... 100644 100644 100644 "
            b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
            b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa src/app.py\0"
            b"? notes.txt\0"
            b"2 R. N... 100644 100644 100644 "
            b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb "
            b"cccccccccccccccccccccccccccccccccccccccc R100 new.py\0old.py\0"
            b"u UU N... 100644 100644 100644 100644 "
            b"dddddddddddddddddddddddddddddddddddddddd "
            b"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee "
            b"ffffffffffffffffffffffffffffffffffffffff conflict.txt\0"
        )

        items = git.parse_status_porcelain_v2_z(self.root, data)

        self.assertEqual([item.path for item in items], [
            "src/app.py",
            "notes.txt",
            "new.py",
            "conflict.txt",
        ])
        self.assertEqual(items[0].status, "modified")
        self.assertTrue(items[0].default_selected)
        self.assertEqual(items[1].status, "untracked")
        self.assertFalse(items[1].default_selected)
        self.assertEqual(items[2].status, "renamed")
        self.assertEqual(items[2].stage_paths, ("old.py", "new.py"))
        self.assertEqual(items[3].status, "conflicted")
        self.assertFalse(items[3].default_selected)

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

    def test_commit_paths_commits_explicit_paths(self):
        path = self.root / "tracked.txt"
        path.write_text("old\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        path.write_text("new\n", encoding="utf-8")

        results = git.commit_paths(self.root, ["tracked.txt"], "update tracked")

        self.assertTrue(all(result.ok for result in results))
        log = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(log.stdout.strip(), "update tracked")


if __name__ == "__main__":
    unittest.main()
