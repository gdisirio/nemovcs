from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from nemovcs import backends
from nemovcs import git
from nemovcs.backends.base import (
    BackendChangeItem,
    BackendCommandPhase,
    BackendLog,
    BackendStatusItem,
    BackendWorktreeIdentity,
    LogChange,
    LogEntry,
)
from nemovcs.backends.git import (
    GitBackend,
    LOG_FIELD_SEP,
    LOG_HEADER_END,
    LOG_RECORD_SEP,
    parse_git_log,
    parse_git_name_status,
)
from nemovcs.backends.svn import (
    SvnBackend,
    SvnResult,
    has_svn_metadata_ancestor,
    parse_svn_log,
)


class BackendRegistryTest(unittest.TestCase):
    def test_git_and_svn_backends_are_registered(self):
        registered = backends.registered_backends()

        self.assertEqual([backend.id for backend in registered], ["git", "svn"])
        self.assertIsInstance(registered[0], GitBackend)
        self.assertIsInstance(registered[1], SvnBackend)

    def test_backend_by_id_returns_registered_backend(self):
        backend = backends.backend_by_id("git")

        self.assertIsNotNone(backend)
        assert backend is not None
        self.assertEqual(backend.id, "git")

    def test_backend_by_id_returns_none_for_unknown_backend(self):
        self.assertIsNone(backends.backend_by_id("hg"))

    def test_file_diff_command_returns_empty_for_unknown_backend(self):
        item = BackendChangeItem(
            backend_id="hg",
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

    def test_commit_collects_results_from_matching_backend(self):
        root = Path("/tmp/repo")
        expected = object()

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["."]}), mock.patch(
            "nemovcs.backends.git.GitBackend.commit",
            return_value=[expected],
        ) as commit:
            self.assertEqual(backends.commit([root], "message"), [expected])

        commit.assert_called_once_with([root], "message")

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

    def test_rename_phases_uses_detected_backend(self):
        root = Path("/tmp/repo")
        phase = BackendCommandPhase(
            title="Rename app.py",
            cwd=root,
            command=("fake", "rename"),
        )

        with mock.patch("nemovcs.git.is_inside_worktree", return_value=True), mock.patch(
            "nemovcs.backends.git.GitBackend.rename_phases",
            return_value=[phase],
        ) as rename_phases:
            self.assertEqual(
                backends.rename_phases(root, "src/app.py", "src/main.py"),
                [phase],
            )

        rename_phases.assert_called_once_with(root, "src/app.py", "src/main.py")

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

    def test_git_backend_commit_stages_then_commits(self):
        backend = GitBackend()
        root = Path("/tmp/repo")
        add_result = git.GitResult(("git",), root, 0, "", "")
        commit_result = git.GitResult(("git",), root, 0, "", "")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}), (
            mock.patch("nemovcs.git.run_git", side_effect=[add_result, commit_result])
        ) as run_git:
            result = backend.commit([root / "src/app.py"], "message")

        self.assertEqual(result, [add_result, commit_result])
        self.assertEqual(
            run_git.mock_calls,
            [
                mock.call(root, ["add", "--", "src/app.py"]),
                mock.call(root, ["commit", "-m", "message"], timeout=3600),
            ],
        )

    def test_git_backend_commit_stops_repository_after_failed_stage(self):
        backend = GitBackend()
        root = Path("/tmp/repo")
        add_result = git.GitResult(("git",), root, 1, "", "failed")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}), (
            mock.patch("nemovcs.git.run_git", return_value=add_result)
        ) as run_git:
            result = backend.commit([root / "src/app.py"], "message")

        self.assertEqual(result, [add_result])
        run_git.assert_called_once_with(root, ["add", "--", "src/app.py"])

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

    def test_git_backend_builds_revert_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        phases = backend.revert_phases({root: ["src/app.py", "README.md"]})

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
                "README.md",
            ),
        )

    def test_git_backend_builds_rename_phases(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        phases = backend.rename_phases(root, "src/app.py", "src/main.py")

        self.assertEqual(len(phases), 1)
        self.assertEqual(phases[0].title, "Rename app.py")
        self.assertEqual(
            phases[0].command,
            (
                "git",
                "-C",
                str(root),
                "mv",
                "--",
                "src/app.py",
                "src/main.py",
            ),
        )

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
        ) as parse_status, mock.patch(
            "nemovcs.git.remote_url", return_value="git@example.com:me/repo.git"
        ):
            run_git.side_effect = [
                git.GitResult(("git",), root, 0, "raw", ""),
                git.GitResult(("git",), root, 0, "tracked.txt\0renamed.txt\0", ""),
            ]
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
                git.CommitItem(
                    root=root,
                    path="new.txt",
                    status="untracked",
                    index_status="?",
                    worktree_status="?",
                    tracked=False,
                ),
            ]

            result = backend.scan_status(root)

        self.assertEqual(
            run_git.call_args_list,
            [
                mock.call(
                    root,
                    ["status", "--porcelain=v2", "-z", "-uall"],
                    env=GitBackend.scan_env,
                ),
                mock.call(root, ["ls-files", "-z"], env=GitBackend.scan_env),
            ],
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.tracked_paths, ("tracked.txt", "renamed.txt"))
        self.assertEqual(result.remote_url, "git@example.com:me/repo.git")
        self.assertEqual(
            result.items,
            (
                BackendStatusItem(path="tracked.txt"),
                BackendStatusItem(path="renamed.txt", old_path="old.txt"),
                BackendStatusItem(path="conflicted.txt", conflicted=True),
                BackendStatusItem(path="new.txt", status="unversioned"),
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

    def test_parse_git_name_status_handles_renames_and_plain_changes(self):
        block = "\n".join(
            [
                "M\tsrc/a.py",
                "A\tsrc/b.py",
                "D\told.py",
                "R100\tone.py\ttwo.py",
                "C075\tbase.py\tcopy.py",
                "T\tsrc/link",
            ]
        )

        self.assertEqual(
            parse_git_name_status(block),
            (
                LogChange(action="modified", path="src/a.py"),
                LogChange(action="added", path="src/b.py"),
                LogChange(action="deleted", path="old.py"),
                LogChange(action="renamed", path="two.py", old_path="one.py"),
                LogChange(action="copied", path="copy.py", old_path="base.py"),
                LogChange(action="modified", path="src/link"),
            ),
        )

    def test_parse_git_log_parses_commits_and_changes(self):
        def commit(fields, name_status_lines):
            header = LOG_RECORD_SEP + LOG_FIELD_SEP.join(fields) + LOG_HEADER_END
            block = "\n" + "".join(f"{line}\n" for line in name_status_lines)
            return header + block

        text = "".join(
            [
                commit(
                    [
                        "abc123",
                        "Alice",
                        "2024-01-02T03:04:05+00:00",
                        "Add feature",
                        "Detailed\nmulti-line body",
                    ],
                    ["M\tsrc/a.py", "R100\told.py\tnew.py"],
                ),
                commit(
                    ["def456", "Bob", "2024-01-01T00:00:00+00:00", "Initial", ""],
                    ["A\tREADME.md"],
                ),
                # A merge with no file changes: empty name-status block.
                commit(
                    ["9990000", "Carol", "2024-01-03T00:00:00+00:00", "Merge", ""],
                    [],
                ),
            ]
        )

        entries = parse_git_log(text)

        self.assertEqual(
            entries,
            [
                LogEntry(
                    revision="abc123",
                    author="Alice",
                    date="2024-01-02T03:04:05+00:00",
                    summary="Add feature",
                    body="Detailed\nmulti-line body",
                    changes=(
                        LogChange(action="modified", path="src/a.py"),
                        LogChange(action="renamed", path="new.py", old_path="old.py"),
                    ),
                ),
                LogEntry(
                    revision="def456",
                    author="Bob",
                    date="2024-01-01T00:00:00+00:00",
                    summary="Initial",
                    body="",
                    changes=(LogChange(action="added", path="README.md"),),
                ),
                LogEntry(
                    revision="9990000",
                    author="Carol",
                    date="2024-01-03T00:00:00+00:00",
                    summary="Merge",
                    body="",
                    changes=(),
                ),
            ],
        )

    def test_git_backend_scan_log_returns_entries(self):
        backend = GitBackend()
        root = Path("/tmp/repo")
        text = (
            LOG_RECORD_SEP
            + LOG_FIELD_SEP.join(
                ["abc123", "Alice", "2024-01-02T03:04:05+00:00", "Only", ""]
            )
            + LOG_HEADER_END
            + "\nA\tfile.txt\n"
        )

        with mock.patch("nemovcs.git.run_git") as run_git:
            run_git.return_value = git.GitResult(("git",), root, 0, text, "")

            result = backend.scan_log(root, limit=5)

        self.assertTrue(result.ok)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].revision, "abc123")
        self.assertEqual(
            result.entries[0].changes,
            (LogChange(action="added", path="file.txt"),),
        )

    def test_git_backend_scan_log_reports_command_error(self):
        backend = GitBackend()
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.run_git") as run_git:
            run_git.return_value = git.GitResult(("git",), root, 128, "", "fatal\n")

            result = backend.scan_log(root, limit=5)

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "fatal")
        self.assertEqual(result.entries, ())

    def test_parse_svn_log_parses_revisions_paths_and_copyfrom(self):
        xml = """<?xml version="1.0"?>
<log>
<logentry revision="42">
<author>alice</author>
<date>2024-01-02T03:04:05.000000Z</date>
<paths>
<path action="M" kind="file">/trunk/a.py</path>
<path action="A" kind="file" copyfrom-path="/trunk/old.py" copyfrom-rev="40">/trunk/new.py</path>
<path action="D" kind="file">/trunk/gone.py</path>
</paths>
<msg>Summary line
body paragraph</msg>
</logentry>
<logentry revision="41">
<author>bob</author>
<date>2024-01-01T00:00:00.000000Z</date>
<paths>
<path action="A" kind="dir">/trunk</path>
</paths>
<msg>Initial import</msg>
</logentry>
</log>
"""

        self.assertEqual(
            parse_svn_log(xml),
            [
                LogEntry(
                    revision="42",
                    author="alice",
                    date="2024-01-02T03:04:05.000000Z",
                    summary="Summary line",
                    body="body paragraph",
                    changes=(
                        LogChange(action="modified", path="/trunk/a.py"),
                        LogChange(
                            action="added",
                            path="/trunk/new.py",
                            old_path="/trunk/old.py",
                        ),
                        LogChange(action="deleted", path="/trunk/gone.py"),
                    ),
                ),
                LogEntry(
                    revision="41",
                    author="bob",
                    date="2024-01-01T00:00:00.000000Z",
                    summary="Initial import",
                    body="",
                    changes=(LogChange(action="added", path="/trunk"),),
                ),
            ],
        )

    def test_parse_svn_log_returns_empty_on_malformed_xml(self):
        self.assertEqual(parse_svn_log("not xml <"), [])

    def test_svn_backend_scan_log_returns_entries(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")
        xml = (
            '<?xml version="1.0"?>\n<log>\n'
            '<logentry revision="7">\n<author>al</author>\n'
            "<date>2024-05-05T00:00:00.0Z</date>\n"
            '<paths>\n<path action="M">/trunk/x</path>\n</paths>\n'
            "<msg>tweak</msg>\n</logentry>\n</log>\n"
        )

        with mock.patch.object(
            backend,
            "run",
            return_value=SvnResult(("svn", "log"), root, 0, xml, ""),
        ):
            result = backend.scan_log(root, limit=5)

        self.assertTrue(result.ok)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].revision, "7")
        self.assertEqual(result.entries[0].summary, "tweak")

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

    def test_svn_backend_parses_xml_status(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")
        xml = """<?xml version="1.0"?>
<status>
  <target path=".">
    <entry path="modified.txt"><wc-status item="modified"/></entry>
    <entry path="new.txt"><wc-status item="unversioned"/></entry>
    <entry path="conflict.txt"><wc-status item="conflicted"/></entry>
  </target>
</status>
"""

        result = backend.parse_status(root, xml)

        self.assertEqual(
            result,
            [
                BackendChangeItem(
                    backend_id="svn",
                    root=root,
                    path="modified.txt",
                    status="modified",
                ),
                BackendChangeItem(
                    backend_id="svn",
                    root=root,
                    path="new.txt",
                    status="untracked",
                    tracked=False,
                ),
                BackendChangeItem(
                    backend_id="svn",
                    root=root,
                    path="conflict.txt",
                    status="conflicted",
                    conflicted=True,
                ),
            ],
        )

    def test_svn_backend_scan_status_includes_unversioned_items(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")
        xml = """<?xml version="1.0"?>
<status>
  <target path=".">
    <entry path="modified.txt"><wc-status item="modified"/></entry>
    <entry path="generated.txt"><wc-status item="unversioned"/></entry>
    <entry path="conflict.txt"><wc-status item="conflicted"/></entry>
  </target>
</status>
"""

        def run(_cwd, args, **_kwargs):
            if args == ["status", "--xml"]:
                return SvnResult(("svn", "status", "--xml"), root, 0, xml, "")
            if args == ["info", "--show-item", "url"]:
                return SvnResult(
                    ("svn", "info", "--show-item", "url"),
                    root,
                    0,
                    "https://svn.example.com/project/trunk\n",
                    "",
                )
            raise AssertionError(args)

        with mock.patch.object(backend, "run", side_effect=run):
            result = backend.scan_status(root)

        self.assertTrue(result.ok)
        self.assertEqual(
            result.items,
            (
                BackendStatusItem(path="modified.txt"),
                BackendStatusItem(path="generated.txt", status="unversioned"),
                BackendStatusItem(path="conflict.txt", conflicted=True),
            ),
        )
        self.assertEqual(result.remote_url, "https://svn.example.com/project/trunk")

    def test_svn_backend_reports_missing_executable_as_failed_result(self):
        backend = SvnBackend()

        with mock.patch("nemovcs.backends.svn.subprocess.run", side_effect=FileNotFoundError):
            result = backend.run("/tmp", ["info"])

        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "svn executable not found\n")

    def test_svn_backend_reports_timeout_as_failed_result(self):
        backend = SvnBackend()

        with mock.patch(
            "nemovcs.backends.svn.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["svn", "status"], 15),
        ):
            result = backend.run("/tmp", ["status"])

        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "svn command timed out\n")

    def test_svn_root_skips_subprocess_without_svn_metadata(self):
        backend = SvnBackend()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(backend, "run") as run:
                self.assertIsNone(backend.root(tmp))
                self.assertFalse(backend.is_worktree(tmp))
            run.assert_not_called()

    def test_svn_root_probes_when_svn_metadata_present(self):
        backend = SvnBackend()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / ".svn").mkdir()
            with mock.patch.object(
                backend,
                "run",
                return_value=SvnResult(
                    ("svn", "info"), root, 0, f"{root}\n", ""
                ),
            ) as run:
                self.assertEqual(backend.root(tmp), root)
            run.assert_called_once()

    def test_has_svn_metadata_ancestor_walks_up_to_working_copy_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(strict=False)
            (root / ".svn").mkdir()
            nested = root / "src" / "pkg"
            nested.mkdir(parents=True)
            leaf = nested / "module.py"
            leaf.write_text("", encoding="utf-8")

            self.assertTrue(has_svn_metadata_ancestor(nested))
            self.assertTrue(has_svn_metadata_ancestor(leaf))

    def test_has_svn_metadata_ancestor_false_without_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b"
            nested.mkdir(parents=True)
            self.assertFalse(has_svn_metadata_ancestor(nested))

    def test_svn_backend_builds_meld_diff_commands(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")

        with mock.patch.object(backend, "group", return_value={root: ["src/app.py"]}), (
            mock.patch("nemovcs.backends.svn.shutil.which", return_value="/usr/bin/meld")
        ):
            result = backend.diff_commands([root / "src/app.py"])

        self.assertEqual(
            result,
            [
                SvnResult(
                    ("nemovcs", "svn-meld-diff", "/tmp/wc/src/app.py"),
                    root,
                    0,
                    "",
                    "",
                )
            ],
        )

    def test_svn_backend_file_diff_command_uses_meld_helper(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")
        item = BackendChangeItem(
            backend_id="svn",
            root=root,
            path="src/app.py",
            status="modified",
        )

        self.assertEqual(
            backend.file_diff_command(item),
            ["nemovcs", "svn-meld-diff", "/tmp/wc/src/app.py"],
        )

    def test_svn_backend_builds_add_commit_and_update_phases(self):
        backend = SvnBackend()
        root = Path("/tmp/wc")

        add = backend.stage_phases({root: ["new.txt"]})
        commit = backend.commit_phases(root, ["new.txt"], "message")
        update = backend.update_phases({root: ["."]})
        revert = backend.revert_phases({root: ["modified.txt"]})
        rename = backend.rename_phases(root, "old.txt", "new.txt")

        self.assertEqual(add[0].command, ("svn", "add", "--parents", "new.txt"))
        self.assertEqual(commit[0].command, ("svn", "commit", "-m", "message", "new.txt"))
        self.assertEqual(update[0].command, ("svn", "update"))
        self.assertEqual(revert[0].command, ("svn", "revert", "modified.txt"))
        self.assertEqual(rename[0].command, ("svn", "move", "old.txt", "new.txt"))


if __name__ == "__main__":
    unittest.main()
