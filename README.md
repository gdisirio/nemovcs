# NemoVCS

NemoVCS is a small Git integration for the Nemo file manager.

The first target is intentionally narrow:

- Git only
- Nemo first
- context menu operations through Nemo Actions
- no runtime Python dependencies beyond the standard library
- no background status daemon until the action flow is solid

RabbitVCS is useful reference material, but NemoVCS is a new project.

## Development

Run the CLI directly from the source tree:

```sh
PYTHONPATH=src python3 -m nemovcs --help
```

Run tests:

```sh
python3 -m unittest discover -s tests
```

Install the Python package in editable mode:

```sh
python3 -m pip install -e .
```

## Nemo Actions

Action files live in `data/nemo/actions`.

For per-user testing, copy or symlink them into:

```text
~/.local/share/nemo/actions
```

Then restart Nemo:

```sh
nemo --quit
```

The actions use `Conditions=exec nemovcs action-visible inside-worktree ...`
so they only appear for paths inside Git working trees.

## Roadmap

1. Implement the operation actions with robust Git command handling.
2. Add small GTK dialogs only where terminal output is not enough.
3. Add a Nemo plugin for emblems, columns, and dynamic menu behavior.
4. Add `nemovcs-statusd` for cached on-visit status with filesystem invalidation.

