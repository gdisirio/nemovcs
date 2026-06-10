# NemoVCS Spec v1

## Purpose

NemoVCS provides Git integration for the Nemo file manager.

The project exists because Nemo/Cinnamon has less maintained VCS integration
than KDE Dolphin and GNOME-oriented workflows. NemoVCS should be small,
predictable, and maintainable rather than a broad RabbitVCS-compatible clone.

## Goals

- Provide useful Git operations from Nemo context menus.
- Keep the first implementation dependency-light.
- Use the system `git` executable as the Git backend.
- Allow RabbitVCS to remain installed while NemoVCS is developed and tested.
- Establish a clean foundation for future status emblems, columns, and cached
  repository status.

## Non-Goals for v1

- No SVN, Mercurial, Bazaar, or other VCS operation backend.
- No Nautilus, Caja, Thunar, PCManFM-Qt, or Dolphin integration.
- No live status emblems.
- No custom Nemo columns.
- No embedded Nemo panel.
- No background status daemon.
- No DBus API.
- No user-facing menu placement configuration.
- No attempt to preserve RabbitVCS APIs, settings, or UI behavior.

## Supported Platform

Initial platform:

- Linux desktop.
- Nemo file manager.
- Git installed and available in `PATH`.
- Python 3.10 or newer.

NemoVCS should not assume a specific distribution, but Linux Mint/Cinnamon is
the primary target environment.

## Distribution Model

v1 uses two pieces:

- Python package providing the `nemovcs` command.
- Nemo Action files that call the command.

The action files are installed for a user into:

```text
~/.local/share/nemo/actions
```

or, when `$XDG_DATA_HOME` is set:

```text
$XDG_DATA_HOME/nemo/actions
```

System-wide packaging can install equivalent files under the system Nemo action
directory later.

## Runtime Dependencies

Required:

- Python standard library.
- External `git` executable.

Recommended external tools:

- Meld for visual diffs.

Avoid runtime Python dependencies in v1.

GTK, PyGObject, DBus, watchdog libraries, Dulwich, GitPython, and similar
dependencies are out of scope for v1.

## Git Backend Strategy

NemoVCS uses the system `git` executable rather than a Python Git library.
This keeps behavior aligned with users' configured Git, including credentials,
hooks, signing, filters, worktrees, submodules, and distribution packaging.

NemoVCS should distinguish between:

- user-facing command output, which can be streamed mostly as Git produces it,
- machine-readable repository state, which should use stable Git formats.

RabbitVCS is useful reference material, but its Git support often presents raw
Git text while its Subversion support is more polished. NemoVCS should avoid
copying that limitation for Git status and metadata features.

For repository state used by menus, emblems, property pages, and future cached
status, prefer documented machine formats:

- `git status --porcelain=v2 -z`
- `git diff --name-status -z`
- explicit `git log --format=...` formats
- focused probes such as `git rev-parse`, `git branch --show-current`, and
  `git remote get-url`

Parsing ad hoc human output should be avoided. Normal Git text output remains
acceptable for early terminal-backed operations and for the future GUI logger
when the output is meant for the user to read directly.

## Command Line Interface

The CLI command is:

```text
nemovcs
```

The CLI must be useful both from Nemo Actions and from a terminal.

### Common Rules

- Paths can be files or directories.
- Relative paths are resolved against the current working directory.
- If a file path is selected, Git commands run from the nearest suitable parent.
- Commands may receive multiple paths.
- Paths from different repositories are grouped by repository root.
- Commands should write normal output to stdout and errors to stderr.
- Nonzero exit codes from Git should propagate as command failure where
  practical.
- Git commands must use argument arrays, not shell interpolation.

### `nemovcs action-visible`

Purpose: decide whether a Nemo Action should be visible.

Syntax:

```text
nemovcs action-visible inside-worktree PATH...
```

Behavior:

- Exit `0` only when all provided paths are inside Git working trees.
- Exit nonzero otherwise.
- Must be fast because Nemo may call this while building menus.
- Must not run `git status`.

Expected Git probe:

```text
git -C PATH rev-parse --is-inside-work-tree
```

### `nemovcs status`

Purpose: show Git status for selected paths.

Syntax:

```text
nemovcs status PATH...
```

Expected Git command:

```text
git -C REPO status --short --branch -- PATH...
```

v1 output can be terminal text.

### `nemovcs diff`

Purpose: show unstaged diff for selected paths using Meld.

Syntax:

```text
nemovcs diff PATH...
```

Expected Git command:

```text
git -C REPO difftool --tool=meld --dir-diff --no-prompt -- PATH...
```

NemoVCS should use Meld for visual diffs instead of building its own diff UI.
If Meld is not installed, the Nemo Action should be hidden through action
dependencies and the CLI should report a clear error.

