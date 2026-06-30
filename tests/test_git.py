from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from nemovcs import git


def have_git() -> bool:
    return shutil.which("git") is not None


class GitExecutableAvailabilityTest(unittest.TestCase):
    def test_run_git_reports_missing_executable_as_failed_result(self):
        with mock.patch("nemovcs.git.subprocess.run", side_effect=FileNotFoundError):
            result = git.run_git("/tmp", ["status"])

        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "git executable not found\n")

    def test_run_git_check_raises_for_missing_executable(self):
        with mock.patch("nemovcs.git.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(git.GitError) as raised:
                git.run_git("/tmp", ["status"], check=True)

        self.assertEqual(raised.exception.result.returncode, 127)

    def test_current_branch_name_returns_none_for_detached_head(self):
        result = git.GitResult(("git",), Path("/tmp/repo"), 0, "\n", "")

        with mock.patch("nemovcs.git.run_git", return_value=result):
            self.assertIsNone(git.current_branch_name("/tmp/repo"))

    def test_recent_branches_are_sorted_by_git_output_and_limited(self):
        result = git.GitResult(
            ("git",),
            Path("/tmp/repo"),
            0,
            "feature/new\nmain\nrelease/1\n",
            "",
        )

        with mock.patch("nemovcs.git.run_git", return_value=result):
            self.assertEqual(
                git.recent_branches("/tmp/repo", limit=2),
                ["feature/new", "main"],
            )

    def test_recent_branches_returns_empty_on_git_failure(self):
        result = git.GitResult(("git",), Path("/tmp/repo"), 1, "", "failed")

        with mock.patch("nemovcs.git.run_git", return_value=result):
            self.assertEqual(git.recent_branches("/tmp/repo"), [])

    def test_worktree_dirty_uses_porcelain_status(self):
        clean = git.GitResult(("git",), Path("/tmp/repo"), 0, "", "")
        dirty = git.GitResult(("git",), Path("/tmp/repo"), 0, " M app.py\n", "")

        with mock.patch("nemovcs.git.run_git", return_value=clean):
            self.assertFalse(git.worktree_dirty("/tmp/repo"))
        with mock.patch("nemovcs.git.run_git", return_value=dirty):
            self.assertTrue(git.worktree_dirty("/tmp/repo"))

    def test_parse_worktree_branch_locations(self):
        data = (
            "worktree /tmp/repo\n"
            "HEAD 1111111111111111111111111111111111111111\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /tmp/feature\n"
            "HEAD 2222222222222222222222222222222222222222\n"
            "branch refs/heads/feature/new\n"
            "\n"
            "worktree /tmp/detached\n"
            "HEAD 3333333333333333333333333333333333333333\n"
            "detached\n"
            "\n"
        )

        self.assertEqual(
            git.parse_worktree_branch_locations(data),
            {
                "main": Path("/tmp/repo"),
                "feature/new": Path("/tmp/feature"),
            },
        )

    def test_worktree_branch_locations_returns_empty_on_git_failure(self):
        result = git.GitResult(("git",), Path("/tmp/repo"), 1, "", "failed")

        with mock.patch("nemovcs.git.run_git", return_value=result):
            self.assertEqual(git.worktree_branch_locations("/tmp/repo"), {})


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

    def test_diff_uses_file_meld_difftool_for_file(self):
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
                "--no-prompt",
                "--",
                "tracked.txt",
            ],
            timeout=3600,
        )

    def test_diff_uses_dir_meld_difftool_for_directory(self):
        fake_result = git.GitResult(("git",), self.root, 0, "", "")
        with mock.patch("nemovcs.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {self.root: ["."]}
            with mock.patch("nemovcs.git.shutil.which", return_value="/usr/bin/meld"):
                with mock.patch(
                    "nemovcs.git.run_git", return_value=fake_result
                ) as run_git:
                    results = git.diff([self.root])

        self.assertEqual(results, [fake_result])
        run_git.assert_called_once_with(
            self.root,
            [
                "difftool",
                "--tool=meld",
                "--dir-diff",
                "--no-prompt",
                "--",
                ".",
            ],
            timeout=3600,
        )

    def test_diff_reports_missing_meld(self):
        with mock.patch("nemovcs.git.shutil.which", return_value=None):
            results = git.diff([self.root])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 127)
        self.assertIn(git.MELD_MISSING_MESSAGE, results[0].stderr)

    def test_diff_commands_builds_file_meld_difftool_command_for_file(self):
        with mock.patch("nemovcs.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {self.root: ["tracked.txt"]}
            with mock.patch("nemovcs.git.shutil.which", return_value="/usr/bin/meld"):
                results = git.diff_commands([self.root / "tracked.txt"])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 0)
        self.assertEqual(
            results[0].args,
            (
                "git",
                "-C",
                str(self.root),
                "difftool",
                "--tool=meld",
                "--no-prompt",
                "--",
                "tracked.txt",
            ),
        )

    def test_diff_commands_builds_dir_meld_difftool_command_for_directory(self):
        with mock.patch("nemovcs.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {self.root: ["."]}
            with mock.patch("nemovcs.git.shutil.which", return_value="/usr/bin/meld"):
                results = git.diff_commands([self.root])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].returncode, 0)
        self.assertEqual(
            results[0].args,
            (
                "git",
                "-C",
                str(self.root),
                "difftool",
                "--tool=meld",
                "--dir-diff",
                "--no-prompt",
                "--",
                ".",
            ),
        )

    def test_diff_commands_reports_missing_meld(self):
        with mock.patch("nemovcs.git.shutil.which", return_value=None):
            results = git.diff_commands([self.root])

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

    def test_push_runs_once_per_repository(self):
        fake_result = git.GitResult(("git",), self.root, 0, "", "")
        with mock.patch("nemovcs.git.group_by_repo") as group_by_repo:
            group_by_repo.return_value = {self.root: ["tracked.txt"]}
            with mock.patch("nemovcs.git.run_git", return_value=fake_result) as run_git:
                results = git.push([self.root / "tracked.txt"])

        self.assertEqual(results, [fake_result])
        run_git.assert_called_once_with(self.root, ["push"], timeout=300)


if __name__ == "__main__":
    unittest.main()
