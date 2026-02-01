# Test environment commands

root := source_directory() / "../.."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

mod pw 'pw.just'
mod backend 'backend.just'
mod cicd 'cicd.just'
mod demo 'demo.just'

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
    {{inv}} test.setup