### `nemovcs log`

Purpose: show commit history affecting selected paths.

Syntax:

```text
nemovcs log [-n LIMIT] PATH...
```

Expected Git command:

```text
git -C REPO log --oneline --decorate -nLIMIT -- PATH...
```

Default limit: `50`.

### `nemovcs commit`

Purpose: stage selected paths and create a commit.

Syntax:

```text
nemovcs commit [-m MESSAGE] PATH...
```

Behavior:

- Group selected paths by repository.
- Run `git add -- PATH...` for each repository group.
- Run `git commit`.
- If `-m MESSAGE` is provided, pass it to Git.
- Without `-m`, Git should open the user's configured editor.

This command is intentionally basic in v1. A GUI commit dialog is a future
feature, not required for the first milestone.

## Future Commit And Staging Dialog

The commit/staging dialog is one of the most important GUI surfaces for the full
tool. RabbitVCS can be used as a practical reference because its commit window
was functional, but NemoVCS should aim for a cleaner workflow closer to the best
parts of tools such as TortoiseSVN.

Core responsibilities:

- Provide two primary work areas: a commit message editor and a changed-file
  checklist.
- Discover changed, untracked, deleted, renamed, and conflicted files for the
  selected repository or selected paths.
- Present the discovered files as a flat list in the initial dialog.
- Allow including or excluding each file through checkboxes.
- Make it clear whether a checked file will be staged, committed, or both.
- Support selecting all, selecting none, and toggling common groups such as
  modified, added, deleted, untracked, and conflicted.
- Show file status, path, and optionally staged/unstaged indicators.
- Open the selected file diff in Meld.
- Open the selected file in the file manager or default editor where useful.
- Give the commit message editor enough vertical space for real messages, not
  just a single-line entry.
- Keep the commit message visible while the user reviews and toggles files.
- Prevent committing with an empty selection or empty message unless Git allows
  the requested mode explicitly.
- Show command progress and results through the GUI logger.

Git state model:

- Use `git status --porcelain=v2 -z` as the primary input.
- Preserve the distinction between staged and unstaged changes.
- Let users stage only the checked paths before committing.
- Avoid hidden broad staging operations such as `git add .`.
- Treat untracked files as opt-in, not automatically included.
- Surface conflicts clearly and avoid committing conflicted paths.
- Keep the status data model independent from the file-list presentation, so a
  hierarchical display can be added later without changing Git parsing.

Partial hunk staging is out of scope for the first GUI commit dialog. It can be
evaluated later, likely by delegating to Git's interactive patch mode or a
purpose-built patch UI.

### `nemovcs update`

Purpose: update the current Git repository.

Syntax:

```text
nemovcs update PATH...
```

Expected Git command:

```text
git -C REPO pull --ff-only
```

Behavior:

- Group selected paths by repository.
- Run one update command per repository root.
- Treat update as a repository operation, not a path-limited operation.
- Prefer fast-forward-only updates in the early prototype to avoid opening
  merge conflict workflows before the GUI layer exists.

This command is intentionally basic in v1. More complete pull/fetch/rebase
policy belongs in settings and later GUI flows.

## Nemo Actions

v1 action files live in:

```text
data/nemo/actions
```

Initial actions:

- selected path status
- background folder status
- selected path diff
- selected path log
- selected path commit
- selected path update
- background folder update
- settings placeholder
- about placeholder

NemoVCS should present different menu items depending on the repository type.
Git is the only operation backend for v1, but repository detection should leave
room for SVN and other VCS types later.

Examples:

- Git worktree: show Git actions.
- SVN working copy: do not show Git actions.
- Unknown or unsupported path: show no repository actions.

Some high-frequency commands may appear at the first context-menu level. Other
commands should appear under a `NemoVCS` submenu to avoid clutter.

current v1 default placement:

- first level: commit, update
- `NemoVCS` submenu: status, diff, log, settings, about

The first-level versus submenu placement should be modeled as action metadata,
not hard-coded deep inside command handlers. User-configurable placement is a
v2 feature.

Actions should use:

```text
Dependencies=git;nemovcs;
UriScheme=file
Conditions=exec nemovcs action-visible inside-worktree ...
```

Actions that require an external helper can add it to `Dependencies`. For
example, `Diff...` depends on `meld`.

Visibility should be contextual:

- Selected-file actions should only appear when selected paths are inside a Git
  worktree.
- Background folder actions should only appear when the current folder is inside
  a Git worktree.

v1 actions can use `Terminal=true`.

Menu items that open a terminal or future dialog should use an ellipsis in their
label. The early prototype uses temporary RabbitVCS icons stored under
`rsc/icons/rabbitvcs`; these assets must be replaced or license-cleared before a
proper release.

