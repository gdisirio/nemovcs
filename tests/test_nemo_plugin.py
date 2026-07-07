import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from nemovcs import nemo_plugin


class FakeLocation:
    def __init__(self, path):
        self.path = path

    def get_path(self):
        return self.path


class FakeItem:
    def __init__(self, path, uri_scheme="file"):
        self.path = path
        self.uri_scheme = uri_scheme
        self.emblems = []
        self.invalidated = 0

    def get_uri_scheme(self):
        return self.uri_scheme

    def get_location(self):
        return FakeLocation(self.path)

    def add_emblem(self, emblem):
        self.emblems.append(emblem)

    def invalidate_extension_info(self):
        self.invalidated += 1


class FakeToggle:
    def __init__(self, active):
        self.active = active
        self.tooltip = ""
        self.image = None

    def get_active(self):
        return self.active

    def set_tooltip_text(self, text):
        self.tooltip = text

    def set_image(self, image):
        self.image = image


class FakeWidget:
    def __init__(self):
        self.visible = True
        self.text = ""
        self.max_width_chars = None
        self.parent = None
        self.resized = False
        self.connections = []
        self.xalign = None
        self.hexpand = False
        self.ellipsize = None
        self.selectable = False
        self.tooltip = ""

    def show_all(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True

    def set_text(self, text):
        self.text = text

    def set_max_width_chars(self, chars):
        self.max_width_chars = chars

    def set_xalign(self, xalign):
        self.xalign = xalign

    def set_hexpand(self, hexpand):
        self.hexpand = hexpand

    def set_ellipsize(self, ellipsize):
        self.ellipsize = ellipsize

    def set_selectable(self, selectable):
        self.selectable = selectable

    def set_tooltip_text(self, text):
        self.tooltip = text

    def get_parent(self):
        return self.parent

    def queue_resize(self):
        self.resized = True

    def connect(self, signal, callback, *args):
        self.connections.append((signal, callback, args))


class FakeCore:
    def __init__(self):
        self.changed_calls = []

    def on_status_changed(self, worktree_id, changed_paths):
        self.changed_calls.append((worktree_id, list(changed_paths)))
        return ["invalidated"]


class NemoVCSInfoProviderCoreTest(unittest.TestCase):
    def test_file_item_path_resolves_absolute_path(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/repo/tracked.txt")

        self.assertEqual(core.item_path(item), "/tmp/repo/tracked.txt")

    def test_non_file_item_is_ignored(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/repo/tracked.txt", uri_scheme="trash")

        self.assertIsNone(core.update_item(item))

    def test_update_item_refreshes_status_and_adds_modified_emblem(self):
        seen_calls = []
        get_status_calls = []

        def seen(paths):
            seen_calls.append(list(paths))
            return ["/tmp/repo"]

        def get_status(paths):
            get_status_calls.append(list(paths))
            return [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "modified",
                }
            ]

        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=seen,
            get_status=get_status,
        )
        item = FakeItem("/tmp/repo/tracked.txt")

        record = core.update_item(item)

        self.assertEqual(record["status"], "modified")
        self.assertEqual(seen_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(get_status_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(item.emblems, ["nemovcs-modified"])
        self.assertEqual(
            core.cache.get(Path("/tmp/repo/tracked.txt"))["status"],
            "modified",
        )
        self.assertIn("/tmp/repo/tracked.txt", core.visible_items)

    def test_status_changed_refreshes_item_after_becoming_versioned(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/newrepo")
        core.track_visible_item("/tmp/newrepo", item)
        # Stale record from when the directory was non-versioned.
        core.cache.update(
            [{"path": "/tmp/newrepo", "worktree_id": "", "status": "error"}]
        )

        invalidated = core.on_status_changed("git:/tmp/newrepo", ["/tmp/newrepo"])

        self.assertEqual(len(invalidated), 1)
        self.assertEqual(item.invalidated, 1)
        self.assertIsNone(core.cache.get("/tmp/newrepo"))

    def test_update_item_uses_single_query_status_call(self):
        query_calls = []

        def query_status(paths):
            query_calls.append(list(paths))
            return [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "git:/tmp/repo",
                    "status": "modified",
                }
            ]

        core = nemo_plugin.NemoVCSInfoProviderCore(query_status=query_status)
        item = FakeItem("/tmp/repo/tracked.txt")

        record = core.update_item(item)

        self.assertEqual(record["status"], "modified")
        self.assertEqual(query_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(item.emblems, ["nemovcs-modified"])

    def test_update_item_reuses_client_cache(self):
        seen_calls = []
        get_status_calls = []

        def seen(paths):
            seen_calls.append(list(paths))
            return ["git:/tmp/repo"]

        def get_status(paths):
            get_status_calls.append(list(paths))
            return [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "git:/tmp/repo",
                    "status": "modified",
                }
            ]

        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=seen,
            get_status=get_status,
        )

        first = core.update_item(FakeItem("/tmp/repo/tracked.txt"))
        second = core.update_item(FakeItem("/tmp/repo/tracked.txt"))

        self.assertEqual(first["status"], "modified")
        self.assertEqual(second["status"], "modified")
        self.assertEqual(seen_calls, [["/tmp/repo/tracked.txt"]])
        self.assertEqual(get_status_calls, [["/tmp/repo/tracked.txt"]])

    def test_location_widget_spec_can_bypass_cached_loading_record(self):
        records = [
            {
                "path": "/tmp/repo",
                "backend": "git",
                "worktree_id": "git:/tmp/repo",
                "root": "/tmp/repo",
                "head": "main",
                "status": "loading",
            },
            {
                "path": "/tmp/repo",
                "backend": "git",
                "worktree_id": "git:/tmp/repo",
                "root": "/tmp/repo",
                "head": "main",
                "remote": "git@example.com:me/repo.git",
                "status": "ok",
            },
        ]
        calls = []

        def query_status(paths):
            calls.append(list(paths))
            return [records[min(len(calls) - 1, 1)]]

        core = nemo_plugin.NemoVCSInfoProviderCore(query_status=query_status)

        first = core.location_widget_spec("/tmp/repo")
        second = core.location_widget_spec("/tmp/repo")
        refreshed = core.location_widget_spec("/tmp/repo", use_cache=False)

        assert first is not None
        assert second is not None
        assert refreshed is not None
        self.assertEqual(first.status, "loading")
        self.assertEqual(second.status, "loading")
        self.assertEqual(refreshed.status, "ok")
        self.assertEqual(refreshed.remote, "git@example.com:me/repo.git")
        self.assertEqual(calls, [["/tmp/repo"], ["/tmp/repo"]])

    def test_conflicted_status_adds_conflict_emblem(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/conflict.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "conflicted",
                }
            ],
        )
        item = FakeItem("/tmp/repo/conflict.txt")

        core.update_item(item)

        self.assertEqual(item.emblems, ["nemovcs-conflicted"])

    def test_ok_status_adds_normal_emblem(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "ok",
                }
            ],
        )
        item = FakeItem("/tmp/repo/tracked.txt")

        core.update_item(item)

        self.assertEqual(item.emblems, ["nemovcs-normal"])

    def test_primary_emblem_maps_only_visible_statuses(self):
        self.assertEqual(nemo_plugin.primary_emblem("modified"), "nemovcs-modified")
        self.assertEqual(
            nemo_plugin.primary_emblem("conflicted"),
            "nemovcs-conflicted",
        )
        self.assertEqual(
            nemo_plugin.primary_emblem("unversioned"),
            "nemovcs-unversioned",
        )
        self.assertEqual(nemo_plugin.primary_emblem("ok"), "nemovcs-normal")
        self.assertEqual(nemo_plugin.primary_emblem("error"), "nemovcs-problems")
        self.assertIsNone(nemo_plugin.primary_emblem("ignored"))
        self.assertIsNone(nemo_plugin.primary_emblem("loading"))
        self.assertIsNone(nemo_plugin.primary_emblem("stale"))

    def test_path_from_uri_accepts_file_uri(self):
        self.assertEqual(
            nemo_plugin.path_from_uri("file:///tmp/repo/src%20dir"),
            "/tmp/repo/src dir",
        )

    def test_path_from_uri_rejects_non_file_uri(self):
        self.assertIsNone(nemo_plugin.path_from_uri("network:///server/share"))

    def test_compact_text_shortens_long_values(self):
        self.assertEqual(
            nemo_plugin.compact_text("feature/very-long-branch", max_chars=12),
            "feature/ver...",
        )
        self.assertEqual(nemo_plugin.compact_text("main", max_chars=12), "main")

    def test_location_widget_spec_uses_status_record(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["git:/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/src",
                    "backend": "git",
                    "worktree_id": "git:/tmp/repo",
                    "root": "/tmp/repo",
                    "head": "feature/test",
                    "status": "modified",
                }
            ],
        )

        spec = core.location_widget_spec("/tmp/repo/src")

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.backend_label, "Git")
        self.assertEqual(spec.head, "feature/test")
        self.assertEqual(spec.status_label, "modified")
        self.assertEqual(spec.root_label, "repo")
        self.assertEqual(spec.icon, "nemovcs-git")

    def test_location_widget_details_match_tooltip_content(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="modified",
            status_label="modified",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
        )

        self.assertEqual(
            nemo_plugin.location_widget_details(spec),
            [
                ("Worktree", "/tmp/repo"),
                ("Status", "modified"),
                ("Branch", "main"),
            ],
        )
        self.assertEqual(
            nemo_plugin.location_widget_tooltip(spec),
            "Worktree: /tmp/repo\nStatus: modified\nBranch: main",
        )

    def test_location_widget_summary_label_uses_git_source_and_head(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="modified",
            status_label="modified",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
        )

        self.assertEqual(
            nemo_plugin.location_widget_summary_label(spec),
            "/tmp/repo (main)",
        )

    def test_location_widget_prefers_remote_url_when_present(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="modified",
            status_label="modified",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
            remote="git@example.com:me/repo.git",
        )

        self.assertEqual(
            nemo_plugin.location_widget_details(spec),
            [
                ("Worktree", "/tmp/repo"),
                ("Status", "modified"),
                ("Branch", "main"),
            ],
        )
        self.assertEqual(
            nemo_plugin.location_widget_summary_label(spec),
            "git@example.com:me/repo.git (main)",
        )

    def test_location_widget_loading_without_remote_does_not_show_worktree_as_source(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="loading",
            status_label="loading",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
        )

        self.assertEqual(
            nemo_plugin.location_widget_summary_label(spec),
            "loading source... (main)",
        )

    def test_location_widget_summary_label_omits_svn_head(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="svn",
            backend_label="SVN",
            head="https://svn.example.com/project/trunk @ r42",
            status="ok",
            status_label="clean",
            root="/tmp/wc",
            root_label="wc",
            icon="nemovcs-svn",
            remote="https://svn.example.com/project/trunk",
        )

        self.assertEqual(
            nemo_plugin.location_widget_summary_label(spec),
            "https://svn.example.com/project/trunk",
        )

    def test_location_widget_details_include_forge_line(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="modified",
            status_label="modified",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
            forge_name="GitHub",
            forge_login="gdisirio",
        )

        self.assertIn(
            ("Forge", "GitHub (gdisirio)"),
            nemo_plugin.location_widget_details(spec),
        )

    def test_location_widget_details_omit_forge_when_absent(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="modified",
            status_label="modified",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
        )

        labels = [label for label, _ in nemo_plugin.location_widget_details(spec)]
        self.assertNotIn("Forge", labels)

    def test_forge_detail_value_omits_login_parens_when_empty(self):
        self.assertEqual(nemo_plugin.forge_detail_value("GitHub", "gdisirio"), "GitHub (gdisirio)")
        self.assertEqual(nemo_plugin.forge_detail_value("GitHub", ""), "GitHub")

    def test_forge_summary_for_remote_detects_forge_and_login(self):
        from nemovcs.forge.base import ForgeAccount

        forge = mock.Mock()
        forge.label = "GitHub"
        forge.accounts.return_value = [
            ForgeAccount("chibios-sheriff", active=False),
            ForgeAccount("gdisirio", active=True),
        ]
        with mock.patch(
            "nemovcs.forge.detect_forge", return_value=forge
        ):
            self.assertEqual(
                nemo_plugin.forge_summary_for_remote("git@github.com:me/repo.git"),
                ("GitHub", "gdisirio"),
            )

    def test_forge_summary_for_remote_empty_when_no_forge(self):
        self.assertEqual(nemo_plugin.forge_summary_for_remote(""), ("", ""))
        with mock.patch("nemovcs.forge.detect_forge", return_value=None):
            self.assertEqual(
                nemo_plugin.forge_summary_for_remote("git@example.com:me/repo.git"),
                ("", ""),
            )

    def test_location_widget_details_include_problem_text(self):
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="unknown",
            status="error",
            status_label="problem",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
            error="daemon timeout",
        )

        self.assertIn(("Problem", "daemon timeout"), nemo_plugin.location_widget_details(spec))
        self.assertIn("Problem: daemon timeout", nemo_plugin.location_widget_tooltip(spec))

    def test_location_detail_value_label_is_ellipsized(self):
        label = FakeWidget()

        nemo_plugin.configure_location_detail_value_label(
            label,
            "git@example.com:very/long/repository/path.git",
            "end",
        )

        self.assertEqual(label.xalign, 0)
        self.assertTrue(label.hexpand)
        self.assertEqual(label.ellipsize, "end")
        self.assertEqual(label.max_width_chars, 80)
        self.assertTrue(label.selectable)
        self.assertEqual(label.tooltip, "git@example.com:very/long/repository/path.git")

    def test_location_details_toggle_state_is_remembered_on_provider(self):
        provider = object.__new__(nemo_plugin.NemoVCSInfoProviderMixin)
        provider.nemovcs_location_details_expanded = False
        parent = FakeWidget()
        details = FakeWidget()
        details.parent = parent

        nemo_plugin.set_location_details_expanded(
            provider,
            True,
            FakeToggle(True),
            details,
            lambda icon: icon,
        )

        self.assertTrue(provider.nemovcs_location_details_expanded)
        self.assertTrue(details.visible)
        self.assertTrue(parent.resized)

        nemo_plugin.set_location_details_expanded(
            provider,
            False,
            FakeToggle(False),
            details,
            lambda icon: icon,
        )

        self.assertFalse(provider.nemovcs_location_details_expanded)
        self.assertFalse(details.visible)

    def test_location_widget_handle_matches_worktree_and_changed_path(self):
        handle = nemo_plugin.LocationWidgetHandle(
            path="/tmp/repo/src",
            worktree_id="git:/tmp/repo",
            outer=object(),
            source=object(),
            details=object(),
        )

        self.assertTrue(
            nemo_plugin.location_widget_handle_affected(
                handle,
                "git:/tmp/repo",
                ["/tmp/repo"],
            )
        )
        self.assertTrue(
            nemo_plugin.location_widget_handle_affected(
                handle,
                "git:/tmp/repo",
                ["/tmp/repo/src/file.txt"],
            )
        )
        self.assertFalse(
            nemo_plugin.location_widget_handle_affected(
                handle,
                "svn:/tmp/repo",
                ["/tmp/repo"],
            )
        )
        self.assertFalse(
            nemo_plugin.location_widget_handle_affected(
                handle,
                "git:/tmp/repo",
                ["/tmp/other"],
            )
        )

    def test_tracking_loading_location_widget_schedules_retry(self):
        provider = object.__new__(nemo_plugin.NemoVCSInfoProviderMixin)
        provider.nemovcs_location_widgets = []
        scheduled = []
        provider.schedule_location_widget_retry = lambda handle: scheduled.append(handle)
        outer = FakeWidget()
        source = FakeWidget()
        details = FakeWidget()
        spec = nemo_plugin.LocationWidgetSpec(
            backend="git",
            backend_label="Git",
            head="main",
            status="loading",
            status_label="loading",
            root="/tmp/repo",
            root_label="repo",
            icon="nemovcs-git",
            worktree_id="git:/tmp/repo",
        )

        handle = nemo_plugin.NemoVCSInfoProviderMixin.track_location_widget(
            provider,
            "/tmp/repo",
            spec,
            outer,
            source,
            details,
        )

        self.assertEqual(scheduled, [handle])
        self.assertEqual(provider.nemovcs_location_widgets, [handle])
        self.assertEqual(outer.connections[0][0], "destroy")

    def test_status_changed_wrapper_invalidates_and_schedules_location_refresh(self):
        provider = object.__new__(nemo_plugin.NemoVCSInfoProviderMixin)
        provider.nemovcs_core = FakeCore()
        scheduled = []

        def schedule(worktree_id, changed_paths):
            scheduled.append((worktree_id, list(changed_paths)))

        provider.schedule_location_widget_refresh = schedule

        invalidated = nemo_plugin.NemoVCSInfoProviderMixin.on_daemon_status_changed(
            provider,
            "git:/tmp/repo",
            ["/tmp/repo"],
        )

        self.assertEqual(invalidated, ["invalidated"])
        self.assertEqual(provider.nemovcs_core.changed_calls, [("git:/tmp/repo", ["/tmp/repo"])])
        self.assertEqual(scheduled, [("git:/tmp/repo", ["/tmp/repo"])])

    def test_location_widget_spec_reads_remote_from_record(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["git:/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/src",
                    "backend": "git",
                    "worktree_id": "git:/tmp/repo",
                    "root": "/tmp/repo",
                    "head": "main",
                    "remote": "git@example.com:me/repo.git",
                    "status": "modified",
                }
            ],
        )

        spec = core.location_widget_spec("/tmp/repo/src")

        assert spec is not None
        self.assertEqual(spec.remote, "git@example.com:me/repo.git")

    def test_location_widget_spec_hides_non_worktree_path(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: [],
            get_status=lambda paths: [
                {
                    "path": "/tmp/outside",
                    "backend": "",
                    "worktree_id": "",
                    "root": "",
                    "head": "",
                    "status": "error",
                }
            ],
        )

        self.assertIsNone(core.location_widget_spec("/tmp/outside"))

    def test_daemon_error_is_recorded_and_does_not_escape(self):
        def seen(_paths):
            raise RuntimeError("no daemon")

        core = nemo_plugin.NemoVCSInfoProviderCore(seen=seen, get_status=lambda _: [])

        self.assertIsNone(core.update_path("/tmp/repo/tracked.txt"))
        self.assertEqual(core.last_error, "no daemon")

    def test_daemon_error_on_local_worktree_returns_problem_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            path = root / "tracked.txt"
            path.write_text("content\n", encoding="utf-8")

            def seen(_paths):
                raise RuntimeError("no daemon")

            core = nemo_plugin.NemoVCSInfoProviderCore(seen=seen, get_status=lambda _: [])
            item = FakeItem(path)

            record = core.update_item(item)

            assert record is not None
            self.assertEqual(record["status"], "error")
            self.assertEqual(record["backend"], "git")
            self.assertEqual(record["root"], str(root))
            self.assertEqual(item.emblems, ["nemovcs-problems"])

    def test_non_worktree_daemon_error_does_not_show_problem_emblem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plain.txt"
            path.write_text("content\n", encoding="utf-8")

            def seen(_paths):
                raise RuntimeError("no daemon")

            core = nemo_plugin.NemoVCSInfoProviderCore(seen=seen, get_status=lambda _: [])
            item = FakeItem(path)

            self.assertIsNone(core.update_item(item))
            self.assertEqual(item.emblems, [])

    def test_malformed_status_response_on_local_worktree_returns_problem_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / ".svn").mkdir()
            (root / ".svn" / "wc.db").write_text("", encoding="utf-8")
            path = root / "tracked.txt"
            path.write_text("content\n", encoding="utf-8")

            core = nemo_plugin.NemoVCSInfoProviderCore(
                seen=lambda paths: [f"svn:{root}"],
                get_status=lambda paths: [{"path": str(path), "status": "surprise"}],
            )

            record = core.update_path(path)

            assert record is not None
            self.assertEqual(record["status"], "error")
            self.assertEqual(record["backend"], "svn")
            self.assertIn("unknown status", record["error"])

    def test_non_worktree_error_record_does_not_apply_problem_emblem(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/plain.txt")

        core.apply_emblem(
            item,
            {
                "path": "/tmp/plain.txt",
                "backend": "",
                "root": "",
                "worktree_id": "",
                "status": "error",
                "error": "not inside a versioned working tree",
            },
        )

        self.assertEqual(item.emblems, [])

    def test_update_path_retries_once_after_daemon_error(self):
        seen_calls = []

        def seen(paths):
            seen_calls.append(list(paths))
            if len(seen_calls) == 1:
                raise RuntimeError("activating")
            return ["/tmp/repo"]

        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=seen,
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/tracked.txt",
                    "worktree_id": "/tmp/repo",
                    "status": "ok",
                }
            ],
        )

        record = core.update_path("/tmp/repo/tracked.txt")

        self.assertEqual(record["status"], "ok")
        self.assertEqual(len(seen_calls), 2)
        self.assertEqual(core.last_error, "")

    def test_visible_item_cache_is_bounded_and_recent_first(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(max_visible_items=2)
        first = FakeItem("/tmp/repo/one.txt")
        second = FakeItem("/tmp/repo/two.txt")
        third = FakeItem("/tmp/repo/three.txt")

        core.track_visible_item(first.path, first)
        core.track_visible_item(second.path, second)
        core.track_visible_item(third.path, third)

        self.assertEqual(
            list(core.visible_items.keys()),
            ["/tmp/repo/three.txt", "/tmp/repo/two.txt"],
        )

    def test_changed_file_invalidates_matching_visible_item(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        item = FakeItem("/tmp/repo/tracked.txt")
        core.track_visible_item(item.path, item)
        core.cache.update(
            [
                {
                    "path": item.path,
                    "worktree_id": "/tmp/repo",
                    "status": "ok",
                }
            ]
        )

        invalidated = core.on_status_changed("/tmp/repo", [item.path])

        self.assertEqual(invalidated, [item.path])
        self.assertEqual(item.invalidated, 1)
        self.assertIsNone(core.cache.get(item.path))

    def test_changed_child_invalidates_visible_parent_folder(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        folder = FakeItem("/tmp/repo/dir")
        core.track_visible_item(folder.path, folder)
        core.cache.update(
            [
                {
                    "path": folder.path,
                    "worktree_id": "/tmp/repo",
                    "status": "ok",
                }
            ]
        )

        invalidated = core.on_status_changed(
            "/tmp/repo",
            ["/tmp/repo/dir/nested.txt"],
        )

        self.assertEqual(invalidated, [folder.path])
        self.assertEqual(folder.invalidated, 1)

    def test_status_changed_ignores_other_worktree_items(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        other = FakeItem("/tmp/other/tracked.txt")
        core.track_visible_item(other.path, other)
        core.cache.update(
            [
                {
                    "path": other.path,
                    "worktree_id": "/tmp/other",
                    "status": "ok",
                }
            ]
        )

        invalidated = core.on_status_changed(
            "/tmp/repo",
            ["/tmp/repo/tracked.txt"],
        )

        self.assertEqual(invalidated, [])
        self.assertEqual(other.invalidated, 0)
        self.assertIsNotNone(core.cache.get(other.path))

    def test_empty_changed_paths_invalidates_visible_worktree_items(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        first = FakeItem("/tmp/repo/a.txt")
        second = FakeItem("/tmp/repo/b.txt")
        core.track_visible_item(first.path, first)
        core.track_visible_item(second.path, second)
        core.cache.update(
            [
                {"path": first.path, "worktree_id": "/tmp/repo", "status": "ok"},
                {"path": second.path, "worktree_id": "/tmp/repo", "status": "ok"},
            ]
        )

        invalidated = core.on_status_changed("/tmp/repo", [])

        self.assertEqual(invalidated, [second.path, first.path])
        self.assertEqual(first.invalidated, 1)
        self.assertEqual(second.invalidated, 1)

    def test_visible_item_without_invalidation_method_is_ignored(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        path = "/tmp/repo/tracked.txt"
        core.track_visible_item(path, object())
        core.cache.update(
            [{"path": path, "worktree_id": "/tmp/repo", "status": "ok"}]
        )

        invalidated = core.on_status_changed("/tmp/repo", [path])

        self.assertEqual(invalidated, [])

    def test_mixin_subscribes_to_status_changed_signal(self):
        with mock.patch(
            "nemovcs.nemo_plugin.subscribe_daemon_status_changed",
            return_value="handle",
        ) as subscribe:
            provider = nemo_plugin.NemoVCSInfoProviderMixin()

        self.assertEqual(provider.nemovcs_signal_subscription, "handle")
        subscribe.assert_called_once_with(provider.on_daemon_status_changed)

    def test_mixin_records_subscription_failure(self):
        with mock.patch(
            "nemovcs.nemo_plugin.subscribe_daemon_status_changed",
            side_effect=RuntimeError("no dbus"),
        ):
            provider = nemo_plugin.NemoVCSInfoProviderMixin()

        self.assertIsNone(provider.nemovcs_signal_subscription)
        self.assertEqual(provider.nemovcs_core.last_error, "no dbus")

    def test_diagnostics_writes_json_lines_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "plugin.log"
            diagnostics = nemo_plugin.PluginDiagnostics(log_path)
            core = nemo_plugin.NemoVCSInfoProviderCore(
                diagnostics=diagnostics,
                seen=lambda paths: ["/tmp/repo"],
                get_status=lambda paths: [
                    {
                        "path": "/tmp/repo/tracked.txt",
                        "worktree_id": "/tmp/repo",
                        "status": "modified",
                    }
                ],
            )

            core.update_item(FakeItem("/tmp/repo/tracked.txt"))

            lines = log_path.read_text(encoding="utf-8").splitlines()
            events = [json.loads(line)["event"] for line in lines]
            self.assertIn("status", events)
            self.assertIn("update-item", events)

    def test_diagnostics_from_environment_uses_configured_path(self):
        with mock.patch.dict("os.environ", {"NEMOVCS_PLUGIN_LOG": "/tmp/nemovcs.log"}):
            diagnostics = nemo_plugin.PluginDiagnostics.from_environment()

        self.assertEqual(diagnostics.path, Path("/tmp/nemovcs.log"))

    def test_diagnostics_write_errors_do_not_escape(self):
        diagnostics = nemo_plugin.PluginDiagnostics("/tmp/nemovcs.log")

        with mock.patch("pathlib.Path.open", side_effect=OSError("denied")):
            diagnostics.log("event")

    def test_menu_launch_command_runs_nemovcs_through_current_python(self):
        command = nemo_plugin.menu_launch_command(("nemovcs", "rename-dialog", "/tmp/repo"))

        self.assertEqual(
            command,
            [
                sys.executable,
                "-m",
                "nemovcs",
                "rename-dialog",
                "/tmp/repo",
            ],
        )

    def test_menu_launch_env_prepends_source_root_for_nemovcs_commands(self):
        env = nemo_plugin.menu_launch_env(("nemovcs", "rename-dialog", "/tmp/repo"))

        self.assertIsNotNone(env)
        assert env is not None
        self.assertEqual(
            env["PYTHONPATH"].split(":", 1)[0],
            str(Path(nemo_plugin.__file__).resolve().parents[1]),
        )

    def test_menu_launch_command_leaves_external_tools_unchanged(self):
        self.assertEqual(
            nemo_plugin.menu_launch_command(("meld", "/tmp/a", "/tmp/b")),
            ["meld", "/tmp/a", "/tmp/b"],
        )
        self.assertIsNone(nemo_plugin.menu_launch_env(("meld", "/tmp/a", "/tmp/b")))

    def test_menu_item_sets_sensitive_property_when_binding_has_no_method(self):
        class FakeMenuItem:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.properties = {}
                self.connected = []

            def connect(self, *args):
                self.connected.append(args)

            def set_property(self, name, value):
                self.properties[name] = value

        class FakeNemo:
            MenuItem = FakeMenuItem

        provider = nemo_plugin.NemoVCSInfoProviderMixin.__new__(
            nemo_plugin.NemoVCSInfoProviderMixin
        )
        spec = nemo_plugin.MenuActionSpec(
            name="NemoVCS::Disabled",
            label="Disabled",
            command=("nemovcs", "about-dialog"),
            sensitive=False,
        )

        item = provider.nemovcs_menu_item(FakeNemo, spec)

        self.assertEqual(item.properties, {"sensitive": False})
        self.assertEqual(len(item.connected), 1)

    def test_git_submenu_group_uses_existing_dialog_commands(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        self.assertEqual([group.label for group in groups], ["Git NemoVCS"])
        self.assertEqual(groups[0].icon, "nemovcs-git")
        specs = list(groups[0].items)
        commands = [spec.command for spec in specs if not spec.separator]
        icons_by_label = {
            spec.label: spec.icon
            for spec in specs
            if not spec.separator
        }
        self.assertIn(
            ("nemovcs", "commit-dialog", "/tmp/repo/src/app.py"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "update-dialog", "/tmp/repo/src/app.py"),
            commands,
        )
        self.assertIn(
            (
                "nemovcs",
                "stage-dialog",
                "--operation",
                "stage",
                "/tmp/repo/src/app.py",
            ),
            commands,
        )
        self.assertIn(
            ("nemovcs", "revert-dialog", "/tmp/repo/src/app.py"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "rename-dialog", "/tmp/repo/src/app.py"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "push-dialog", "/tmp/repo/src/app.py"),
            commands,
        )
        self.assertEqual(icons_by_label["Commit..."], "nemovcs-commit")
        self.assertEqual(icons_by_label["Update..."], "nemovcs-update")
        self.assertEqual(icons_by_label["Stage..."], "nemovcs-add")
        self.assertEqual(icons_by_label["Rename..."], "nemovcs-rename")
        self.assertEqual(icons_by_label["Revert..."], "nemovcs-revert")
        self.assertEqual(icons_by_label["Push..."], "nemovcs-push")
        self.assertEqual(icons_by_label["Status..."], "nemovcs-status")
        self.assertEqual(icons_by_label["Log..."], "nemovcs-show-log")
        self.assertEqual(icons_by_label["Settings..."], "nemovcs-settings")
        self.assertEqual(icons_by_label["About..."], "nemovcs")

    def test_git_submenu_includes_clean_switch_branch_menu(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.current_branch_name", return_value="main")
        ), mock.patch("nemovcs.git.worktree_dirty", return_value=False), (
            mock.patch(
                "nemovcs.git.recent_branches",
                return_value=["feature/new", "main", "release"],
            )
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        switch = next(spec for spec in groups[0].items if spec.label == "Switch Branch")

        self.assertTrue(switch.sensitive)
        self.assertEqual(switch.icon, "nemovcs-git")
        self.assertEqual(
            [child.label for child in switch.children if not child.separator],
            ["feature/new", "main", "release", "Others..."],
        )
        self.assertEqual(
            switch.children[0].command,
            (
                "nemovcs",
                "switch-branch-dialog",
                "/tmp/repo",
                "feature/new",
            ),
        )
        self.assertFalse(switch.children[1].sensitive)
        self.assertEqual(switch.children[1].icon, "object-select-symbolic")
        self.assertIsNone(switch.children[0].icon)
        self.assertIsNone(switch.children[2].icon)
        self.assertTrue(switch.children[-1].sensitive)
        self.assertIsNone(switch.children[-1].icon)
        self.assertEqual(
            switch.children[-1].command,
            ("nemovcs", "switch-branch-dialog", "/tmp/repo"),
        )

    def test_git_switch_branch_menu_stays_active_with_single_branch(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.current_branch_name", return_value="main")
        ), mock.patch("nemovcs.git.worktree_dirty", return_value=False), (
            mock.patch("nemovcs.git.recent_branches", return_value=["main"])
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        switch = next(spec for spec in groups[0].items if spec.label == "Switch Branch")

        self.assertTrue(switch.sensitive)
        self.assertEqual(
            [child.label for child in switch.children if not child.separator],
            ["main", "Others..."],
        )
        self.assertFalse(switch.children[0].sensitive)
        self.assertEqual(switch.children[0].icon, "object-select-symbolic")
        self.assertTrue(switch.children[-1].sensitive)

    def test_git_switch_branch_menu_includes_current_when_recent_list_is_empty(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.current_branch_name", return_value="main")
        ), mock.patch("nemovcs.git.worktree_dirty", return_value=False), (
            mock.patch("nemovcs.git.recent_branches", return_value=[])
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        switch = next(spec for spec in groups[0].items if spec.label == "Switch Branch")

        self.assertTrue(switch.sensitive)
        self.assertEqual(
            [child.label for child in switch.children if not child.separator],
            ["main", "Others..."],
        )
        self.assertFalse(switch.children[0].sensitive)
        self.assertEqual(switch.children[0].icon, "object-select-symbolic")

    def test_git_switch_branch_menu_disables_branch_checked_out_elsewhere(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.current_branch_name", return_value="main")
        ), mock.patch("nemovcs.git.worktree_dirty", return_value=False), (
            mock.patch("nemovcs.git.recent_branches", return_value=["main", "feature/new"])
        ), mock.patch(
            "nemovcs.git.worktree_branch_locations",
            return_value={
                "main": Path("/tmp/repo"),
                "feature/new": Path("/tmp/feature"),
            },
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        switch = next(spec for spec in groups[0].items if spec.label == "Switch Branch")
        occupied = next(spec for spec in switch.children if spec.label == "feature/new")

        self.assertFalse(occupied.sensitive)
        self.assertEqual(occupied.tip, "Checked out at /tmp/feature")

    def test_git_switch_branch_menu_disables_branch_actions_when_worktree_is_dirty(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")), (
            mock.patch("nemovcs.git.current_branch_name", return_value="main")
        ), mock.patch("nemovcs.git.worktree_dirty", return_value=True), (
            mock.patch("nemovcs.git.recent_branches", return_value=["feature/new", "main"])
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        switch = next(spec for spec in groups[0].items if spec.label == "Switch Branch")

        self.assertTrue(switch.sensitive)
        self.assertEqual(switch.icon, "emblem-nemovcs-modified")
        self.assertEqual(
            [child.label for child in switch.children if not child.separator],
            ["feature/new", "main", "Others..."],
        )
        self.assertFalse(switch.children[0].sensitive)
        self.assertFalse(switch.children[1].sensitive)
        self.assertEqual(switch.children[1].icon, "object-select-symbolic")
        self.assertFalse(switch.children[-1].sensitive)

    def test_git_top_level_specs_use_common_dialog_commands(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        core.cache.update(
            [
                {
                    "path": "/tmp/repo/src/app.py",
                    "worktree_id": "git:/tmp/repo",
                    "status": "modified",
                }
            ]
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            specs = core.top_level_specs(["/tmp/repo/src/app.py"])

        self.assertEqual(
            [spec.label for spec in specs],
            ["Diff..."],
        )
        self.assertEqual(
            [spec.icon for spec in specs],
            ["nemovcs-diff"],
        )
        self.assertEqual(
            [spec.command for spec in specs],
            [
                ("nemovcs", "diff-dialog", "/tmp/repo/src/app.py"),
            ],
        )

    def test_top_level_diff_is_hidden_for_clean_path(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        core.cache.update(
            [
                {
                    "path": "/tmp/repo/src/app.py",
                    "worktree_id": "git:/tmp/repo",
                    "status": "ok",
                }
            ]
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            specs = core.top_level_specs(["/tmp/repo/src/app.py"])

        self.assertEqual(specs, [])

    def test_top_level_diff_is_hidden_for_unversioned_path(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        core.cache.update(
            [
                {
                    "path": "/tmp/repo/tmp",
                    "worktree_id": "git:/tmp/repo",
                    "status": "unversioned",
                }
            ]
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            specs = core.top_level_specs(["/tmp/repo/tmp"])

        self.assertEqual(specs, [])

    def test_top_level_diff_is_hidden_when_status_is_not_cached(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: [],
            get_status=lambda paths: [],
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            specs = core.top_level_specs(["/tmp/repo/src/app.py"])

        self.assertEqual(specs, [])

    def test_top_level_diff_uses_daemon_status_when_status_is_not_cached(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: ["git:/tmp/repo"],
            get_status=lambda paths: [
                {
                    "path": "/tmp/repo/src/app.py",
                    "worktree_id": "git:/tmp/repo",
                    "status": "modified",
                }
            ],
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ):
            specs = core.top_level_specs(["/tmp/repo/src/app.py"])

        self.assertEqual([spec.label for spec in specs], ["Diff..."])

    def test_top_level_diff_compares_two_selected_files_with_meld(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.txt"
            right = Path(tmp) / "right.txt"
            left.write_text("left\n", encoding="utf-8")
            right.write_text("right\n", encoding="utf-8")

            specs = core.top_level_specs([left, right])

        self.assertEqual([spec.label for spec in specs], ["Diff..."])
        self.assertEqual(specs[0].command, ("meld", str(left), str(right)))

    def test_top_level_diff_compares_two_selected_directories_with_meld(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            left.mkdir()
            right.mkdir()

            specs = core.top_level_specs([left, right])

        self.assertEqual([spec.label for spec in specs], ["Diff..."])
        self.assertEqual(specs[0].command, ("meld", str(left), str(right)))

    def test_top_level_diff_hides_mixed_two_path_compare(self):
        core = nemo_plugin.NemoVCSInfoProviderCore(
            seen=lambda paths: [],
            get_status=lambda paths: [],
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "dir"
            file_path = Path(tmp) / "file.txt"
            directory.mkdir()
            file_path.write_text("file\n", encoding="utf-8")

            with mock.patch(
                "nemovcs.nemo_plugin.matching_backend_ids",
                return_value=[],
            ):
                specs = core.top_level_specs([directory, file_path])

        self.assertEqual(specs, [])

    def test_svn_submenu_group_uses_existing_dialog_commands(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["svn"])
        ):
            groups = core.submenu_groups(["/tmp/wc/tracked.c"])

        self.assertEqual([group.label for group in groups], ["SVN NemoVCS"])
        self.assertEqual(groups[0].icon, "nemovcs-svn")
        specs = list(groups[0].items)
        commands = [spec.command for spec in specs if not spec.separator]
        icons_by_label = {
            spec.label: spec.icon
            for spec in specs
            if not spec.separator
        }
        self.assertIn(
            ("nemovcs", "commit-dialog", "/tmp/wc/tracked.c"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "update-dialog", "/tmp/wc/tracked.c"),
            commands,
        )
        self.assertIn(
            (
                "nemovcs",
                "stage-dialog",
                "--operation",
                "add",
                "/tmp/wc/tracked.c",
            ),
            commands,
        )
        self.assertIn(
            ("nemovcs", "revert-dialog", "/tmp/wc/tracked.c"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "rename-dialog", "/tmp/wc/tracked.c"),
            commands,
        )
        self.assertNotIn(
            ("nemovcs", "push-dialog", "/tmp/wc/tracked.c"),
            commands,
        )
        self.assertEqual(icons_by_label["Commit..."], "nemovcs-commit")
        self.assertEqual(icons_by_label["Update..."], "nemovcs-update")
        self.assertEqual(icons_by_label["Add..."], "nemovcs-add")
        self.assertEqual(icons_by_label["Rename..."], "nemovcs-rename")
        self.assertEqual(icons_by_label["Revert..."], "nemovcs-revert")
        self.assertEqual(icons_by_label["Status..."], "nemovcs-status")
        self.assertEqual(icons_by_label["Log..."], "nemovcs-show-log")

    def test_svn_top_level_specs_use_common_dialog_commands(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        core.cache.update(
            [
                {
                    "path": "/tmp/wc/tracked.c",
                    "worktree_id": "svn:/tmp/wc",
                    "status": "modified",
                }
            ]
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["svn"])
        ):
            specs = core.top_level_specs(["/tmp/wc/tracked.c"])

        self.assertEqual(
            [spec.command for spec in specs],
            [
                ("nemovcs", "diff-dialog", "/tmp/wc/tracked.c"),
            ],
        )

    def test_both_backend_matches_get_separate_submenu_groups(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        core.cache.update(
            [
                {
                    "path": "/tmp/combined",
                    "worktree_id": "git:/tmp/combined",
                    "status": "conflicted",
                }
            ]
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch(
                "nemovcs.nemo_plugin.matching_backend_ids",
                return_value=["git", "svn"],
            )
        ):
            groups = core.submenu_groups(["/tmp/combined"])
            top_level_specs = core.top_level_specs(["/tmp/combined"])

        self.assertEqual(
            [group.label for group in groups],
            ["Git NemoVCS", "SVN NemoVCS"],
        )
        self.assertEqual(
            [group.icon for group in groups],
            ["nemovcs-git", "nemovcs-svn"],
        )
        self.assertEqual([spec.label for spec in top_level_specs], ["Diff..."])

    def test_clone_submenu_groups_offer_git_clone_and_svn_checkout(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=True):
            groups = core.submenu_groups(["/tmp/target"])
            top_level_specs = core.top_level_specs(["/tmp/target"])

        self.assertEqual(
            [group.label for group in groups],
            ["Git NemoVCS", "SVN NemoVCS"],
        )
        self.assertEqual(
            [group.icon for group in groups],
            ["nemovcs-git", "nemovcs-svn"],
        )
        specs = [spec for group in groups for spec in group.items]
        commands = [spec.command for spec in specs if not spec.separator]
        icons_by_label = {spec.label: spec.icon for spec in specs if not spec.separator}
        self.assertIn(
            ("nemovcs", "clone-dialog", "--vcs", "git", "/tmp/target"),
            commands,
        )
        self.assertIn(
            ("nemovcs", "clone-dialog", "--vcs", "svn", "/tmp/target"),
            commands,
        )
        self.assertEqual(icons_by_label["Git Clone..."], "nemovcs-checkout")
        self.assertEqual(icons_by_label["SVN Checkout..."], "nemovcs-checkout")
        self.assertEqual(top_level_specs, [])

    def test_mixed_or_unknown_backend_has_no_submenu_groups(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=[])
        ):
            self.assertEqual(core.submenu_groups(["/tmp/path"]), [])
            self.assertEqual(core.top_level_specs(["/tmp/path"]), [])


class CloneTargetMenuTest(unittest.TestCase):
    def test_git_clone_menu_includes_create_repository(self):
        specs = nemo_plugin.git_clone_menu_specs(["/tmp/dir"])

        create = next(
            spec for spec in specs if spec.name == "NemoVCS::GitInit"
        )
        self.assertEqual(create.label, "Create Repository...")
        self.assertEqual(
            create.command, ("nemovcs", "init-dialog", "/tmp/dir")
        )
        # The clone action is still offered alongside it.
        self.assertIn(
            "NemoVCS::GitClone", [spec.name for spec in specs]
        )


class ForgeMenuSpecsTest(unittest.TestCase):
    def _forge(self, *, available=True, label="GitHub", forge_id="github", actions=None):
        from nemovcs.forge.base import ForgeAction

        forge = mock.Mock()
        forge.id = forge_id
        forge.label = label
        forge.icon = "nemovcs-git"
        forge.is_available.return_value = available
        forge.actions.return_value = (
            actions
            if actions is not None
            else [
                ForgeAction(id="open", label="Open on GitHub", icon="web-browser"),
            ]
        )
        return forge

    def _patch_repo(self, remote):
        return (
            mock.patch("nemovcs.git.repo_root", return_value=Path("/tmp/repo")),
            mock.patch("nemovcs.git.remote_url", return_value=remote),
            mock.patch("nemovcs.git.current_branch_name", return_value="main"),
            mock.patch("nemovcs.git.worktree_dirty", return_value=False),
            mock.patch("nemovcs.git.default_branch_name", return_value="main"),
        )

    def test_detected_forge_returns_submenu_with_actions(self):
        hosting = self._forge()
        patches = self._patch_repo("git@github.com:o/r.git")
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch(
            "nemovcs.forge.detect_forge", return_value=hosting
        ):
            specs = nemo_plugin.forge_menu_specs(["/tmp/repo/src/app.py"])

        self.assertEqual(len(specs), 1)
        submenu = specs[0]
        self.assertEqual(submenu.label, "GitHub")
        self.assertEqual(submenu.icon, "nemovcs-git")
        child = submenu.children[0]
        self.assertEqual(child.label, "Open on GitHub")
        self.assertEqual(child.icon, "web-browser")
        self.assertTrue(child.sensitive)
        self.assertEqual(
            child.command, ("nemovcs", "forge", "open", "/tmp/repo/src/app.py")
        )

    def test_action_command_routes_by_kind(self):
        from nemovcs.forge.base import (
            FORGE_ACTION_DIALOG,
            FORGE_ACTION_OUTPUT,
            ForgeAction,
        )

        launch = ForgeAction(id="open", label="Open")
        output = ForgeAction(id="cr-list", label="List", kind=FORGE_ACTION_OUTPUT)
        dialog = ForgeAction(id="cr-create", label="Create", kind=FORGE_ACTION_DIALOG)
        paths = ["/tmp/repo/app.py"]

        self.assertEqual(
            nemo_plugin.forge_action_command(launch, paths, "github"),
            ("nemovcs", "forge", "open", "/tmp/repo/app.py"),
        )
        self.assertEqual(
            nemo_plugin.forge_action_command(output, paths, "github"),
            ("nemovcs", "forge", "--output", "cr-list", "/tmp/repo/app.py"),
        )
        self.assertEqual(
            nemo_plugin.forge_action_command(dialog, paths, "github"),
            (
                "nemovcs", "forge-dialog", "--forge", "github",
                "--action", "cr-create", "/tmp/repo/app.py",
            ),
        )

    def test_disabled_action_renders_insensitive_with_reason(self):
        from nemovcs.forge.base import ForgeAction

        hosting = self._forge(
            actions=[
                ForgeAction(
                    id="create-pr",
                    label="Create Pull Request",
                    enabled=False,
                    disabled_reason="current branch is the default branch",
                ),
            ]
        )
        patches = self._patch_repo("git@github.com:o/r.git")
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch(
            "nemovcs.forge.detect_forge", return_value=hosting
        ):
            specs = nemo_plugin.forge_menu_specs(["/tmp/repo"])

        child = specs[0].children[0]
        self.assertFalse(child.sensitive)
        self.assertEqual(child.tip, "current branch is the default branch")

    def test_no_remote_offers_publish_for_available_forges(self):
        hosting = self._forge()
        patches = self._patch_repo("")
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch(
            "nemovcs.forge.registered_forges", return_value=(hosting,)
        ):
            specs = nemo_plugin.forge_menu_specs(["/tmp/repo"])

        self.assertEqual(len(specs), 1)
        publish = specs[0]
        self.assertEqual(publish.label, "Publish to GitHub...")
        self.assertEqual(publish.icon, "nemovcs-git")
        self.assertEqual(
            publish.command,
            ("nemovcs", "publish-dialog", "--forge", "github", "/tmp/repo"),
        )

    def test_no_remote_skips_unavailable_forges(self):
        hosting = self._forge(available=False)
        patches = self._patch_repo("")
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch(
            "nemovcs.forge.registered_forges", return_value=(hosting,)
        ):
            self.assertEqual(nemo_plugin.forge_menu_specs(["/tmp/repo"]), [])

    def test_empty_without_repo_root(self):
        with mock.patch("nemovcs.git.repo_root", return_value=None):
            self.assertEqual(nemo_plugin.forge_menu_specs(["/tmp/x"]), [])

    def test_empty_when_no_forge_detected(self):
        patches = self._patch_repo("git@example.com:o/r.git")
        with patches[0], patches[1], patches[2], patches[3], patches[4], mock.patch(
            "nemovcs.forge.detect_forge", return_value=None
        ):
            self.assertEqual(nemo_plugin.forge_menu_specs(["/tmp/repo"]), [])

    def test_git_menu_places_forge_after_log_with_separator(self):
        extra = nemo_plugin.MenuActionSpec(name="NemoVCS::Forge", label="GitHub")
        specs = nemo_plugin.git_menu_specs(["/tmp/a", "/tmp/b"], [extra])
        names = [spec.name for spec in specs]

        log_index = names.index("NemoVCS::GitLog")
        self.assertEqual(names[log_index + 1], "NemoVCS::GitForgeSep")
        self.assertTrue(specs[log_index + 1].separator)
        self.assertEqual(names[log_index + 2], "NemoVCS::Forge")
        self.assertEqual(names[log_index + 3], "NemoVCS::GitSep2")

    def test_git_menu_omits_forge_separator_without_extras(self):
        specs = nemo_plugin.git_menu_specs(["/tmp/a", "/tmp/b"])
        names = [spec.name for spec in specs]

        self.assertNotIn("NemoVCS::GitForgeSep", names)
        log_index = names.index("NemoVCS::GitLog")
        self.assertEqual(names[log_index + 1], "NemoVCS::GitSep2")

    def test_git_submenu_group_includes_forge_items(self):
        core = nemo_plugin.NemoVCSInfoProviderCore()
        extra = nemo_plugin.MenuActionSpec(
            name="NemoVCS::Forge",
            label="GitHub",
            children=(
                nemo_plugin.MenuActionSpec(
                    name="NemoVCS::ForgeOpen", label="Open on GitHub"
                ),
            ),
        )

        with mock.patch("nemovcs.nemo_plugin.is_clone_target", return_value=False), (
            mock.patch("nemovcs.nemo_plugin.matching_backend_ids", return_value=["git"])
        ), mock.patch(
            "nemovcs.nemo_plugin.forge_menu_specs", return_value=[extra]
        ):
            groups = core.submenu_groups(["/tmp/repo/src/app.py"])

        self.assertEqual([group.label for group in groups], ["Git NemoVCS"])
        self.assertIn("GitHub", [item.label for item in groups[0].items])


if __name__ == "__main__":
    unittest.main()
