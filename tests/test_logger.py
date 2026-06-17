from pathlib import Path
import unittest

from nemovcs.ui import logger


class LoggerCommandPhaseTest(unittest.TestCase):
    def test_git_phase_builds_explicit_git_command(self):
        root = Path("/tmp/example")

        phase = logger.CommandPhase.git("Update example", root, ["pull", "--ff-only"])

        self.assertEqual(phase.title, "Update example")
        self.assertEqual(phase.cwd, root)
        self.assertEqual(
            phase.command,
            ("git", "-C", str(root), "pull", "--ff-only"),
        )


if __name__ == "__main__":
    unittest.main()
