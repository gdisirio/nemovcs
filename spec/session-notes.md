# NemoVCS Session Notes

Purpose: keep short durable context for moving work between PCs and Codex
sessions. Update this file before pushing changes.

## Current Focus

- Source-tree testing of NemoVCS 0.3.0 after milestone 3.
- Continue validating Nemo context menus, status emblems, status daemon
  refresh behavior, and Git/SVN dialog workflows.

## Last Known State

- `main` was updated to `origin/main` at milestone 3.
- Per-user Nemo extension install was refreshed with
  `./scripts/install-nemo-extension.sh`.
- Nemo and `nemovcs statusd` were restarted after the update.
- Tests passed with:
  `PYTHONPATH=src python3 -m unittest discover -s tests`
  and `python3 -m compileall -q src tests scripts`.

## Recent Changes To Keep In Mind

- `Rename...` is available for single Git/SVN selections.
- `Settings...` opens a GTK settings panel for status daemon status/cache
  inspection and settings.
- Status daemon settings are stored under `~/.config/nemovcs/settings.json`.
- Unversioned Git/SVN leaf files should show the unversioned emblem.
- SVN parent folders should not become dirty only because they contain
  unversioned descendants.

## Next Likely Tasks

- Continue manual testing from Nemo on real Git and SVN working trees.
- Watch for stale status daemon cache behavior after file changes, VCS
  operations, and daemon restarts.
- Validate `Rename...` behavior for both Git and SVN files/directories.
- Validate the settings panel against a live DBus-activated status daemon.