## Error Handling

v1 should prefer clear terminal errors over complex dialogs.

Examples:

- Git executable missing.
- Path is not inside a Git worktree.
- Git command timed out.
- Git command failed.

Commands should avoid Python tracebacks for expected user-facing errors.

## Future GUI Output Logger

The terminal pause wrapper is acceptable for early testing, but the full tool
needs a graphical output/log window similar in spirit to RabbitVCS'
notification/logger windows.

Expected responsibilities:

- Show command title, repository root, and selected paths.
- Stream stdout and stderr from Git commands.
- Preserve the exact command output for troubleshooting.
- Show parsed command results when structured data is available.
- Show exit status and elapsed time.
- Keep output visible after completion.
- Allow copying output to clipboard.
- Allow saving output to a file.
- Support canceling long-running commands where possible.
- Present errors in a user-readable way without Python tracebacks.
- Support multiple command phases, such as `git add` followed by `git commit`.

Initial tab model:

- `Summary`: structured, command-specific results when available, such as
  changed files, branch movement, ahead/behind state, or commit result.
- `Output`: raw stdout and stderr from Git and NemoVCS helper steps.

If a command does not yet have structured parsing, `Summary` can show a compact
completion state and direct the user to `Output` for details. The raw output tab
should always be available because it is the most useful troubleshooting view
and preserves exactly what Git reported.

The logger should be reusable by Nemo Actions, future plugin actions, and any
standalone repository browser.

The logger should not be required for v1. It is the planned replacement for
`nemovcs run-terminal` once the operation flow is proven.

## Prototype Checkpoint

The current prototype has demonstrated:

- contextual Nemo Action visibility inside Git working trees,
- native Nemo submenu layout with `Commit...` and `Update...` at top level,
- terminal-backed `status`, `log`, `commit`, and `update` commands,
- Meld-backed `diff` command,
- temporary icons on installed menu items,
- pause-on-exit terminal behavior for early testing.

This does not close v1. The next major gap is replacing terminal output with a
small GUI logger and adding better error presentation.

## Timeouts

Short Git probes should use a short timeout.

Longer user-initiated operations may use longer timeouts:

- status/diff/log: short to moderate timeout
- commit: long timeout because the editor may remain open

Exact timeout values can evolve with testing.

## Future Nemo Plugin

A Nemo plugin is not part of v1, but the architecture should allow it.

Expected plugin responsibilities:

- Implement `Nemo.InfoProvider.update_file_info()` for on-visit status.
- Add emblems for visible files/folders.
- Add optional columns.
- Add a repository-related property page in Nemo's file properties dialog.
- Add dynamic menus if Nemo Actions become too limited.
- Keep Nemo UI callbacks fast.

The plugin should not run expensive Git commands directly on the UI path.

## Future Property Page

A Nemo property page is not part of v1, but it is a required feature for the
full tool.

Expected provider:

```text
Nemo.PropertyPageProvider
```

The page should appear only for paths inside supported working copies.

Initial Git information:

- VCS type.
- Repository root.
- Current branch.
- HEAD commit.
- Upstream branch.
- Ahead/behind counts when available.
- Selected path relative to repository root.
- Selected path status summary.
- Remote URLs.

The property page should use cached status data when a status daemon exists.
Before then, it should run only cheap Git commands and avoid blocking Nemo's UI.

## Future Repository Browser

A repository browser is required after the core action workflow is usable.

There are two plausible designs:

- Standalone NemoVCS browser application.
- Repository content exposed to Nemo as browsable files/directories.

The standalone browser is the preferred first implementation. RabbitVCS has a
standalone GTK SVN browser that can be used as reference material, but it should
not be copied wholesale: it is SVN-focused and tied to RabbitVCS internals.

Using Nemo itself as the browser is an open research item. A normal Nemo
extension can add menus, emblems, columns, and property pages, but it does not
by itself provide a new filesystem. To make Nemo browse repository content that
is not already present in the working tree, NemoVCS would likely need one of:

- a GVfs backend or custom URI/mount integration,
- a FUSE filesystem,
- a temporary materialized checkout/tree view,
- or a simpler action that opens local working-tree paths in Nemo.

For Git, the standalone browser should initially support:

- browse tracked files at a revision,
- choose branch/tag/commit,
- open or export a file,
- compare selected revision/path with working tree when applicable.

For SVN, a future backend could provide remote repository browsing similar to
RabbitVCS' browser.

## Future Status Daemon

A status daemon is not part of v1.

Expected daemon name:

```text
nemovcs-statusd
```

Expected direction:

