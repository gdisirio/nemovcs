# AGENTS.md

Guidance for coding agents working on NemoVCS.

## Project Identity

NemoVCS is a new project, not a continuation of RabbitVCS internals.

General direction:

- Git and SVN support are both present; keep backend behavior uniform where
  practical.
- Nemo-first because Cinnamon/Nemo is underserved compared with KDE/GNOME.
- Use the nemo-python extension for context-menu operations and live
  integration such as emblems, columns, dynamic menus, or panels.
- Live status is served by a DBus-activated status daemon with cached worktree
  scans, filesystem-monitor invalidation, TTL fallback, and async scan workers.

RabbitVCS can be used as reference material, but do not copy its architecture blindly.

## GitHub Account

Use the user's personal GitHub account for this project:

- GitHub user: `gdisirio`

The machine may also have a `gh` account named `chibios-sheriff`. That account is for AI work related to the ChibiOS organization and should not be used for NemoVCS.

`gh auth status` may appear invalid inside the managed sandbox because it cannot access the keyring/network normally. When verifying GitHub CLI authentication or performing GitHub operations, rerun the necessary `gh` command with escalated permissions.

## Repository

The local repository is:

```text
/home/giovanni/Projects/personal-github/nemovcs
```

Current branch convention:

- Primary branch: `main`

## Design Rules

Keep runtime dependencies minimal:

- Python standard library.
- External `git` executable.
- Nemo/Cinnamon integration files where needed.

Avoid adding Python runtime dependencies unless there is a clear, practical reason.

Prefer shelling out to `git` over using a Git library. Git owns the edge cases.
Prefer shelling out to `svn` for Subversion behavior for the same reason.

Do not block Nemo's UI thread. Nemo plugin code should render cached state and
delegate expensive work to the CLI or status daemon.

Status design:

- Discover repositories from Nemo on-visit callbacks.
- Run an initial VCS status scan per repository root.
- Cache per repository root and path.
- Use filesystem monitoring to invalidate caches.
- Debounce refreshes.
- Use a bounded scan TTL as a fallback for missed filesystem events.
- Run daemon scans off the GLib/DBus main loop.
- Return cached, stale, loading, or error status quickly.

## Development Commands

From the repository root:

```sh
PYTHONPATH=src python3 -m nemovcs --help
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
```

Install locally for development:

```sh
python3 -m pip install -e .
```

Install the Nemo integration for the current user:

```sh
./scripts/install-nemo-extension.sh
./scripts/install-statusd-service.sh
nemo --quit
```

Remove the per-user development install:

```sh
./scripts/uninstall.sh
nemo --quit
```

## Session Handoff

Keep `spec/session-notes.md` updated as durable context for work that moves
between PCs or Codex sessions.

Before pushing changes, update `spec/session-notes.md` with the current focus,
last tested behavior, known issues, and likely next task. This is a project
rule, not optional housekeeping.

## Editing Style

- Keep the initial code small and direct.
- Add tests for Git parsing and command behavior before broadening features.
- Keep legacy Nemo Action cleanup in the installers/uninstaller, but current
  context menus come from the nemo-python extension.
- Keep project naming consistent:
  - project: `NemoVCS`
  - command: `nemovcs`
  - package: `nemovcs`
  - daemon: `nemovcs-statusd`
  - config dir: `~/.config/nemovcs`
  - cache dir: `~/.cache/nemovcs`
