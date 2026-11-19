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

# Write frontend/app/lib/opsnotices/noticeTypes.generated.ts from backend/*/ops_notices.py
[group('py')]
gen-notice-types:
    {{quote(python)}} -I {{quote(backend / "opsnotices/export_schema.py")}}

# Exit 1 with a diff when the generated notice types are stale (needs the poetry venv)
[group('py')]
notice-types-check:
    {{quote(python)}} -I {{quote(backend / "opsnotices/export_schema.py")}} --check
# Regenerate frontend/app/lib/notifications/messageTypes.generated.ts from the message registry; --check fails instead of writing when stale
[group('py')]
gen-message-types *args:
    {{quote(python)}} -I {{quote(backend / "notifications/export_schema.py")}} \
        | node {{quote(root / "frontend/scripts/zod-from-json-schema.mjs")}} \
            --out {{quote(root / "frontend/app/lib/notifications/messageTypes.generated.ts")}} "$@"
