# Update commands (git, deps, images)

set shell := ["bash", "-euo", "pipefail", "-c"]

root := clean(source_directory() / "..")
just := quote(just_executable()) + " --justfile " + quote(root / "justfile")
# poetry comes from the project venv when it has one.
export PATH := root / ".venv/bin" + ":" + env("PATH")

# git pull, migrate dev, then (when online) npm, poetry and image pulls
[group('update')]
all:
    {{just}} update::git
    {{just}} db::migrate::dev
    if {{just}} update::online; then \
        {{just}} update::npm && {{just}} update::python && {{just}} docker::all-pull; \
    else \
        echo "No internet connection; skipping npm, poetry and image pulls"; \
    fi

# npm and poetry installs when online (used by test::setup)
[group('update')]
all-test:
    if {{just}} update::online; then \
        {{just}} update::npm && {{just}} update::python; \
    else \
        echo "No internet connection; skipping npm and poetry installs"; \
    fi

[group('update')]
git:
    cd {{quote(root)}} && git pull

[group('update')]
npm:
    cd {{quote(root / "frontend")}} && npm install

[group('update')]
python:
    cd {{quote(root)}} && poetry install

[private]
online:
    curl -s --max-time 5 -o /dev/null http://www.google.com
