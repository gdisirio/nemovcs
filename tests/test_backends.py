from pathlib import Path
import unittest
from unittest import mock

from nemovcs import backends
from nemovcs import git
from nemovcs.backends.base import (
    BackendChangeItem,
    BackendStatusItem,
    BackendWorktreeIdentity,
)
from nemovcs.backends.git import GitBackend


class BackendRegistryTest(unittest.TestCase):
    def test_git_backend_is_registered(self):
        registered = backends.registered_backends()

        self.assertEqual([backend.id for backend in registered], ["git"])
        self.assertIsInstance(registered[0], GitBackend)

    def test_backend_by_id_returns_registered_backend(self):
        backend = backends.backend_by_id("git")

        self.assertIsNotNone(backend)
        assert backend is not None
        self.assertEqual(backend.id, "git")

    def test_backend_by_id_returns_none_for_unknown_backend(self):
        self.assertIsNone(backends.backend_by_id("svn"))

    def test_detect_backend_returns_git_for_git_worktree(self):
        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True):
            backend = backends.detect_backend(Path("/tmp/repo"))

        self.assertIsNotNone(backend)
        self.assertEqual(backend.id, "git")

    def test_detect_backend_returns_none_outside_worktree(self):
        with mock.patch("nemovcs.git.is_inside_worktree", return_value=False):
            self.assertIsNone(backends.detect_backend(Path("/tmp/repo")))

    def test_detect_root_returns_backend_and_root(self):
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.repo_root", return_value=root):
            detected = backends.detect_root(root / "src")

        self.assertIsNotNone(detected)
        backend, detected_root = detected
        self.assertEqual(backend.id, "git")
        self.assertEqual(detected_root, root)

    def test_detect_worktree_identity_returns_backend_and_identity(self):
        root = Path("/tmp/repo")
        identity = BackendWorktreeIdentity(
            root=root,
            vcs_dir=root / ".git",
            common_dir=root / ".git",
            head_label="main",
        )

        with mock.patch("nemovcs.backends.git.GitBackend.identity", return_value=identity):
            detected = backends.detect_worktree_identity(root)

        self.assertIsNotNone(detected)
        backend, detected_identity = detected
        self.assertEqual(backend.id, "git")
        self.assertEqual(detected_identity, identity)

    def test_group_by_backend_groups_git_roots(self):
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}):
            grouped = backends.group_by_backend([root / "src/app.py"])

        backend = next(iter(grouped))
        self.assertEqual(backend.id, "git")
        self.assertEqual(grouped[backend], {root: ["src/app.py"]})

    def test_commit_items_collects_items_from_registered_backend(self):
        root = Path("/tmp/repo")
        item = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
        )

        with mock.patch(
            "nemovcs.backends.git.GitBackend.commit_items",
            return_value={root: [item]},
        ):
            self.assertEqual(backends.commit_items([root]), {root: [item]})

    def test_current_branch_uses_detected_backend(self):
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True), mock.patch(
            "nemovcs.git.current_branch",
            return_value="main",
        ) as current_branch:
            self.assertEqual(backends.current_branch(root), "main")

        current_branch.assert_called_once_with(root)

    def test_git_backend_delegates_status_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.status", return_value=expected) as status:
            result = backend.status([Path("/tmp/repo")])

        self.assertIs(result, expected)
        status.assert_called_once_with([Path("/tmp/repo")])

    def test_git_backend_translates_commit_items(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.commit_items") as commit_items:
            commit_items.return_value = {
                root: [
                    git.CommitItem(
                        root=root,
                        path="src/app.py",
                        status="modified",
                        index_status=".",
                        worktree_status="M",
                    ),
                    git.CommitItem(
                        root=root,
                        path="new.txt",
                        status="untracked",
                        index_status="?",
                        worktree_status="?",
                        tracked=False,
                    ),
                ]
            }

            result = backend.commit_items([root])

        self.assertEqual(
            result,
            {
                root: [
                    BackendChangeItem(
                        backend_id="git",
                        root=root,
                        path="src/app.py",
                        status="modified",
                    ),
                    BackendChangeItem(
                        backend_id="git",
                        root=root,
                        path="new.txt",
                        status="untracked",
                        tracked=False,
                    ),
                ]
            },
        )

    def test_git_backend_scan_status_translates_porcelain_items(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.run_git") as run_git, mock.patch(
            "nemovcs.git.parse_status_porcelain_v2_z"
        ) as parse_status:
            run_git.return_value = git.GitResult(("git",), root, 0, "raw", "")
            parse_status.return_value = [
                git.CommitItem(
                    root=root,
                    path="tracked.txt",
                    status="modified",
                    index_status=".",
                    worktree_status="M",
                ),
                git.CommitItem(
                    root=root,
                    path="renamed.txt",
                    old_path="old.txt",
                    status="renamed",
                    index_status="R",
                    worktree_status=".",
                ),
                git.CommitItem(
                    root=root,
                    path="conflicted.txt",
                    status="conflicted",
                    index_status="U",
                    worktree_status="U",
                    conflicted=True,
                ),
            ]

            result = backend.scan_status(root)

        self.assertTrue(result.ok)
        self.assertEqual(
            result.items,
            (
                BackendStatusItem(path="tracked.txt"),
                BackendStatusItem(path="renamed.txt", old_path="old.txt"),
                BackendStatusItem(path="conflicted.txt", conflicted=True),
            ),
        )
        parse_status.assert_called_once_with(
            root,
            b"raw",
        )

    def test_git_backend_scan_status_reports_command_error(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.run_git") as run_git:
            run_git.return_value = git.GitResult(("git",), root, 128, "", "fatal\n")

            result = backend.scan_status(root)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "fatal")
        self.assertEqual(result.items, ())

    def test_git_backend_builds_identity_from_rev_parse(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.run_git") as run_git:
            run_git.side_effect = [
                git.GitResult(
                    ("git",),
                    root,
                    0,
                    "/tmp/repo\n/tmp/repo/.git\n/tmp/repo/.git\n",
                    "",
                ),
                git.GitResult(("git",), root, 0, "main\n", ""),
            ]

            identity = backend.identity(root / "src")

        self.assertEqual(
            identity,
            BackendWorktreeIdentity(
                root=root,
                vcs_dir=root / ".git",
                common_dir=root / ".git",
                head_label="main",
            ),
        )

    def test_git_backend_identity_returns_none_outside_worktree(self):
        backend = GitBackend()

        with mock.patch("nemovcs.git.run_git") as run_git:
            run_git.return_value = git.GitResult(("git",), Path("/tmp"), 128, "", "fatal")

            self.assertIsNone(backend.identity(Path("/tmp")))


if __name__ == "__main__":
    unittest.main()
