# Test environment commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

mod pw 'pw.just'
mod backend 'backend.just'
mod cicd 'cicd.just'
mod demo 'demo.just'
mod populate 'populate.just'

[group('test')]
up:
    {{inv}} test.up

[group('test')]
upd:
    {{inv}} test.upd

[group('test')]
down:
    {{inv}} test.down

[group('test')]
logs:
    {{inv}} test.logs

[group('test')]
ps:
    {{inv}} test.ps

[group('test')]
restart:
    {{inv}} test.restart

[group('test')]
stop:
    {{inv}} test.stop

[group('test')]
build:
    {{inv}} test.build

[group('test')]
pull:
    {{inv}} test.pull

[group('test')]
top:
    {{inv}} test.top

[group('test')]
exec service cmd:
    {{inv}} test.exec --service {{service}} --cmd '{{cmd}}'

[group('test')]
run cmd service="backend":
    {{inv}} test.run --service {{service}} --cmd '{{cmd}}'

[group('test')]
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    # If worktree, ensure backend/.env is copied from main repo
    main_repo="$(git -C "{{root}}" rev-parse --git-common-dir 2>/dev/null | sed 's|/\.git$||')"
    if [[ -n "$main_repo" && "$main_repo" != "{{root}}/.git" && "$main_repo" != "." ]]; then
        if [[ -f "$main_repo/backend/.env" && ! -f "{{root}}/backend/.env" ]]; then
            echo "Worktree detected — copying backend/.env from main repo..."
            cp "$main_repo/backend/.env" "{{root}}/backend/.env"
        fi
    fi
    {{inv}} test.setup

slots_py := "cd " + quote(root) + " && " + quote(root / ".venv/bin/python") + " -m scripts.slots --root " + quote(root)

# Allocate (or re-adopt) this worktree's test slot and print it
[group('test')]
slot:
    {{slots_py}} print

# Show every slot reservation and df* project (read-only)
[group('test')]
slots:
    {{slots_py}} status

# Release this worktree's slot, or another idle one with --slot N
[group('test')]
slot-release *args:
    {{slots_py}} release {{args}}

# Move this worktree to slot N
[group('test')]
slot-claim n:
    {{slots_py}} claim {{n}}

# Tear down an orphaned df* project whose worktree is gone
[group('test')]
slot-reap project:
    {{slots_py}} reap {{project}}

# Turn the Discord bot and celery beat on or off for this slot
[group('test')]
background state:
    {{slots_py}} background {{state}}

# Run docker compose against this worktree's slot (--stack S, --as-slot 0 for config)
[group('test')]
[positional-arguments]
compose *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{root}}"
    exec "{{root}}/.venv/bin/python" -m scripts.slots --root "{{root}}" compose "$@"

# Slot helper unit tests (no containers)
[group('test')]
slots-unit *args:
    cd {{quote(root)}} && {{quote(root / ".venv/bin/python")}} -m pytest -p no:django -p no:cacheprovider scripts/slot_tests -q {{args}}
