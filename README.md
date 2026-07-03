# NemoVCS

NemoVCS is version-control integration for the Nemo file manager, focused on
fast context-menu operations and live file status inside Cinnamon/Nemo.

Status: alpha. It is usable for source-tree testing, but still needs broader
manual testing and hardening before unattended daily use.

## Features

- Context menu actions inside Git and Subversion working trees.
- Clone and checkout actions for unversioned directories.
- GTK dialogs for stage/add, commit, rename, revert, status, update, push, log,
  settings, and about.
- Meld integration for selected-path diffs and two-path comparisons.
- Repository context bar showing backend, active branch/head, status, and root.
- Live status emblems in Nemo:
  - clean paths,
  - modified paths and folders,
  - conflicted paths and folders,
  - unversioned paths and folders.
- DBus-activated status daemon with cached status, filesystem monitoring, TTL
  revalidation, and async scans.
- Linked Git worktrees are treated as independent worktrees.

## Dependencies

Required:

- Nemo
- nemo-python
- Python 3.10 or newer
- python3-gi / PyGObject
- python3-dbus
- Git and/or Subversion command-line clients

Optional:

- Meld, for the `Diff...` action.

NemoVCS shells out to native VCS tools such as `git` and `svn`. It does not use
Python VCS libraries.

## Install

The current install flow is for per-user source-tree testing.

From the repository root:

```sh
./scripts/install-nemo-extension.sh
./scripts/install-statusd-service.sh
nemo --quit
```

What this does:

- Legacy NemoVCS action files are removed from `~/.local/share/nemo/actions`
  and pruned from Nemo's action layout.
- The generated nemo-python extension:
  `~/.local/share/nemo-python/extensions/NemoVCS.py`.
- NemoVCS icons into `~/.local/share/icons/hicolor/scalable`.
- The status daemon wrapper:
  `~/.local/bin/nemovcs-statusd`.
- The DBus activation file:
  `~/.local/share/dbus-1/services/io.github.gdisirio.NemoVCS.Statusd.service`.

After installing the DBus service, the status daemon starts on demand. You do
not need to start it manually for normal use.

## Uninstall

To remove the per-user development install and stop the status daemon:

```sh
./scripts/uninstall.sh
nemo --quit
```

The uninstall script removes only NemoVCS-owned files and prunes NemoVCS entries
from Nemo's action layout. Unrelated Nemo actions are preserved.

## Use

Open Nemo inside a Git or Subversion working tree, or on an unversioned
directory where you want to clone or check out a working copy.

The context menu is provided by the NemoVCS nemo-python extension so the
top-level items and backend submenus stay in the same menu group.

Top-level actions:

- `Diff...`

Backend submenu actions:

- `Git NemoVCS`
- `SVN NemoVCS`
- `Commit...`
- `Update...`
- `Git Clone...`
- `SVN Checkout...`
- `Stage...`
- `Add...`
- `Rename...`
- `Revert...`
- `Push...`
- `Status...`
- `Log...`
- `Settings...`
- `About...`

The status daemon is started automatically through session DBus activation when
Nemo asks for status.

Status results are cached per worktree. Filesystem monitor events mark cached
worktrees stale, and a bounded scan TTL is used as a fallback for missed nested
changes. Scans run outside the daemon's DBus/GLib main loop, so the first query
for an unscanned worktree can briefly report `loading` before Nemo receives a
status-changed signal and refreshes the visible items.

The same operations are available from the source tree through the CLI:

```sh
PYTHONPATH=src python3 -m nemovcs status .
PYTHONPATH=src python3 -m nemovcs log .
PYTHONPATH=src python3 -m nemovcs commit-dialog .
PYTHONPATH=src python3 -m nemovcs status-cache --dbus .
```

## Troubleshooting

Restart Nemo after installing, uninstalling, or changing the extension:

```sh
nemo --quit
```

Check whether the daemon can answer:

```sh
PYTHONPATH=src python3 -m nemovcs status-cache --dbus .
```

Open the settings panel to inspect cached worktrees, refresh the cache view, or
change status daemon settings such as cache size, refresh debounce, and scan
TTL:

```sh
PYTHONPATH=src python3 -m nemovcs settings
```

Run the daemon manually while debugging:

```sh
PYTHONPATH=src python3 -m nemovcs statusd
```

Enable optional plugin diagnostics when launching Nemo manually:

```sh
NEMOVCS_PLUGIN_LOG=/tmp/nemovcs-plugin.log nemo
```

## Development

NemoVCS intentionally keeps runtime dependencies small. Core repository
operations shell out to `git` and `svn`; machine-readable state is parsed from
stable command output such as Git porcelain status and SVN XML status.

Run the CLI directly from the source tree:

```sh
PYTHONPATH=src python3 -m nemovcs --help
```

Run tests:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Compile-check Python files:

```sh
python3 -m compileall -q src tests scripts
```

If `pip` is available, the Python package can also be installed in editable
mode:

```sh
python3 -m pip install -e .
```

## Notes

- RabbitVCS is useful reference material, but NemoVCS is a separate project and
  does not reuse RabbitVCS internals.
- Some icons are temporary and should be replaced with NemoVCS-native artwork or
  kept with complete attribution before a broader release.
