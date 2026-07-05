# NemoVCS Session Notes

Purpose: keep short durable context for moving work between PCs and Codex
sessions. Update this file before pushing changes.

## Current Focus

- Source-tree testing, performance hardening, and metadata cleanup for NemoVCS
  0.3.0 after milestone 3.
- Nemo Action installer removal: current context menus are provided by the
  nemo-python extension; legacy action cleanup remains in install/uninstall.
- Current performance focus: keep Nemo extension callbacks from triggering
  repeated synchronous status work during directory enumeration and keep DBus
  failures visible instead of silently masking unexpected problems.

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
- First-visit hang investigation with Nemo launched under GDB showed Nemo's
  main thread blocked in a synchronous DBus call from nemo-python during
  `extension_info_start`, while `nemovcs statusd` was busy. The live GDB log
  also showed heavy child process churn during the freeze.
- Statusd now ignores duplicate `Seen()` scan requests while a worktree scan is
  already in flight or already scheduled. This prevents visible item
  enumeration from turning the initial async scan into a rescan/invalidate/query
  loop. Live testing after reinstall showed Nemo and `statusd` settling at 0%
  CPU, and the user confirmed the immediate hang was gone.
- Status lookup protocol was hardened after the hang fix. Nemo now uses one
  DBus `QueryStatus(paths)` call instead of separate `Seen()` and `GetStatus()`
  calls; the old methods remain for compatibility/debugging. DBus client calls
  use a hidden persisted `dbus_timeout_seconds` setting in
  `~/.config/nemovcs/settings.json` (currently `1` second, not exposed in the
  settings UI yet). A live `status-cache --dbus` probe against the restarted
  daemon returned the repo status successfully, and Nemo/statusd settled at 0%
  CPU afterward.
- Unexpected status/protocol failures now surface as a dedicated "problems"
  visual state. Internally this remains `status="error"`; visually it maps to
  the new `nemovcs-problems` emblem. Non-worktree "not versioned" errors remain
  quiet. The client validates daemon status records and synthesizes a problem
  record only when local marker detection indicates a real Git/SVN worktree.

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
- Repository context bar top line is unified for collapsed and expanded modes.
  Git shows icon, backend, remote/source, and branch/head in parentheses. SVN
  shows icon, backend, and remote/source without a head suffix because the
  branch path is usually encoded in the URL. `git.remote_url()` uses the current
  branch upstream remote URL when available, otherwise `origin`, otherwise None
  so the view falls back to the worktree path after scanning. SVN scans now
  populate `remote_url` from `svn info --show-item url`. While a first async
  scan is still `loading` and no remote is known yet, the top line shows
  `loading source...` instead of briefly showing the local worktree as if it
  were the final source.
- The context bar now updates the active GTK widget when statusd emits
  `StatusChanged`; it tracks location widget handles, recomputes the spec, and
  updates source text, tooltip, and detail rows. It also has a bounded loading
  retry that bypasses the client cache to cover the race where the initial scan
  signal arrives before the widget handle is registered. Expand/collapse no
  longer rewrites source text, preventing stale creation-time `loading` specs
  from overwriting a refreshed remote URL. Live testing showed the bar now
  refreshes without changing directories.
- Expanded context bar detail values are single-line, selectable, ellipsized at
  the end, and carry the full value in their tooltip so long URLs and paths do
  not stretch the Nemo window.
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
- The daemon self-terminates when the Nemo file manager exits. `run_foreground`
  watches `NameOwnerChanged` for `org.Nemo`; when that name loses its owner
  (`nemo_name_lost`), it quits. DBus re-activates a fresh daemon (from source)
  on the next status request, so a Nemo restart transparently picks up code
  changes with no manual daemon kill. `nemo-desktop` owns `org.NemoDesktop`,
  not `org.Nemo`, so it does not keep a stale daemon alive. Verified live: a
  `nemo --quit` shuts the daemon down on its own.
- Structured revision log backend (first step toward a proper Log dialog to
  replace the text dump). `LogEntry`/`LogChange`/`BackendLog` live in
  `backends/base.py`; `backends.scan_log(path, limit)` detects the backend/root
  and returns entries. Git parses `git log --name-status` with a control-char
  pretty format (`parse_git_log`, `parse_git_name_status` in `backends/git.py`);
  SVN parses `svn log --xml --verbose` (`parse_svn_log` in `backends/svn.py`).
  Parsers are pure and unit-tested; the Git format was verified live against
  this repo.
- The Log dialog (`ui/log_dialog.py`) is now a revision browser: a revision
  `TreeView` (revision/author/date/summary) over a vertical split, with the
  selected revision's message on the left and its changed paths on the right.
  `cmd_log_dialog` uses it instead of the text `logger`. Double-click a revision
  for a whole-commit Meld diff, or a changed path for a per-file diff (Git only
  for now). "Show more" grows the limit and reloads; real backend paging is a
  follow-up. Row/label/date/diff logic is factored into pure module functions
  and unit-tested; the window itself was smoke-tested live against this repo.
  `update`/`push` still use the text `logger`.
