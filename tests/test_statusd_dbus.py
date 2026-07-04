import unittest
from unittest import mock

from nemovcs import statusd, statusd_dbus


class StatusDaemonDBusMetadataTest(unittest.TestCase):
    def test_introspection_declares_expected_api(self):
        xml = statusd_dbus.INTROSPECTION_XML

        self.assertIn(statusd.DBUS_INTERFACE, xml)
        self.assertIn('name="QueryStatus"', xml)
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


class StatusDaemonDBusClientTest(unittest.TestCase):
    def test_seen_uses_configured_timeout(self):
        proxy = mock.Mock()
        proxy.Seen.return_value = ["git:/tmp/repo"]

        with mock.patch("nemovcs.statusd_dbus._statusd_proxy", return_value=proxy), mock.patch(
            "nemovcs.statusd_dbus.dbus_timeout_seconds",
            return_value=0.25,
        ):
            self.assertEqual(statusd_dbus.call_seen(["/tmp/repo"]), ["git:/tmp/repo"])

        proxy.Seen.assert_called_once_with(
            ["/tmp/repo"],
            dbus_interface=statusd.DBUS_INTERFACE,
            timeout=0.25,
        )

    def test_get_status_uses_configured_timeout(self):
        proxy = mock.Mock()
        proxy.GetStatus.return_value = [{"path": "/tmp/repo", "status": "ok"}]

        with mock.patch("nemovcs.statusd_dbus._statusd_proxy", return_value=proxy), mock.patch(
            "nemovcs.statusd_dbus.dbus_timeout_seconds",
            return_value=0.5,
        ):
            records = statusd_dbus.call_get_status(["/tmp/repo"])

        self.assertEqual(records, [{"path": "/tmp/repo", "status": "ok"}])
        proxy.GetStatus.assert_called_once_with(
            ["/tmp/repo"],
            dbus_interface=statusd.DBUS_INTERFACE,
            timeout=0.5,
        )

    def test_query_status_uses_configured_timeout(self):
        proxy = mock.Mock()
        proxy.QueryStatus.return_value = [{"path": "/tmp/repo", "status": "loading"}]

        with mock.patch("nemovcs.statusd_dbus._statusd_proxy", return_value=proxy), mock.patch(
            "nemovcs.statusd_dbus.dbus_timeout_seconds",
            return_value=0.75,
        ):
            records = statusd_dbus.call_query_status(["/tmp/repo"])

        self.assertEqual(records, [{"path": "/tmp/repo", "status": "loading"}])
        proxy.QueryStatus.assert_called_once_with(
            ["/tmp/repo"],
            dbus_interface=statusd.DBUS_INTERFACE,
            timeout=0.75,
        )


if __name__ == "__main__":
    unittest.main()
