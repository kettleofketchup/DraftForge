# Python/Django commands (run in backend/ with the project venv)

set shell := ["bash", "-euo", "pipefail", "-c"]
set positional-arguments

root := clean(source_directory() / "..")
backend := root / "backend"
python := env("DF_JUST_PYTHON", root / ".venv/bin/python")
py := "cd " + quote(backend) + " && " + quote(python)
nocache := "cd " + quote(backend) + " && DISABLE_CACHE=true " + quote(python)

[group('py')]
manage *args:
    {{py}} manage.py "$@"

[group('py')]
migrate *args:
    {{nocache}} manage.py migrate "$@"

[group('py')]
makemigrations *args:
    {{py}} manage.py makemigrations "$@"

[group('py')]
shell:
    {{nocache}} manage.py shell

[group('py')]
runserver *args:
    {{py}} manage.py runserver "$@"

[group('py')]
run *args:
    {{py}} "$@"

# Run a Python script with Django configured (auto-sets DJANGO_SETTINGS_MODULE, DISABLE_CACHE, PYTHONPATH)
[group('py')]
script *args:
    cd {{quote(backend)}} && PYTHONPATH={{quote(backend)}} DJANGO_SETTINGS_MODULE=backend.settings DISABLE_CACHE=true {{quote(python)}} "$@"

# pytest on the host with docker/.env.test loaded and the cache on, as in the test container
[group('py')]
test *args:
    {{quote(root / "scripts/in-env.sh")}} test backend {{quote(python)}} -m pytest "$@"
