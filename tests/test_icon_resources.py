from pathlib import Path
import unittest


EMBLEM_DIR = Path(__file__).resolve().parents[1] / "rsc" / "icons" / "nemovcs" / "emblems"


class IconResourcesTest(unittest.TestCase):
    def test_live_emblems_are_cropped_for_larger_nemo_overlay(self):
        for status in ("normal", "modified", "conflicted", "problems"):
            with self.subTest(status=status):
                path = EMBLEM_DIR / f"emblem-nemovcs-{status}.svg"

                self.assertIn('viewBox="0 95 162 162"', path.read_text(encoding="utf-8"))

    def test_small_emblem_variants_keep_original_canvas(self):
        for status in (
            "normal",
            "modified",
            "conflicted",
            "added",
            "deleted",
            "problems",
            "unversioned",
        ):
            with self.subTest(status=status):
                path = EMBLEM_DIR / f"emblem-nemovcs-{status}-small.svg"
                text = path.read_text(encoding="utf-8")

                self.assertTrue(path.exists())
                self.assertNotIn('viewBox="0 95 162 162"', text)


if __name__ == "__main__":
    unittest.main()
