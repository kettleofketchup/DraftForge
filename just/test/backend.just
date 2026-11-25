# Backend tests: the full suite in this worktree's test stack (as CI runs it), or focused pytest on the host

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
pytest := quote(root / "scripts/in-env.sh") + " test backend " + quote(python) + " -m pytest"

# Full suite as CI runs it: manage.py test --parallel auto in this slot's stack, one ci::backend-test-labels group at a time; args go to manage.py test
[group('test::backend')]
all *args:
    #!/usr/bin/env bash
    set -euo pipefail
    {{just}} test::upd
    # One group at a time: all four at once oversubscribes the CPU and measured slower.
    summary=() fail=0 start=$SECONDS
    procs=()
    if [[ "${GITHUB_ACTIONS-}" != true && -z "${CI-}" ]]; then
        procs=(-e "DJANGO_TEST_PROCESSES=${DJANGO_TEST_PROCESSES:-6}")
    fi
    run() {
        local name=$1 t=$SECONDS status=pass
        shift
        echo "==> $name"
        {{just}} test::compose exec -T "${procs[@]}" backend python manage.py "$@" || { status=FAIL; fail=1; }
        summary+=("$(printf '%-17s %-4s %4ss' "$name" "$status" $((SECONDS - t)))")
    }
    run makemigrations makemigrations --check --dry-run
    for group in app migrations-draft migrations-user rest; do
        labels=$({{just}} ci::backend-test-labels "$group")
        # No labels would make `manage.py test` run everything, so skip the group as CI does
        [[ -n "$labels" ]] || { summary+=("$(printf '%-17s skip' "$group")"); continue; }
        # shellcheck disable=SC2086 # one label per word
        run "$group" test -v 2 --parallel auto $labels "$@"
    done
    echo
    printf '%s\n' "${summary[@]}" "total $((SECONDS - start))s"
    exit "$fail"

# Focused pytest on the host with docker/.env.test loaded (needs Redis on localhost:6379): just test::backend::pytest app/tests/test_x.py -k name
[group('test::backend')]
pytest *args:
    {{pytest}} -c pytest.ini "$@"

[group('test::backend')]
steam *args:
    {{pytest}} -vvv steam/tests/ -c pytest.ini "$@"

[group('test::backend')]
draft *args:
    cd {{quote(root / "backend")}} && {{pytest}} -vvv draft/tests/test_team_shuffle*.py -c pytest.ini "$@"
