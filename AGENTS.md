# AGENTS.md

Guidance for coding agents working on NemoVCS.

## Project Identity

NemoVCS is a new project, not a continuation of RabbitVCS internals.

General direction:

- Git-only initially.
- Nemo-first because Cinnamon/Nemo is underserved compared with KDE/GNOME.
- Use Nemo Actions first for easy installation and context-menu operations.
- Add a Nemo plugin later for live integration such as emblems, columns, dynamic menus, or panels.
- Add a status daemon later only when cached live status is needed.

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

Do not block Nemo's UI thread. Future Nemo plugin code should render cached state and delegate expensive work to the CLI or a daemon.

Future status design:

- Discover repositories from Nemo on-visit callbacks.
- Run an initial Git status scan per repository root.
- Cache per repository root and path.
- Use filesystem monitoring to invalidate caches.
- Debounce refreshes.
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

Install Nemo action files for the current user:

```sh
./scripts/install-actions.sh
nemo --quit
```

## Editing Style

- Keep the initial code small and direct.
- Add tests for Git parsing and command behavior before broadening features.
- Keep Nemo Actions as thin integration glue.
- Keep project naming consistent:
  - project: `NemoVCS`
  - command: `nemovcs`
  - package: `nemovcs`
  - future daemon: `nemovcs-statusd`
  - config dir: `~/.config/nemovcs`
  - cache dir: `~/.cache/nemovcs`

