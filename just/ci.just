# CI entry points (module: ci::). Recipes here run on the bare runner: host bash,
# git and python3 only, no .venv.

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "..")

# Shellcheck every just recipe, rendered with --dry-run, plus the checker's tests (the `shellcheck` CI job); pass namepaths to check only those
[group('ci')]
[positional-arguments]
shellcheck *recipes:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    fail=0
    python3 -I scripts/test_shellcheck_just.py 2>&1 | tail -n 3 || fail=1
    python3 -I scripts/shellcheck_just.py "$@" || fail=1
    exit "$fail"

# Every event: fragment rules (including [Unreleased] holding only the pointer and no
# fragment a release already consumed) and the checker's tests. push to main: HEAD
# must not hand-edit CHANGELOG.md. pull_request: CHANGELOG.md untouched unless
# labelled changelog:edit, and a warning when the PR adds no fragment. Every check
# reports before the recipe exits, so one run shows all problems.
#
# Changelog fragments gate (the `changelog` CI job); locally: fragment checks and the checker's tests
[group('ci')]
changelog-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"
    fail=0
    python3 scripts/changelog.py check || fail=1
    # Fixtures and temp repos only; never the checkout's own CHANGELOG.md.
    python3 scripts/test_changelog.py || fail=1
    # Same pattern as RELEASE_SUBJECT_RE in scripts/changelog.py.
    release_re='^Updated version to [0-9]+\.[0-9]+\.[0-9]+$'
    squash_re='\(#[0-9]+\)$'
    merge_re='^Merge pull request #[0-9]+ from '
    event="${GITHUB_EVENT_NAME:-}"

    if [ "$event" = "push" ]; then
        # Report-only (the commit is already on main), and HEAD~1..HEAD only.
        subject="$(git log -1 --format=%s HEAD)"
        if [[ "$subject" =~ $release_re || "$subject" =~ $squash_re || "$subject" =~ $merge_re ]]; then
            echo "HEAD is a release, squash-merge or merge commit; CHANGELOG.md edit check skipped."
        elif git rev-parse -q --verify HEAD~1 >/dev/null; then
            if ! git cat-file -e HEAD~1:CHANGELOG.md 2>/dev/null; then
                if git cat-file -e HEAD:CHANGELOG.md 2>/dev/null; then
                    echo "::notice::CHANGELOG.md is introduced by this commit; edit check skipped."
                fi
            elif ! git diff --quiet HEAD~1 HEAD -- CHANGELOG.md; then
                echo "::error file=CHANGELOG.md::$(git rev-parse --short HEAD) edits CHANGELOG.md outside a release commit. A backfill note for an already-merged PR #N goes in changelog.d/<section>/pr-<N>.md."
                fail=1
            fi
        fi
        exit "$fail"
    fi

    if [ "$event" != "pull_request" ]; then
        echo "event '${event:-local}': fragment checks and tests only"
        exit "$fail"
    fi

    base="$(scripts/ci-merge-base.sh)" || exit 1
    echo "Comparing $(git rev-parse --short HEAD) against merge base $(git rev-parse --short "$base")"

    if ! git cat-file -e "$base:CHANGELOG.md" 2>/dev/null; then
        echo "::notice::CHANGELOG.md is introduced by this PR; label check skipped."
    elif ! git diff --quiet "$base" HEAD -- CHANGELOG.md; then
        # Read live, not from the frozen event payload, so a re-run sees a label added later.
        rc=0
        python3 scripts/changelog.py has-label changelog:edit || rc=$?
        if [ "$rc" -eq 0 ]; then
            echo "CHANGELOG.md changed; allowed by the changelog:edit label."
        elif [ "$rc" -eq 1 ]; then
            echo "::error file=CHANGELOG.md::This PR edits CHANGELOG.md. Move the new bullets into changelog.d/<section>/<branch-slug>.md (see changelog.d/README.md) and revert the CHANGELOG.md hunk. For a deliberate correction to a released section, add the changelog:edit label, copy CHANGELOG.md to frontend/app/data/CHANGELOG.md, then re-run the failed job (gh run rerun <id> --failed)."
            fail=1
        else
            echo "::error file=CHANGELOG.md::could not read PR labels (exit $rc); re-run the changelog job."
            fail=1
        fi
    fi

    mapfile -d '' -t added < <(git diff -z --name-only --diff-filter=A "$base" HEAD -- 'changelog.d/*/*.md')
    # A fragment at a path a release already removed is reported by `changelog.py check`.
    if [ "${#added[@]}" -eq 0 ]; then
        echo "::warning::This PR adds no changelog.d/ fragment. Fine for chore/CI/test work; anything a user or operator would notice needs one."
    fi
    exit "$fail"

# Test labels for one `Backend tests` CI group: `app`; `migrations` (every
# `test*migration*.py` module outside app); or `rest` (every other module in the other
# top-level packages). Together they cover what an unlabelled `manage.py test` discovers.
[group('ci')]
backend-test-labels group:
    #!/usr/bin/env bash
    set -euo pipefail
    group={{quote(group)}}
    cd {{quote(root)}}/backend
    shopt -s nullglob globstar
    stray=(test*.py)
    if [ "${#stray[@]}" -gt 0 ]; then
        echo "::error::backend/${stray[0]} is outside a package; no backend-test-labels group runs it." >&2
        exit 1
    fi
    # Modules discovery would import: test*.py whose every parent directory is a package.
    modules() {
        local f dir ok
        for f in "$1"/**/test*.py; do
            dir="${f%/*}"; ok=1
            while [ "$dir" != . ] && [ -n "$dir" ]; do
                [ -f "$dir/__init__.py" ] || { ok=0; break; }
                [ "${dir%/*}" = "$dir" ] && break
                dir="${dir%/*}"
            done
            [ "$ok" = 1 ] || continue
            f="${f%.py}"; echo "${f//\//.}"
        done
    }
    is_migration() { [[ "${1##*.}" == test*migration* ]]; }
    case "$group" in
        app) echo app ;;
        migrations|rest)
            labels=()
            for init in */__init__.py; do
                pkg="${init%/__init__.py}"
                [ "$pkg" = app ] && continue
                mods=($(modules "$pkg"))
                mig=() other=()
                for m in "${mods[@]}"; do
                    if is_migration "$m"; then mig+=("$m"); else other+=("$m"); fi
                done
                if [ "$group" = migrations ]; then
                    labels+=("${mig[@]}")
                elif [ "${#mig[@]}" -eq 0 ]; then
                    labels+=("$pkg")
                else
                    labels+=("${other[@]}")
                fi
            done
            echo "${labels[*]}"
            ;;
        *) echo "unknown group: $group (app, migrations or rest)" >&2; exit 2 ;;
    esac
