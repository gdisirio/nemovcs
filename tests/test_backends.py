from pathlib import Path
import unittest
from unittest import mock

from nemovcs import backends
from nemovcs import git
from nemovcs.backends.base import (
    BackendChangeItem,
    BackendCommandPhase,
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

    def test_file_diff_command_returns_empty_for_unknown_backend(self):
        item = BackendChangeItem(
            backend_id="svn",
            root=Path("/tmp/repo"),
            path="src/app.py",
            status="modified",
        )

        self.assertEqual(backends.file_diff_command(item), [])

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

    def test_raw_status_collects_status_from_matching_backend(self):
        root = Path("/tmp/repo")
        expected = object()

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["."]}), mock.patch(
            "nemovcs.git.status",
            return_value=[expected],
        ) as status:
            self.assertEqual(backends.raw_status([root]), [expected])

        status.assert_called_once_with([root])

    def test_raw_log_collects_log_from_matching_backend(self):
        root = Path("/tmp/repo")
        expected = object()

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["."]}), mock.patch(
            "nemovcs.git.log",
            return_value=[expected],
        ) as log:
            self.assertEqual(backends.raw_log([root], 7), [expected])

        log.assert_called_once_with([root], limit=7)

    def test_raw_diff_collects_diff_from_matching_backend(self):
        root = Path("/tmp/repo")
        expected = object()

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["."]}), mock.patch(
            "nemovcs.git.diff",
            return_value=[expected],
        ) as diff:
            self.assertEqual(backends.raw_diff([root]), [expected])

        diff.assert_called_once_with([root])

    def test_diff_commands_collects_commands_from_matching_backend(self):
        root = Path("/tmp/repo")
        expected = object()

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["."]}), mock.patch(
            "nemovcs.git.diff_commands",
            return_value=[expected],
        ) as diff_commands:
            self.assertEqual(backends.diff_commands([root]), [expected])

        diff_commands.assert_called_once_with([root])

    def test_current_branch_uses_detected_backend(self):
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True), mock.patch(
            "nemovcs.git.current_branch",
            return_value="main",
        ) as current_branch:
            self.assertEqual(backends.current_branch(root), "main")

        current_branch.assert_called_once_with(root)

    def test_stage_phases_uses_detected_backend(self):
        root = Path("/tmp/repo")
        phase = BackendCommandPhase(
            title="Stage repo",
            cwd=root,
            command=("fake", "stage"),
        )

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True), mock.patch(
            "nemovcs.backends.git.GitBackend.stage_phases",
            return_value=[phase],
        ) as stage_phases:
            self.assertEqual(backends.stage_phases({root: ["src/app.py"]}), [phase])

        stage_phases.assert_called_once_with({root: ["src/app.py"]})

    def test_commit_phases_uses_detected_backend(self):
        root = Path("/tmp/repo")
        phase = BackendCommandPhase(
            title="Commit repo",
            cwd=root,
            command=("fake", "commit"),
        )

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True), mock.patch(
            "nemovcs.backends.git.GitBackend.commit_phases",
            return_value=[phase],
        ) as commit_phases:
            self.assertEqual(
                backends.commit_phases(root, ["src/app.py"], "message"),
                [phase],
            )

        commit_phases.assert_called_once_with(root, ["src/app.py"], "message")

    def test_git_backend_delegates_status_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.status", return_value=expected) as status:
            result = backend.status([Path("/tmp/repo")])

        self.assertIs(result, expected)
        status.assert_called_once_with([Path("/tmp/repo")])

    def test_git_backend_delegates_log_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.log", return_value=expected) as log:
            result = backend.log([Path("/tmp/repo")], 7)

        self.assertIs(result, expected)
        log.assert_called_once_with([Path("/tmp/repo")], limit=7)

    def test_git_backend_delegates_diff_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.diff", return_value=expected) as diff:
            result = backend.diff([Path("/tmp/repo")])

        self.assertIs(result, expected)
        diff.assert_called_once_with([Path("/tmp/repo")])

    def test_git_backend_delegates_diff_commands_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.diff_commands", return_value=expected) as diff_commands:
            result = backend.diff_commands([Path("/tmp/repo")])

        self.assertIs(result, expected)
        diff_commands.assert_called_once_with([Path("/tmp/repo")])

    def test_git_backend_builds_stage_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        phases = backend.stage_phases({root: ["src/app.py", "README.md"]})

        self.assertEqual(
            phases,
            [
                BackendCommandPhase(
                    title="Stage repo",
                    cwd=root,
                    command=(
                        "git",
                        "-C",
                        str(root),
                        "add",
                        "--",
                        "src/app.py",
                        "README.md",
                    ),
                )
            ],
        )

    def test_git_backend_builds_commit_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        phases = backend.commit_phases(root, ["src/app.py"], "message")

        self.assertEqual([phase.title for phase in phases], [
            "Stage selected files",
            "Create commit",
        ])
        self.assertEqual(
            phases[0].command,
            ("git", "-C", str(root), "add", "--", "src/app.py"),
        )
        self.assertEqual(
            phases[1].command,
            (
                "git",
                "-C",
                str(root),
                "commit",
                "-m",
                "message",
                "--",
                "src/app.py",
            ),
        )

    def test_git_backend_builds_log_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        phases = backend.log_phases({root: ["src/app.py"]}, 7)

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Log repo")
        self.assertEqual(
            phases[0].command,
            (
                "git",
                "-C",
                str(root),
                "log",
                "--oneline",
                "--decorate",
                "-n7",
                "--",
                "src/app.py",
            ),
        )

    def test_git_backend_builds_update_and_push_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        update = backend.update_phases({root: ["src/app.py"]})
        push = backend.push_phases({root: ["src/app.py"]})

        self.assertEqual(update[0].command, ("git", "-C", str(root), "pull", "--ff-only"))
        self.assertEqual(push[0].command, ("git", "-C", str(root), "push"))

    def test_git_backend_builds_file_diff_command(self):
        backend = GitBackend()
        root = Path("/tmp/repo")
        item = BackendChangeItem(
            backend_id="git",
            root=root,
            path="src/app.py",
            status="modified",
        )

        self.assertEqual(
            backend.file_diff_command(item),
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
