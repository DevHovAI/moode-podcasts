# How this project is developed

Short-lived feature branches on a `main` that always works. No `develop`
branch — for a single maintainer the second merge path is pure overhead.

```
issue  →  branch feat/short-name  →  commits  →  just check
   →  push  →  pull request  →  CI green  →  squash merge  →  release
```

## Setup

```sh
just            # list the recipes
just env        # show the interpreter and library versions in use
```

The virtual environment is created automatically on first use, always with
`--system-site-packages`. On an immutable host the GObject bindings come from
the base image and cannot be rebuilt with pip.

## Branches

`feat/…`, `fix/…`, `docs/…`, `refactor/…`, `chore/…`. One branch, one topic.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), English,
imperative mood, no trailing full stop:

```
feat(nexus): read mod dependencies from the API
fix(layout): keep reading legacy sentinel files
```

Prefixes: `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore`
`style` `i18n`. A change that breaks existing behaviour gets `feat!:` or a
`BREAKING CHANGE:` paragraph in the body.

This is not ceremony — the changelog and the version bump are derived from it.
The body answers *why*; the diff already shows *what*.

## Before pushing

```sh
just check      # ruff, syntax, imports, unit tests — the same set the CI runs
just privacy    # must pass; a hit is a stop, not a warning
```

## Pull requests

```sh
gh pr create --fill --base main
gh pr checks --watch
gh pr merge --squash --delete-branch
```

The PR title becomes the squashed commit subject, so write it in Conventional
Commit form.

## Releases

See `references/release.md` in the `repo-flow` skill. In short: bump
`__version__` in `moode_podcasts/__init__.py`, update the changelog, merge, then
tag `vX.Y.Z`. The release workflow does the rest and refuses to run if the
tag and `__version__` disagree.

## What never goes into this repository

Conversation logs, session links, commit trailers, real e-mail addresses,
real names, home directory paths, machine names, hardware details, API keys
or tokens of any kind. `just privacy` checks for all of it.
