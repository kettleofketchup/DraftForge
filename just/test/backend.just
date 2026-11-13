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
    cd {{quote(root / "backend")}} && {{pytest}} -vvv app/tests/test_shuffle_draft*.py -c pytest.ini "$@"
