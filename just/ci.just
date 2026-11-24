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

# Pull the stack images and the test DB in the background; ci::prefetch-wait joins them (each workflow step is its own shell, so sentinel files, not `wait`)
[group('ci')]
prefetch-start:
    #!/usr/bin/env bash
    set -euo pipefail
    dir="${RUNNER_TEMP:-/tmp}/df-prefetch"
    rm -rf "$dir" && mkdir -p "$dir"
    just={{quote(just_executable())}}
    justfile={{quote(root / "justfile")}}
    for task in images:docker::test-pull db:docker::db::pull; do
        name="${task%%:*}" recipe="${task#*:}"
        # shellcheck disable=SC2016 # expanded by the inner bash
        nohup bash -c '
            start=$SECONDS
            if "$1" --justfile "$2" "$3" > "$4/$5.log" 2>&1; then s=ok; else s=fail; fi
            echo "$((SECONDS - start))" > "$4/$5.$s"
        ' _ "$just" "$justfile" "$recipe" "$dir" "$name" >/dev/null 2>&1 &
        echo "prefetch $name started ($recipe)"
    done

# Wait for a ci::prefetch-start task (images | db), print its log, and exit with its status
[group('ci')]
prefetch-wait name timeout="900":
    #!/usr/bin/env bash
    set -euo pipefail
    dir="${RUNNER_TEMP:-/tmp}/df-prefetch"
    name={{quote(name)}}
    waited=0
    while [[ ! -f "$dir/$name.ok" && ! -f "$dir/$name.fail" ]]; do
        if (( waited >= {{timeout}} )); then
            echo "prefetch $name still running after ${waited}s" >&2
            cat "$dir/$name.log" 2>/dev/null || true
            exit 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    cat "$dir/$name.log" 2>/dev/null || true
    if [[ -f "$dir/$name.ok" ]]; then
        echo "prefetch $name: ok in $(cat "$dir/$name.ok")s (waited ${waited}s here)"
        exit 0
    fi
    echo "prefetch $name: failed after $(cat "$dir/$name.fail")s" >&2
    exit 1

# Boot a docker-container buildx builder unless one is already in use (jobs set up with buildx: 'false')
[group('ci')]
buildx-builder:
    #!/usr/bin/env bash
    set -euo pipefail
    if docker buildx inspect 2>/dev/null | grep -qE '^Driver:\s+docker-container'; then
        exit 0
    fi
    docker buildx create --name df-ci --driver docker-container --use --bootstrap >/dev/null
    echo "buildx builder df-ci ready"

