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
    # One group at a time: each already uses every core (--parallel auto), so running the
    # four at once oversubscribes the CPU and measured slower than this, not faster.
    summary=() fail=0 start=$SECONDS
    run() {
        local name=$1 t=$SECONDS status=pass
        shift
        echo "==> $name"
        {{just}} test::compose exec -T backend python manage.py "$@" || { status=FAIL; fail=1; }
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

# Promotion-sync race tests on a throwaway local PostgreSQL container (test-only; production stays on SQLite)
[group('test::backend')]
pg-race *args:
    #!/usr/bin/env bash
    set -euo pipefail
    image="postgres:16-alpine"
    name="df-pgtest-$$"
    password="df-pgtest-synthetic"
    driver="${XDG_CACHE_HOME:-$HOME/.cache}/draftforge/pgtest-driver"
    if [[ ! -d "$driver/psycopg" ]]; then
        uv pip install --quiet --python {{quote(python)}} --target "$driver" 'psycopg[binary]==3.2.10'
    fi
    docker run -d --rm --name "$name" -e POSTGRES_USER=df_pgtest \
        -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=df_pgtest \
        -p 127.0.0.1::5432 "$image" >/dev/null
    trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
    for _ in $(seq 1 60); do
        if docker exec "$name" pg_isready -U df_pgtest -d df_pgtest -h 127.0.0.1 >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    port="$(docker port "$name" 5432/tcp | head -n1 | sed 's/.*://')"
    labels=("$@")
    if [[ ${#labels[@]} -eq 0 ]]; then
        labels=(org.tests.test_promotion_sync_races)
    fi
    cd {{quote(root / "backend")}}
    DISABLE_CACHE=true \
    DJANGO_SETTINGS_MODULE=backend.settings_pgtest \
    DF_PGTEST_DSN="postgresql://df_pgtest:${password}@127.0.0.1:${port}/df_pgtest" \
    PYTHONPATH="$driver${PYTHONPATH:+:$PYTHONPATH}" \
        {{quote(python)}} manage.py test "${labels[@]}" -v 2
