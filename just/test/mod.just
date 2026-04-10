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
