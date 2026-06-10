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

Avoid runtime Python dependencies in v1.

GTK, PyGObject, DBus, watchdog libraries, Dulwich, GitPython, and similar
dependencies are out of scope for v1.

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

Purpose: show unstaged diff for selected paths.

Syntax:

```text
nemovcs diff PATH...
```

Expected Git command:

```text
git -C REPO diff -- PATH...
```

v1 output can be terminal text.

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

NemoVCS should present different menu items depending on the repository type.
Git is the only operation backend for v1, but repository detection should leave
room for SVN and other VCS types later.

Examples:

- Git worktree: show Git actions.
- SVN working copy: do not show Git actions.
- Unknown or unsupported path: show no repository actions.

Some high-frequency commands may appear at the first context-menu level. Other
commands should appear under a `NemoVCS` submenu to avoid clutter.

v1 default placement:

- first level: status, diff, commit
- `NemoVCS` submenu: log and future lower-frequency actions

The first-level versus submenu placement should be modeled as action metadata,
not hard-coded deep inside command handlers. User-configurable placement is a
v2 feature.

Actions should use:

```text
Dependencies=git;nemovcs;
UriScheme=file
Conditions=exec nemovcs action-visible inside-worktree ...
```

Visibility should be contextual:

- Selected-file actions should only appear when selected paths are inside a Git
  worktree.
- Background folder actions should only appear when the current folder is inside
  a Git worktree.

v1 actions can use `Terminal=true`.

## Error Handling

v1 should prefer clear terminal errors over complex dialogs.

Examples:

- Git executable missing.
- Path is not inside a Git worktree.
- Git command timed out.
- Git command failed.

Commands should avoid Python tracebacks for expected user-facing errors.

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
- Add dynamic menus if Nemo Actions become too limited.
- Keep Nemo UI callbacks fast.

The plugin should not run expensive Git commands directly on the UI path.

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
- Nemo Action files install for the current user.
- Nemo shows the actions only inside Git worktrees.
- Existing unit tests pass.