# Build and push, under the content-hash tag only, every Playwright-stack image and the test DB the registry lacks (the Playwright `prepare` job); DF_PREPARE_READONLY=1 only reports. DF_PREPARE_PR=<n> (prepare on the home runner) builds through the home BuildKit and pushes only draftforge-ci/<img>:pr-<n>-<hash>, never a draftforge/ tag. --probe prints `missing=<names>` and builds nothing. Build and push failures warn and exit 0 (test jobs rebuild what is still missing); building on a self-hosted runner outside PR mode is an error.
[group('ci')]
[positional-arguments]
prepare-images *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    start=$SECONDS
    probe=false
    for flag in "$@"; do
        case "$flag" in
            --probe) probe=true ;;
            *) echo "ci::prepare-images: unknown option $flag (use --probe)" >&2; exit 2 ;;
        esac
    done
    just={{quote(just_executable())}}
    justfile={{quote(root / "justfile")}}
    registry=ghcr.io/kettleofketchup/draftforge
    ci_registry=ghcr.io/kettleofketchup/draftforge-ci
    db_registry="${DF_TEST_DB_REGISTRY:-$registry/test-db}"
    pr="${DF_PREPARE_PR-}"
    if [[ -n "$pr" && ! "$pr" =~ ^[0-9]+$ ]]; then
        echo "::error::ci::prepare-images: DF_PREPARE_PR must be a PR number, got '$pr'" >&2
        exit 2
    fi
    # The home runner builds PR code: it may push only draftforge-ci/ tags (PR mode).
    if [[ -z "$pr" && "${RUNNER_ENVIRONMENT-}" == self-hosted ]]; then
        echo "::error::ci::prepare-images: on a self-hosted runner only PR mode (DF_PREPARE_PR=<n>) may build; refusing to push draftforge/ tags" >&2
        exit 1
    fi
    dir=$(mktemp -d)
    trap 'rm -rf "$dir"' EXIT
    # name, service hashed by hash-docker-image.sh, build recipe
    images=(
        "frontend-dev frontend docker::frontend::build-dev"
        "backend-dev backend docker::backend::build-dev"
        "playwright-runner playwright docker::frontend::build-pw"
        "nginx nginx docker::nginx::build"
    )
    declare -A ref ci_ref recipe
    names=()
    for entry in "${images[@]}"; do
        read -r name service build <<< "$entry"
        names+=("$name")
        ref[$name]="$registry/$name:$(./scripts/hash-docker-image.sh "$service")"
        recipe[$name]=$build
    done
    names+=(test-db)
    ref[test-db]="$db_registry:$(./scripts/hash-test-db-sources.sh)"
    if [[ -n "$pr" ]]; then
        for name in "${names[@]}"; do
            ci_ref[$name]="$ci_registry/$name:pr-$pr-${ref[$name]##*:}"
        done
    fi

    # In PR mode an item is present when main's hash tag or this PR's draftforge-ci tag exists.
    for name in "${names[@]}"; do
        (
            if docker buildx imagetools inspect "${ref[$name]}" >/dev/null 2>&1 \
                || { [[ -n "$pr" ]] && docker buildx imagetools inspect "${ci_ref[$name]}" >/dev/null 2>&1; }; then
                touch "$dir/$name.present"
            fi
        ) &
    done
    wait
    missing=()
    for name in "${names[@]}"; do
        [[ -f "$dir/$name.present" ]] || missing+=("$name")
    done
    if [[ "$probe" == true ]]; then
        echo "missing=${missing[*]}"
        exit 0
    fi

    line() { local h="${ref[$1]##*:}"; printf '%-18s %s  %s\n' "$1" "${h:0:12}" "$2" | tee -a "$dir/summary"; }
    readonly_reason=""
    if [[ "${DF_PREPARE_READONLY-}" == 1 ]]; then
        readonly_reason="no registry write access"
    fi
    if [[ -n "$pr" ]]; then
        echo "PR mode: builds push only $ci_registry/<image>:pr-$pr-<hash>" | tee -a "$dir/summary"
    fi

    if [[ ${#missing[@]} -gt 0 && -z "$readonly_reason" ]]; then
        if [[ -n "$pr" ]]; then
            # PR mode builds everything, the test DB included, on the remote home BuildKit.
            "$just" --justfile "$justfile" ci::home-builder
        elif [[ " ${missing[*]} " != " test-db " ]]; then
            "$just" --justfile "$justfile" ci::buildx-builder
        fi
        for name in "${missing[@]}"; do
            (
                t=$SECONDS
                if [[ "$name" == test-db && -n "$pr" ]]; then
                    if python="${DF_JUST_PYTHON:-$("$just" --justfile "$justfile" ci::venv)}" \
                        && DF_JUST_PYTHON="$python" "$just" --justfile "$justfile" docker::db::build --mode=pr --pr="$pr"; then
                        s=ok
                    else
                        s=fail
                    fi
                elif [[ "$name" == test-db ]]; then
                    # Populate runs on the host: DF_JUST_PYTHON must have Django, else ci::venv makes one.
                    if python="${DF_JUST_PYTHON:-$("$just" --justfile "$justfile" ci::venv)}" \
                        && DF_JUST_PYTHON="$python" "$just" --justfile "$justfile" docker::db::build \
                        && "$just" --justfile "$justfile" docker::db::push --hash-only; then
                        s=ok
                    else
                        s=fail
                    fi
                elif [[ -n "$pr" ]]; then
                    if "$just" --justfile "$justfile" "${recipe[$name]}" --mode=pr --pr="$pr"; then
                        s=ok
                    else
                        s=fail
                    fi
                elif "$just" --justfile "$justfile" "${recipe[$name]}" --push --hash-only; then
                    s=ok
                else
                    s=fail
                fi
                echo "$((SECONDS - t))" > "$dir/$name.$s"
            ) > "$dir/$name.log" 2>&1 &
        done
        wait
        for name in "${missing[@]}"; do
            echo "::group::$name build log"
            cat "$dir/$name.log"
            echo "::endgroup::"
        done
    fi

    failed=()
    for name in "${names[@]}"; do
        if [[ -f "$dir/$name.present" ]]; then
            line "$name" present
        elif [[ -n "$readonly_reason" ]]; then
            line "$name" "missing; not built ($readonly_reason)"
        elif [[ -f "$dir/$name.ok" ]]; then
            line "$name" "built+pushed in $(cat "$dir/$name.ok")s"
        else
            line "$name" "build or push failed after $(cat "$dir/$name.fail" 2>/dev/null || echo '?')s"
            failed+=("$name")
        fi
    done
    if [[ -n "$readonly_reason" && ${#missing[@]} -gt 0 ]]; then
        echo "::warning::prepare: ${missing[*]} missing and not built ($readonly_reason); each test job builds them itself"
    fi
    if [[ ${#failed[@]} -gt 0 ]]; then
        hint=""
        for name in "${failed[@]}"; do
            if grep -qiE 'denied|unauthorized|forbidden|403' "$dir/$name.log"; then
                hint=" (registry refused the push: fork PR or no package write access)"
            fi
        done
        echo "::warning::prepare: ${failed[*]} not pushed${hint}; each test job builds them itself"
    fi
    echo "prepare-images: done in $((SECONDS - start))s"
    if [[ -n "${GITHUB_STEP_SUMMARY-}" ]]; then
        { echo '```'; cat "$dir/summary"; echo "done in $((SECONDS - start))s"; echo '```'; } >> "$GITHUB_STEP_SUMMARY"
    fi

# Create or reuse the `home` remote buildx builder (the home cluster's BuildKit) and bootstrap it; the draftforge-home runner has no Docker daemon. Unreachable is an ::error:: and exit 1.
[group('ci')]
home-builder:
    #!/usr/bin/env bash
    set -euo pipefail
    addr="${DF_HOME_BUILDKIT:-tcp://buildkit-0.buildkit.buildkit.svc.cluster.local:1234}"
    docker buildx create --name home --driver remote "$addr" --use >/dev/null 2>&1 || docker buildx use home
    if ! timeout 20 docker buildx inspect --bootstrap home >/dev/null; then
        echo "::error::home BuildKit unreachable; unset the SELF_HOSTED_RUNNERS repo variable so prepare runs on ubuntu-latest"
        exit 1
    fi
    echo "buildx builder home ready"

# Create .venv with Poetry for a job set up with python: 'false' that needs Django on the host (the test-DB populate fallback); prints its python
[group('ci')]
venv:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    if [[ ! -x .venv/bin/python ]]; then
        command -v poetry >/dev/null || pipx install 'poetry==2.2.0' >&2
        POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --no-interaction --no-ansi >&2
    fi
    echo "$PWD/.venv/bin/python"

# Write the Zot cache registry's auth entry (user ci, password from env ZOT_PASSWORD) into
# $DOCKER_CONFIG/config.json (default ~/.docker), keeping every other key. Zot is plain
# HTTP on a ClusterIP and client-side `docker login` assumes HTTPS, so the entry is
# written directly; BuildKit reads it from the client config through the buildx session.
# Prints only the ::add-mask:: line for the encoded value.
[group('ci')]
zot-auth:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "${ZOT_PASSWORD:-}" ]]; then
        echo "::error::ZOT_PASSWORD is empty; not writing a Zot credential" >&2
        exit 1
    fi
    python3 -I - <<'PY'
    import base64, json, os, tempfile
    registry = "zot.zot.svc.cluster.local:5000"
    auth = base64.b64encode(("ci:" + os.environ["ZOT_PASSWORD"]).encode()).decode()
    print("::add-mask::" + auth, flush=True)
    config_dir = os.environ.get("DOCKER_CONFIG") or os.path.expanduser("~/.docker")
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    path = os.path.join(config_dir, "config.json")
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    config.setdefault("auths", {})[registry] = {"auth": auth}
    fd, tmp = tempfile.mkstemp(dir=config_dir, prefix=".config.json.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent="\t")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    PY

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

# Test labels for `Backend tests`: app, migrations-user (org/user migration modules),
# migrations-draft (all other non-app migration modules), rest (remaining modules).
# Together they cover what an unlabelled `manage.py test` discovers.
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
        migrations-draft|migrations-user|rest)
            labels=()
            for init in */__init__.py; do
                pkg="${init%/__init__.py}"
                [ "$pkg" = app ] && continue
                mapfile -t mods < <(modules "$pkg")
                mig=() other=()
                for m in "${mods[@]}"; do
                    if is_migration "$m"; then mig+=("$m"); else other+=("$m"); fi
                done
                if [ "$group" != rest ]; then
                    case "$pkg" in
                        org|user) migration_group=migrations-user ;;
                        *) migration_group=migrations-draft ;;
                    esac
                    if [ "$group" = "$migration_group" ]; then
                        labels+=("${mig[@]}")
                    fi
                elif [ "${#mig[@]}" -eq 0 ]; then
                    labels+=("$pkg")
                else
                    labels+=("${other[@]}")
                fi
            done
            echo "${labels[*]}"
            ;;
        *) echo "unknown group: $group (app, migrations-draft, migrations-user or rest)" >&2; exit 2 ;;
    esac

# Pull queue waits, step and per-command timings, and buildx layer reports for recent runs into .ci-timing/summary.md; e.g. ci::timing --runs 20 --workflows playwright.yml
[group('ci')]
[positional-arguments]
timing *args:
    cd {{quote(root)}} && python3 -I scripts/ci_timing.py "$@"

# Check which jobs may use the draftforge-home runner, plus the checker's tests (the `runs-on-guard` CI job); needs mikefarah yq
[group('ci')]
check-runs-on:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{quote(root)}}
    python3 -I scripts/test_check_runs_on.py
    bash scripts/check-runs-on.sh
