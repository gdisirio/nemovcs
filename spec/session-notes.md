# NemoVCS Session Notes

Purpose: keep short durable context for moving work between PCs and Codex
sessions. Update this file before pushing changes.

## Current Focus

- Source-tree testing, performance hardening, and metadata cleanup for NemoVCS
  0.3.0 after milestone 3.
- Nemo Action installer removal: current context menus are provided by the
  nemo-python extension; legacy action cleanup remains in install/uninstall.

## Last Known State

- `main` was updated to `origin/main` at milestone 3.
- Per-user Nemo extension install was refreshed with
  `./scripts/install-nemo-extension.sh`.
- Nemo and `nemovcs statusd` were restarted after the update.
- Tests passed with:
  `PYTHONPATH=src python3 -m unittest discover -s tests`
  and `python3 -m compileall -q src tests scripts`.
- Opening large directories is more responsive after changing statusd `Seen()`
  handling so fresh, already-scanned worktrees are not rescanned for every
  visible file.
- Statusd now has a persisted `scan_ttl_seconds` setting, defaulting to 15
  seconds, so missed filesystem monitor invalidations become bounded staleness
  instead of permanent staleness.
- Live DBus validation with `scan_ttl_seconds=1` confirmed a nested tracked file
  edit remains cached immediately after save and reports `modified` after TTL
  expiry. The user's previous live settings were restored afterward:
  `max_worktrees=16`, `debounce_seconds=0.75`, `scan_ttl_seconds=15`.
- Status scans now run off the DBus/GLib main loop in the live daemon. Initial
  DBus status for an unscanned worktree can return `loading`; completion is
  applied back on the GLib main loop and emits `StatusChanged`.
- Live DBus validation confirmed initial async scan behavior (`loading` then
  `ok`) and TTL-triggered async behavior (`ok` cached immediately after TTL
  request, then `modified` after the worker completed). Live settings were
  restored to `max_worktrees=16`, `debounce_seconds=0.75`,
  `scan_ttl_seconds=15`.
- Metadata/docs were refreshed after the status daemon hardening: `pyproject`
  now describes Git and SVN integration and alpha status, README documents
  cache TTL/async scan behavior, and `AGENTS.md` no longer describes SVN or the
  daemon as future work.
- After moving around SVN repositories, Nemo became unresponsive while a live
  `svn status --xml` process was visible. The likely cause was not the async
  scan worker itself, but repeated synchronous SVN worktree identification:
  `Seen()` and `GetStatus()` still called `identify_worktree()` for every child
  path, which runs `svn info --show-item wc-root` for SVN paths.
- Statusd now reuses cached worktree identities for child paths already under a
  known cached root, while still forcing a fresh probe when a nested `.git` or
  `.svn` marker is present. `SvnBackend.run()` also converts command timeouts
  into failed results instead of raising `TimeoutExpired`.

## Recent Changes To Keep In Mind

- `Rename...` is available for single Git/SVN selections.
- `Settings...` opens a GTK settings panel for status daemon status/cache
  inspection and settings.
- Status daemon settings are stored under `~/.config/nemovcs/settings.json`.
- Unversioned Git/SVN leaf files should show the unversioned emblem.
- SVN parent folders should not become dirty only because they contain
  unversioned descendants.
- `scripts/install-actions.sh`, `scripts/install-layout.py`, and
  `tests/test_install_layout.py` were removed as obsolete.
- `scripts/install-nemo-extension.py` now prunes legacy NemoVCS action files,
  the old `nemovcs-icons` action directory, and Nemo action layout entries.
- `SvnBackend.run()` now reports a failed result when the `svn` executable is
  missing instead of raising `FileNotFoundError`; this keeps Git-only menu
  detection working on systems without Subversion installed.
- `git.run_git()` now mirrors that behavior for missing `git`, so SVN-only
  menu detection is not broken by Git absence.
- Ignored Git files are now distinguished from clean tracked files internally.
  Example: `chibios_tools/tools/chibiscope/chibiscope` is ignored by
  `tools/chibiscope/.gitignore`, so it should not receive the clean/green
  emblem; the parent directory remains unversioned when it has no tracked
  descendants.
- Experimental `Nemo.LocationWidgetProvider` support adds a compact repository
  context bar above the current directory listing with backend, active
  branch/head, aggregate status, and repository root name.
- The repository context bar now supports a compact/expanded toggle and uses a
  thin bottom separator to keep it visually distinct from Nemo's file list
  headers.
- Future repository context bar refinement: for Git expanded view, prefer a
  remote URL over the local worktree path. Rule: use the current branch
  upstream remote URL when available, otherwise `origin` remote URL when
  available, otherwise fall back to the local worktree path. Compact view can
  remain branch/status/root-name oriented.
- Future context bar action refinement: allow selected/pinnable context-menu
  actions to appear as icon-only buttons on the right side of the compact bar,
  before the expand button. Keep the first-line repository summary short and
  left-aligned. Selection-dependent actions should remain in the context menu
  until Nemo selection tracking is available.
- Status daemon `Seen()` now scans only when a worktree is unscanned, stale, or
  in error. This removes repeated full `git status --porcelain=v2 -z -uall` and
  `git ls-files -z` scans while Nemo enumerates many files in the same
  worktree. The known tradeoff is that freshness now depends more directly on
  filesystem monitor invalidation, explicit refresh, daemon restart, or cache
  eviction.
- TTL-based revalidation extends that rule: `Seen()` also rescans when the
  cached worktree scan age reaches `scan_ttl_seconds`. Setting the value to `0`
  disables age-based rescans.
- The DBus daemon uses a thread-backed scan scheduler. Core tests still use the
  synchronous default unless a scheduler is injected. Async scan results are
  copied back to the cached worktree entry only if that entry is still present
  in the cache.

## Next Likely Tasks

- Continue manual testing from Nemo on real Git and SVN working trees after
  reinstalling the extension and restarting Nemo.
- Decide whether the repository context bar is useful enough to keep, and tune
  its visual density/placement if it feels intrusive.
- Add Git upstream/origin remote URL data to status records for the expanded
  repository context bar.
- Future branch switch dialog refinement: differentiate local and remote
  branches. Keep the fast context submenu local-only; make `Others...` show
  local and remote sections/tabs, with remote branches creating or selecting a
  local tracking branch explicitly. The full dialog is also the right place for
  branch management actions such as create-and-switch, rename, and delete.
- Watch for stale status daemon cache behavior after file changes, VCS
  operations, daemon restarts, and missed filesystem monitor events. TTL now
  bounds missed invalidations, but scans still run synchronously in the daemon
  GLib main loop.
- Watch Nemo behavior around first-time `loading` status. Async scans now emit
  `StatusChanged` after `Seen()`-triggered scans so visible items should be
  invalidated and re-read after completion.
- Consider adding a lightweight visible diagnostic for scan reason and duration
  before more performance tuning.
- Review CLI command help text for remaining Git-specific wording where commands
  now route through backend abstractions.
- Continue stress testing SVN navigation in Nemo. Watch for remaining
  synchronous paths in context-menu construction, especially backend detection
  for uncached SVN roots.
- Validate `Rename...` behavior for both Git and SVN files/directories.
- Validate the settings panel against a live DBus-activated status daemon.
