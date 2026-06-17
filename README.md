# NemoVCS

NemoVCS is a small Git integration for the Nemo file manager.

Status: pre-alpha functional prototype. The command skeleton, Nemo Action files,
contextual visibility, temporary icons, basic terminal-backed operations, a
first GTK commit dialog, and a reusable GTK command logger are in place. This is
still not ready for unattended daily use.

The first target is intentionally narrow:

- Git only
- Nemo first
- context menu operations through Nemo Actions
- no runtime Python dependencies beyond the standard library
- no background status daemon until the action flow is solid

RabbitVCS is useful reference material, but NemoVCS is a new project.
The prototype keeps each operation explicit so early behavior is easy to test.

## Current Functionality

The current prototype installs contextual Nemo menu items that appear only for
paths inside Git working trees.

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
and `Log...` currently run in a terminal and pause before closing. `Settings...`
is a placeholder, and `About...` reports project information.

`Diff...` uses Meld through Git's difftool support. If Meld is not installed,
the diff action is hidden by Nemo's action dependency handling.

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

## Roadmap

1. Implement the operation actions with robust Git command handling.
2. Expand the GTK logger and use it for more operations where terminal output is
   not enough.
3. Add a Nemo plugin for emblems, columns, and dynamic menu behavior.
4. Add `nemovcs-statusd` for cached on-visit status with filesystem invalidation.
