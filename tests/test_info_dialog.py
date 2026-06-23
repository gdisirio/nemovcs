import unittest
from unittest import mock

from nemovcs.ui import info_dialog


class InfoDialogTest(unittest.TestCase):
    def test_about_logo_pixbuf_loads_resource_icon(self):
        self.assertIsNotNone(info_dialog.about_logo_pixbuf())

    def test_about_logo_pixbuf_returns_none_on_load_failure(self):
        with mock.patch(
            "gi.repository.GdkPixbuf.Pixbuf.new_from_file_at_size",
            side_effect=RuntimeError("missing"),
        ):
            self.assertIsNone(info_dialog.about_logo_pixbuf())


if __name__ == "__main__":
    unittest.main()
