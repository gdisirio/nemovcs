import unittest

from nemovcs import statusd, statusd_dbus


class StatusDaemonDBusMetadataTest(unittest.TestCase):
    def test_introspection_declares_expected_api(self):
        xml = statusd_dbus.INTROSPECTION_XML

        self.assertIn(statusd.DBUS_INTERFACE, xml)
        self.assertIn('name="Seen"', xml)
        self.assertIn('name="GetStatus"', xml)
        self.assertIn('name="GetCacheEntries"', xml)
        self.assertIn('name="GetSettings"', xml)
        self.assertIn('name="SetSettings"', xml)
        self.assertIn('name="StatusChanged"', xml)
        self.assertIn('type="as"', xml)
        self.assertIn('type="aa{ss}"', xml)
        self.assertIn('name="worktree_id" type="s"', xml)
        self.assertIn('name="paths" type="as"', xml)


class NemoNameLostTest(unittest.TestCase):
    def test_reports_lost_when_nemo_owner_cleared(self):
        self.assertTrue(
            statusd_dbus.nemo_name_lost(statusd.NEMO_BUS_NAME, ":1.42", "")
        )

    def test_not_lost_when_nemo_owner_acquired(self):
        self.assertFalse(
            statusd_dbus.nemo_name_lost(statusd.NEMO_BUS_NAME, "", ":1.42")
        )

    def test_not_lost_without_prior_owner(self):
        self.assertFalse(
            statusd_dbus.nemo_name_lost(statusd.NEMO_BUS_NAME, "", "")
        )

    def test_ignores_other_bus_names(self):
        self.assertFalse(
            statusd_dbus.nemo_name_lost("org.NemoDesktop", ":1.63", "")
        )


class StatusDaemonCoreTest(unittest.TestCase):
    def test_get_status_reports_non_repository_as_error(self):
        core = statusd.StatusDaemonCore()

        records = core.get_status(["/definitely/not/a/nemovcs/worktree"])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["backend"], "")
        self.assertEqual(records[0]["status"], statusd.EmblemStatus.ERROR)
        self.assertEqual(records[0]["error"], "not inside a versioned working tree")


if __name__ == "__main__":
    unittest.main()
