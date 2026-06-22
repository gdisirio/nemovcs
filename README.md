# NemoVCS

NemoVCS is a Git integration for the Nemo file manager.

Status: alpha. It is usable for local testing, but still needs broader manual
testing and hardening before unattended daily use.

## Features

- Context menu actions inside Git working trees.
- GTK dialogs for stage, commit, status, update, log, settings, and about.
- Meld integration for diffs.
- Live status emblems in Nemo:
  - clean paths,
  - modified paths and folders,
  - conflicted paths and folders.
- DBus-activated status daemon with cached status and filesystem monitoring.
- Linked Git worktrees are treated as independent worktrees.

## Dependencies

Required:

- Nemo
- nemo-python
- Python 3.10 or newer
- python3-gi / PyGObject
- python3-dbus
- Git

Optional:

- Meld, for the `Diff...` action.

NemoVCS shells out to the `git` executable. It does not use a Python Git
library.

## Install

The current install flow is for per-user source-tree testing.

From the repository root:

```sh
./scripts/install-actions.sh
./scripts/install-nemo-extension.sh
./scripts/install-statusd-service.sh
nemo --quit
```

What this installs:

- Nemo action files into `~/.local/share/nemo/actions`.
- Temporary action icons under `~/.local/share/nemo/actions/nemovcs-icons`.
- The generated nemo-python extension:
  `~/.local/share/nemo-python/extensions/NemoVCS.py`.
- Status emblem icons into `~/.local/share/icons/hicolor/scalable/emblems`.
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

Open Nemo inside a Git working tree.

Top-level actions:

- `Commit...`
- `Stage...`
- `Update...`

`NemoVCS` submenu actions:

- `Status...`
- `Diff...`
- `Log...`
- `Settings...`
- `About...`

The status daemon is started automatically through session DBus activation when
Nemo asks for status.

## Troubleshooting

Restart Nemo after installing, uninstalling, or changing the extension:

```sh
nemo --quit
```

Check whether the daemon can answer:

```sh
PYTHONPATH=src python3 -m nemovcs status-cache --dbus .
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

RabbitVCS is useful reference material, but NemoVCS is a new project.

Temporary icons are currently derived from RabbitVCS assets. They should be
replaced with NemoVCS-native icons or clearly documented upstream assets before
a broader release.
