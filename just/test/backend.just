# Backend tests via pytest on the host (test env)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
pytest := quote(root / "scripts/in-env.sh") + " test backend " + quote(python) + " -m pytest"

# All backend tests
[group('test::backend')]
all *args:
    {{pytest}} -vvv -s -c pytest.ini "$@"

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
