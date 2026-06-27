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
        self.assertIsNone(nemo_plugin.primary_emblem("ignored"))
        self.assertIsNone(nemo_plugin.primary_emblem("loading"))
        self.assertIsNone(nemo_plugin.primary_emblem("stale"))
        self.assertIsNone(nemo_plugin.primary_emblem("error"))

    def test_daemon_error_is_recorded_and_does_not_escape(self):
        def seen(_paths):
            raise RuntimeError("no daemon")

        core = nemo_plugin.NemoVCSInfoProviderCore(seen=seen, get_status=lambda _: [])

        self.assertIsNone(core.update_path("/tmp/repo/tracked.txt"))
        self.assertEqual(core.last_error, "no daemon")

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
        subscribe.assert_called_once_with(provider.nemovcs_core.on_status_changed)

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


if __name__ == "__main__":
    unittest.main()
