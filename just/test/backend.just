# Backend tests via pytest on the host (test env, cache off)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "../..")
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
pytest := quote(root / "scripts/in-env.sh") + " test backend env DISABLE_CACHE=true " + quote(python) + " -m pytest"

# All backend tests on a fresh backend/test.db.sqlite3
[group('test::backend')]
all *args:
    rm -f {{quote(root / "backend/test.db.sqlite3")}}
    touch {{quote(root / "backend/test.db.sqlite3")}}
    {{pytest}} -vvv -s -c pytest.ini "$@"

[group('test::backend')]
steam *args:
    {{pytest}} -vvv steam/tests/ -c pytest.ini "$@"

[group('test::backend')]
draft *args:
    cd {{quote(root / "backend")}} && {{pytest}} -vvv app/tests/test_shuffle_draft*.py -c pytest.ini "$@"
