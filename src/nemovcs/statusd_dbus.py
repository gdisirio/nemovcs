"""DBus adapter for the status daemon prototype."""

from __future__ import annotations

from typing import Sequence

from . import statusd
from . import statusd_monitor


INTROSPECTION_XML = f"""<!DOCTYPE node PUBLIC
"-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
"http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="{statusd.DBUS_INTERFACE}">
    <method name="Seen">
      <arg name="paths" type="as" direction="in"/>
      <arg name="worktree_ids" type="as" direction="out"/>
    </method>
    <method name="GetStatus">
      <arg name="paths" type="as" direction="in"/>
      <arg name="records" type="aa{{ss}}" direction="out"/>
    </method>
    <signal name="StatusChanged">
      <arg name="worktree_id" type="s"/>
      <arg name="paths" type="as"/>
    </signal>
  </interface>
</node>
"""


def run_foreground() -> int:
    import dbus
    import dbus.mainloop.glib
    import dbus.service
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    bus_name = dbus.service.BusName(statusd.DBUS_BUS_NAME, bus=bus)
    core = statusd.StatusDaemonCore(timer=glib_timer)
    monitor_manager = statusd_monitor.WorktreeMonitorManager(core)
    core.set_monitor_manager(monitor_manager)
    StatusDaemonDBusService(bus, core)
    print(
        f"nemovcs-statusd prototype running on {statusd.DBUS_BUS_NAME}. "
        "Press Ctrl+C to stop."
    )
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("nemovcs-statusd stopped.")
        loop.quit()
    finally:
        monitor_manager.stop_all()
        bus_name.__del__()
    return 0


def glib_timer(delay_seconds, callback):
    from gi.repository import GLib

    def on_timeout():
        callback()
        return False

    return GLib.timeout_add(int(delay_seconds * 1000), on_timeout)


def call_seen(paths: Sequence[str]) -> list[str]:
    import dbus

    proxy = _statusd_proxy()
    return list(proxy.Seen(list(paths), dbus_interface=statusd.DBUS_INTERFACE))


def call_get_status(paths: Sequence[str]) -> list[dict[str, str]]:
    proxy = _statusd_proxy()
    return [
        {str(key): str(value) for key, value in dict(record).items()}
        for record in proxy.GetStatus(list(paths), dbus_interface=statusd.DBUS_INTERFACE)
    ]


def subscribe_status_changed(callback):
    import dbus

    bus = dbus.SessionBus()
    return bus.add_signal_receiver(
        callback,
        signal_name="StatusChanged",
        dbus_interface=statusd.DBUS_INTERFACE,
        bus_name=statusd.DBUS_BUS_NAME,
        path=statusd.DBUS_OBJECT_PATH,
    )


def _statusd_proxy():
    import dbus

    bus = dbus.SessionBus()
    return bus.get_object(statusd.DBUS_BUS_NAME, statusd.DBUS_OBJECT_PATH)


def make_service_class():
    import dbus
    import dbus.service

    class StatusDaemonDBusService(dbus.service.Object):
        def __init__(
            self,
            bus: dbus.bus.BusConnection,
            core: statusd.StatusDaemonCore,
        ):
            super().__init__(bus, statusd.DBUS_OBJECT_PATH)
            self.core = core
            self.core.status_changed_callback = self.StatusChanged

        @dbus.service.method(
            statusd.DBUS_INTERFACE,
            in_signature="as",
            out_signature="as",
        )
        def Seen(self, paths):
            worktree_ids = self.core.seen([str(path) for path in paths])
            return worktree_ids

        @dbus.service.method(
            statusd.DBUS_INTERFACE,
            in_signature="as",
            out_signature="aa{ss}",
        )
        def GetStatus(self, paths):
            records = self.core.get_status([str(path) for path in paths])
            return [
                dbus.Dictionary(record, signature="ss")
                for record in records
            ]

        @dbus.service.signal(
            statusd.DBUS_INTERFACE,
            signature="sas",
        )
        def StatusChanged(self, worktree_id, paths):
            pass

    return StatusDaemonDBusService


StatusDaemonDBusService = make_service_class()
