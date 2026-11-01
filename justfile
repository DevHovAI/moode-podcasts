# moode-podcasts — local checks.
#
# Everything runs in .venv, built with --system-site-packages (Pillow from
# the host is used for the cover tests if it is there).
#
# After an rpm-ostree update that moves Python to a new minor version:
#   just rebuild

set shell := ["bash", "-euo", "pipefail", "-c"]

root  := justfile_directory()
venv  := root / ".venv"
py    := venv / "bin" / "python"
ruff  := venv / "bin" / "ruff"
stamp := venv / ".requirements-stamp"

# List the recipes
default:
    @just --list --unsorted

# --- environment ----------------------------------------------------------

[private]
_venv:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -x "{{py}}" ]; then
        echo "creating .venv (--system-site-packages)"
        /usr/bin/python3 -m venv --system-site-packages "{{venv}}"
        "{{py}}" -m pip install --quiet --upgrade pip
    fi
    if [ ! -f "{{stamp}}" ] || [ requirements-dev.txt -nt "{{stamp}}" ]; then
        "{{py}}" -m pip install --quiet -r requirements-dev.txt
        touch "{{stamp}}"
    fi

# Throw the venv away and build it again
rebuild:
    rm -rf "{{venv}}"
    @just _venv
    @just env

# Show what is actually running here
env: _venv
    @"{{py}}" -c 'import sys; print("python    ", sys.version.split()[0], sys.executable)'
    @"{{ruff}}" --version

# --- checks ---------------------------------------------------------------

# Everything the CI runs. Do this before every push.
check: lint fmt-check compile imports test
    @echo
    @echo "all green"

# Rules only
lint: _venv
    "{{ruff}}" check .

# Formatting check
fmt-check: _venv
    "{{ruff}}" format --check --diff .

# Deliberately WITHOUT `ruff format`: over a grown codebase that produces a
# diff that makes git blame useless. Use `just reformat` for that, once.
#
# Fix what can be fixed automatically
fix: _venv
    "{{ruff}}" check --fix .

# Commit this on its own, then put the commit hash into
# .git-blame-ignore-revs.
#
# One-off reformat of the whole tree
reformat: _venv
    "{{ruff}}" format .
    "{{ruff}}" check --fix .

# Syntax check across every file
compile: _venv
    "{{py}}" -m compileall -q moode_podcasts tools

# Catches circular imports and typos at module level that no test reaches.
#
# Every module imports cleanly
imports: _venv
    #!/usr/bin/env bash
    set -euo pipefail
    "{{py}}" - <<'PY'
    import importlib, pathlib, sys
    failed, seen = [], 0
    roots = [pathlib.Path("moode_podcasts")] + sorted(
        p for p in pathlib.Path("moode_podcasts").iterdir() if p.is_dir() and (p / "__init__.py").exists())
    for root in roots:
        for path in sorted(root.glob("*.py")):
            name = ".".join(path.with_suffix("").parts)
            if name.endswith("__main__"):
                continue
            seen += 1
            try:
                importlib.import_module(name)
            except Exception as exc:
                print("FAIL", name, type(exc).__name__, exc)
                failed.append(name)
    print(f"{seen - len(failed)} modules imported, {len(failed)} failed")
    sys.exit(1 if failed else 0)
    PY

# --- tests ----------------------------------------------------------------

# Unit tests. Touch neither the network nor the real database.
test *ARGS: _venv
    "{{py}}" -m pytest {{ARGS}}

# --- running --------------------------------------------------------------

# Run from the checkout (e.g. `just run serve --port 8090`)
run *ARGS: _venv
    "{{py}}" -m moode_podcasts {{ARGS}}

# --- housekeeping ---------------------------------------------------------

# The single source of truth for the version
version:
    @grep -oP '__version__ = "\K[^"]+' moode_podcasts/__init__.py

# What happened since the last tag — the same view the release uses
changelog:
    #!/usr/bin/env bash
    set -euo pipefail
    last="$(git describe --tags --abbrev=0 2>/dev/null || true)"
    echo "since ${last:-the beginning}:"
    git log --no-merges --format='  %s' "${last:+$last..}HEAD"

# Privacy check — must pass before every push
privacy *ARGS:
    bash ~/.claude/skills/repo-flow/scripts/privacy-scan.sh {{ARGS}}

# Rebuild the recommendation list from the iTunes directory (network!)
recommendations: _venv
    "{{py}}" tools/build_recommendations.py

# Copy the checkout to a moOde device and install it there: just deploy pi@moode
deploy TARGET:
    ./deploy/push.sh {{TARGET}}

clean:
    find . -name __pycache__ -type d -prune -exec rm -rf {} +
    find . -name '*.pyc' -delete
    rm -rf .pytest_cache .ruff_cache

# --- unattended queue -----------------------------------------------------

# Runs until the queue is empty, waiting out usage limits. Watch it with
# `tmux attach -t runner`, stop it with `just queue-stop`.
#
# Work the labelled issues unattended
queue *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    if tmux has-session -t runner 2>/dev/null; then
        echo "A runner session already exists. Attach with: tmux attach -t runner"
        exit 1
    fi
    tmux new-session -d -s runner \
        "systemd-inhibit --what=idle:sleep --who=queue-runner --why='working the issue queue' \
         queue-runner.sh run {{ARGS}}; echo; echo '--- finished, press a key ---'; read -r -n1"
    echo "Started. Watch it with:  tmux attach -t runner   (leave again with Ctrl-b d)"

# What is queued, running, or waiting for you
queue-status:
    @queue-runner.sh status

# Only the checks, start nothing
queue-check:
    @queue-runner.sh preflight

# Finish the current issue, then stop
queue-stop:
    @queue-runner.sh stop
