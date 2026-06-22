from pathlib import Path
import unittest
from unittest import mock

from nemovcs import backends
from nemovcs.backends.git import GitBackend


class BackendRegistryTest(unittest.TestCase):
    def test_git_backend_is_registered(self):
        registered = backends.registered_backends()

        self.assertEqual([backend.id for backend in registered], ["git"])
        self.assertIsInstance(registered[0], GitBackend)

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

    def test_group_by_backend_groups_git_roots(self):
        root = Path("/tmp/repo")

        with mock.patch("nemovcs.git.group_by_repo", return_value={root: ["src/app.py"]}):
            grouped = backends.group_by_backend([root / "src/app.py"])

        backend = next(iter(grouped))
        self.assertEqual(backend.id, "git")
        self.assertEqual(grouped[backend], {root: ["src/app.py"]})

    def test_git_backend_delegates_status_to_existing_git_helpers(self):
        backend = GitBackend()
        expected = object()

        with mock.patch("nemovcs.git.status", return_value=expected) as status:
            result = backend.status([Path("/tmp/repo")])

        self.assertIs(result, expected)
        status.assert_called_once_with([Path("/tmp/repo")])


if __name__ == "__main__":
    unittest.main()
