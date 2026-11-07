# CI entry points (module: ci::). Recipes here run on the bare runner: host bash,
# git and python3 only, no .venv.

root := source_directory() / ".."

# Every event: fragment rules and the checker's tests. push to main: HEAD must not
# hand-edit CHANGELOG.md. pull_request: CHANGELOG.md untouched unless labelled
# changelog:edit, no fragment a release already consumed, and a warning when the PR
# adds none.
#
# Changelog fragments gate (the `changelog` CI job); locally, fragment checks only
[group('ci')]
changelog-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"
    python3 scripts/changelog.py check
    python3 scripts/test_changelog.py
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
                exit 1
            fi
        fi
        echo "event 'push': fragment checks only"
        exit 0
    fi

    if [ "$event" != "pull_request" ]; then
        echo "event '${event:-local}': fragment checks only"
        exit 0
    fi

    base="$(scripts/ci-merge-base.sh)" || exit 1
    echo "Comparing $(git rev-parse --short HEAD) against merge base $(git rev-parse --short "$base")"
    fail=0

    if ! git cat-file -e "$base:CHANGELOG.md" 2>/dev/null; then
        echo "::notice::CHANGELOG.md is introduced by this PR; label check skipped."
    elif ! git diff --quiet "$base" HEAD -- CHANGELOG.md; then
        # Read live, not from the frozen event payload, so a re-run sees a label added later.
        rc=0
        python3 scripts/changelog.py has-label changelog:edit || rc=$?
        if [ "$rc" -eq 0 ]; then
            echo "CHANGELOG.md changed; allowed by the changelog:edit label."
        elif [ "$rc" -eq 1 ]; then
            echo "::error file=CHANGELOG.md::This PR edits CHANGELOG.md. Move the new bullets into changelog.d/<section>/<branch-slug>.md (see changelog.d/README.md) and revert the CHANGELOG.md hunk. For a deliberate correction to a released section, add the changelog:edit label, then re-run the failed job (gh run rerun <id> --failed)."
            fail=1
        else
            echo "::error file=CHANGELOG.md::could not read PR labels (exit $rc); re-run the changelog job."
            fail=1
        fi
    fi

    mapfile -d '' -t added < <(git diff -z --name-only --diff-filter=A "$base" HEAD -- 'changelog.d/*/*.md')
    for f in ${added[@]+"${added[@]}"}; do
        hit="$(git log -n 1 --diff-filter=D -E --grep="$release_re" --format='%H %s' "$base" -- "$f")"
        if [ -n "$hit" ]; then
            ver="${hit#* Updated version to }"
            echo "::error file=${f}::${f} was released in ${ver} (${hit:0:9}) and must not come back; delete it. A genuinely new note needs a new slug."
            fail=1
        fi
    done

    if [ "${#added[@]}" -eq 0 ]; then
        echo "::warning::This PR adds no changelog.d/ fragment. Fine for chore/CI/test work; anything a user or operator would notice needs one."
    fi
    exit "$fail"