- Discover repositories from Nemo on-visit events.
- Run one initial status scan per repository root.
- Cache status by repository root and relative path.
- Return cached, stale, loading, or error states quickly.
- Watch worktree and `.git` changes.
- Debounce refreshes.
- Refresh once per burst of filesystem events.
- Notify the Nemo plugin so visible items can invalidate and repaint.

The daemon should avoid continuous polling and should not scan arbitrary home
directories.

## Ideas Under Evaluation

This section is for ideas that may be useful later but are not committed product
direction yet.

### Repository Metadata Filesystem

A narrower VFS/FUSE idea is to expose repository metadata only, not repository
file contents.

This would let Nemo browse Git concepts as ordinary directories while avoiding
most of the complexity of presenting every file at every revision.

Possible read-only layout:

```text
NemoVCS/
  repositories/
    project-name/
      branches/
      tags/
      remotes/
      stashes/
      commits/
      worktrees/
      submodules/
```

Each leaf could expose small text or desktop files with useful metadata:

- branch name, upstream, ahead/behind counts,
- tag name, target object, annotation,
- remote name and URLs,
- stash subject and commit IDs,
- recent commit summaries,
- linked worktree paths,
- submodule paths and status.

This metadata filesystem would be read-only initially. It should be considered
a browser/navigation aid, not a way to perform Git operations by editing files.

Compared with exposing complete repository snapshots, metadata-only VFS has a
smaller surface:

- fewer path encoding and file content edge cases,
- less pressure to implement full POSIX semantics,
- easier caching,
- lower risk of confusing users about write behavior.

Open questions:

- FUSE mount versus GVfs backend.
- Whether metadata entries should be text files, desktop files, or directories.
- How to discover repositories.
- How to avoid stale mounts.
- How this interacts with the future status daemon cache.

### Hierarchical Commit File View

The first commit/staging dialog should use a flat changed-file list. A
hierarchical tree view is worth evaluating later for repositories with many
changed files spread across several directories.

Possible behavior:

- Display changed paths grouped by directory.
- Allow expanding and collapsing directory rows.
- Let checking a directory toggle all visible changed children.
- Show per-directory counts such as modified, added, deleted, untracked, and
  conflicted.
- Keep file-level actions such as Meld diff on leaf rows.
- Preserve checked state when switching between flat and hierarchical views.

Implementation notes:

- GTK3 can represent this with `Gtk.TreeStore` and `Gtk.TreeView`.
- A true mixed/indeterminate checkbox state for directory rows may require a
  custom cell renderer or a secondary status indicator.
- The underlying Git status model should remain flat and path-based; the tree
  should be a display projection only.

### Optional AI Assistance

AI integration is a future concept, not part of v1 and not required for normal
VCS operations.

Possible uses:

- Suggest commit messages from selected staged changes.
- Summarize a diff or a group of changed files.
- Explain merge conflicts in user-facing language.
- Suggest conflict resolution options while leaving final edits to the user.
- Summarize update/pull results and likely next actions.
- Help classify large change sets before commit.

Guardrails:

- AI features must be explicitly opt-in.
- NemoVCS must remain fully usable without network access or AI services.
- Repository content must not be sent to external services without clear user
  consent.
- Suggested commit messages and conflict resolutions are advisory only.
- The user must review and apply any generated text or code changes.
- AI integration must not add mandatory runtime dependencies to the core tool.

Open questions:

- Local model support versus external API integration.
- Configuration and credential storage.
- How to show exactly which files, diffs, or conflict hunks would be shared.
- Whether AI features belong in the commit dialog, logger, conflict helper, or a
  separate assistant window.

## Compatibility with RabbitVCS

NemoVCS should coexist with RabbitVCS during development.

Avoid using RabbitVCS names for:

- Python packages.
- commands.
- DBus names.
- config directories.
- cache directories.
- icon names.

## Naming

Canonical names:

- Project: `NemoVCS`
- Command: `nemovcs`
- Python package: `nemovcs`
- Future daemon: `nemovcs-statusd`
- Config directory: `~/.config/nemovcs`
- Cache directory: `~/.cache/nemovcs`

## First Milestone Acceptance Criteria

The first milestone is complete when:

- `nemovcs --help` works.
- `nemovcs action-visible inside-worktree PATH` works.
- `nemovcs status PATH` works inside a Git repo.
- `nemovcs diff PATH` works inside a Git repo.
- `nemovcs log PATH` works inside a Git repo.
- `nemovcs update PATH` works inside a Git repo.
- `nemovcs commit PATH` works inside a Git repo.
- Nemo Action files install for the current user.
- Nemo shows the actions only inside Git worktrees.
- Nemo shows the expected top-level items and `NemoVCS` submenu.
- Existing unit tests pass.
