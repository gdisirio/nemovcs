# NemoVCS

NemoVCS is a small Git integration for the Nemo file manager.

Status: alpha. NemoVCS now has contextual Nemo Actions, GTK commit/status/update
flows, a DBus-activated status daemon, and a `nemo-python` emblem plugin for
clean, modified, and conflicted Git status. It is usable for local testing, but
still needs more hardening before unattended daily use.

The first target is intentionally narrow:

- Git only
- Nemo first
- context menu operations through Nemo Actions
- live emblems through a lightweight Nemo plugin
- cached status through a DBus-activated daemon
- no Python Git library; Git remains the status/action authority

RabbitVCS is useful reference material, but NemoVCS is a new project.
The prototype keeps each operation explicit so early behavior is easy to test.

## Current Functionality

The current alpha installs contextual Nemo menu items that appear only for paths
inside Git working trees, plus a Nemo plugin for live status emblems.

Top-level actions:

- `Commit...`
- `Update...`

`NemoVCS` submenu actions:

- `Status...`
- `Diff...` opens Meld
- `Log...`
- `Settings...`
- `About...`

`Commit...` opens the first GTK commit dialog with a message editor, flat
changed-file checklist, include checkboxes, and per-file context menu. The
stage and commit steps run through a GTK logger with `Summary` and `Output`
tabs.

`Update...` runs `git pull --ff-only` through the same GTK logger. `Status...`
opens a GTK status window with a structured changed-file list in `Summary` and
raw `git status --short --branch` text in `Output`. `Log...` runs through the
GTK logger. `Settings...` is a GTK placeholder, and `About...` reports project
information in a GTK about dialog.

`Diff...` launches Meld through Git's difftool support without opening a
terminal. If Meld is not installed, the diff action is hidden by Nemo's action
dependency handling.

Status emblems are provided by the Nemo plugin:

- clean paths use the normal emblem,
- modified paths and folders use the modified emblem,
- conflicted paths and folders use the conflict emblem.

The status daemon keeps a bounded cache of recently seen worktrees, supports
linked worktrees as independent worktrees, watches cached worktrees with
filesystem monitors, and is started on demand by session DBus activation.

## Development

Run the CLI directly from the source tree:

```sh
PYTHONPATH=src python3 -m nemovcs --help
```

Run tests from the source tree:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

If `pip` is available, install the Python package in editable mode:

```sh
python3 -m pip install -e .
```

## Nemo Actions

Action files live in `data/nemo/actions`.

For per-user testing, install the actions and temporary icons with:

```sh
./scripts/install-actions.sh
```

Then restart Nemo:

```sh
nemo --quit
```

The actions use `Conditions=exec nemovcs action-visible inside-worktree ...`
so they only appear for paths inside Git working trees.

The installer also writes the current `NemoVCS` submenu layout into Nemo's user
action layout file.

## Nemo Plugin

The status-emblem plugin is an early prototype. It installs a `nemo-python`
`InfoProvider` that resolves local file paths, talks to the foreground status
daemon, and applies one primary emblem for `ok`, `modified`, or `conflicted`
status. It also listens for daemon status-change signals and invalidates
bounded visible file items so Nemo can refresh emblems without navigating away.

For per-user source-tree testing, install the extension with:

```sh
./scripts/install-nemo-extension.sh
./scripts/install-statusd-service.sh
```

The status daemon is DBus-activated after installing the service. A DBus call
to `io.github.gdisirio.NemoVCS.Statusd` starts it on demand. You can also run
it manually while debugging:

```sh
PYTHONPATH=src python3 -m nemovcs statusd
```

Optional plugin diagnostics can be enabled when launching Nemo manually:

```sh
NEMOVCS_PLUGIN_LOG=/tmp/nemovcs-plugin.log nemo
```

Then restart Nemo:

```sh
nemo --quit
```

To remove the per-user development install and stop the status daemon:

```sh
./scripts/uninstall.sh
nemo --quit
```

## Roadmap

1. Harden live Nemo invalidation and linked-worktree behavior with broader
   manual testing.
2. Add optional diagnostics and configuration for cache sizes and plugin
   behavior.
3. Replace temporary RabbitVCS-derived icons with NemoVCS-native assets.
4. Expand structured UI for log and other operations.
