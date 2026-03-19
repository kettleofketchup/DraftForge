# Python/Django commands

root := source_directory() / ".."
backend := root / "backend"
py := ". " + root / ".venv/bin/activate && cd " + backend + " && python"

[group('py')]
manage *args:
    {{py}} manage.py {{args}}

[group('py')]
migrate *args:
    DISABLE_CACHE=true {{py}} manage.py migrate {{args}}

[group('py')]
makemigrations *args:
    {{py}} manage.py makemigrations {{args}}

[group('py')]
shell:
    DISABLE_CACHE=true {{py}} manage.py shell

[group('py')]
runserver *args:
    {{py}} manage.py runserver {{args}}

[group('py')]
run *args:
    {{py}} {{args}}

# Run a Python script with Django configured (auto-sets DJANGO_SETTINGS_MODULE, DISABLE_CACHE, PYTHONPATH)
[group('py')]
script *args:
    . {{root}}/.venv/bin/activate && cd {{backend}} && PYTHONPATH={{backend}} DJANGO_SETTINGS_MODULE=backend.settings DISABLE_CACHE=true python {{args}}

[group('py')]
test *args:
    DISABLE_CACHE=true {{py}} -m pytest {{args}}