- `SvnBackend.root()` now short-circuits via a filesystem `.svn` ancestor check
  (`has_svn_metadata_ancestor`) before running `svn info`. Backend detection
  runs on Nemo's UI thread during context-menu construction, so this avoids one
  `svn` subprocess per selected path for the common case of Git trees and plain
  folders. Genuine SVN working copies always have a `.svn` root, so detection is
  unchanged for them.
- Removed the dead `git.commit_paths()` helper and its test. Commits route
  through the backend commit path (`GitBackend.commit`/`commit_phases`); the
  helper had no production callers.
- Statusd monitor callbacks suppress scan-induced Git `index*` and SVN
  `wc.db*` metadata events during a scan and briefly after it completes. Those
  events are expected side effects of status probes and should not immediately
  mark the same worktree stale again.
- The Log dialog can filter revision history by the selected paths, so opening
  it on a file or subdirectory shows relevant history instead of always showing
  whole-repository history.
- Git Log dialog path-filtered history now matches SVN behavior more closely:
  selected paths filter which revisions are listed, but each listed Git
  revision shows the full set of files changed in that revision.
- The Log dialog changed-files context menu has `Diff with previous...`,
  `Diff with current...`, a separator, and `Save as...`. Git file-level
  `Diff with current...` handles added files with `/dev/null` on the left and
  deleted/missing files by materializing revision content to a temporary file
  and comparing it to `/dev/null`; deletion commits read content from
  `revision~1:path`. `Save as...` exports the selected revision content and
  also uses `revision~1:path` for deleted entries.
- Log dialog context menus now show icons: both diff actions use the NemoVCS
  diff icon, `Save as...` uses the themed `document-save-as-symbolic` icon, and
  the changed-files list shows system file icons in the Path column with a
  generic fallback for missing/deleted paths.
- New icon resources: `emblem-nemovcs-problems.svg` and
  `emblem-nemovcs-problems-small.svg`. Installer/uninstaller and the statusd
  settings cache view know about the new problem emblem.

## Next Likely Tasks

- Log dialog follow-ups: implement real backend paging for "Show more"
  (`--skip` for Git, revision-range for SVN) instead of re-fetching a larger
  limit; add per-revision diff/save support for SVN (currently Git-only, others
  show an info message); optionally add status icons to the changed-paths
  column and author/date sorting niceties.

- Continue manual testing from Nemo on real Git and SVN working trees after
  reinstalling the extension and restarting Nemo.
- Decide whether the repository context bar is useful enough to keep, and tune
  its visual density/placement if it feels intrusive.
- Validate the expanded context bar remote URL against live Git worktrees:
  upstream-configured branch, origin-only, and no-remote repositories, plus SVN
  (which should still show the worktree path).
- Future branch switch dialog refinement: differentiate local and remote
  branches. Keep the fast context submenu local-only; make `Others...` show
  local and remote sections/tabs, with remote branches creating or selecting a
  local tracking branch explicitly. The full dialog is also the right place for
  branch management actions such as create-and-switch, rename, and delete.
- Watch for stale status daemon cache behavior after file changes, VCS
  operations, daemon restarts, and missed filesystem monitor events. TTL now
  bounds missed invalidations, and scans run off the GLib main loop so they no
  longer block DBus handlers, monitor callbacks, or the settings UI.
- Watch Nemo behavior around first-time `loading` status. Async scans now emit
  `StatusChanged` after `Seen()`-triggered scans so visible items should be
  invalidated and re-read after completion.
- Continue stress testing repeated enter/leave navigation in versioned
  directories. The first-visit hang fix passed one live check, but more manual
  testing on real Git and SVN trees is still useful.
- Continue watching the context bar live refresh path. Current implementation
  tracks location widget handles and removes them on widget destroy; if Nemo
  creates many transient widgets, consider switching the handle list to weak
  references or adding additional pruning.
- Keep an eye on DBus timeout behavior. The current policy intentionally shows
  the problem emblem for unexpected DBus/protocol failures instead of falling
  back to cached status, because cached fallback could hide real integration
  problems.
- Consider adding a lightweight visible diagnostic for scan reason and duration
  before more performance tuning.
- Review CLI command help text for remaining Git-specific wording where commands
  now route through backend abstractions.
- CLI help text was refreshed so backend-routed commands describe VCS status,
  diff, log, update, and push instead of Git-only behavior. The branch switch
  command remains Git-specific.
- Continue stress testing SVN navigation in Nemo. The `.svn` ancestor
  pre-check removes the `svn info` subprocess from context-menu construction in
  non-SVN trees; watch for remaining synchronous paths, including Git's
  `git rev-parse`-based detection, if menus still feel slow.
- Validate `Rename...` behavior for both Git and SVN files/directories.
- Validate the settings panel against a live DBus-activated status daemon.
