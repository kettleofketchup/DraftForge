# Development environment commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('dev')]
debug:
    {{inv}} dev.debug

[group('dev')]
upd:
    {{inv}} dev.upd

[group('dev')]
up *args:
    {{inv}} dev.up {{args}}

[group('dev')]
down:
    {{inv}} dev.down

[group('dev')]
logs:
    {{inv}} dev.logs

[group('dev')]
ps:
    {{inv}} dev.ps

[group('dev')]
restart:
    {{inv}} dev.restart

[group('dev')]
stop:
    {{inv}} dev.stop

[group('dev')]
build:
    {{inv}} dev.build

[group('dev')]
pull:
    {{inv}} dev.pull

[group('dev')]
top:
    {{inv}} dev.top

[group('dev')]
exec service cmd:
    {{inv}} dev.exec --service {{service}} --cmd '{{cmd}}'

[group('dev')]
run cmd service="backend":
    {{inv}} dev.run --service {{service}} --cmd '{{cmd}}'

[group('dev')]
sync-users:
    {{inv}} dev.sync-users

[group('dev')]
sync-tournaments:
    {{inv}} dev.sync-tournaments

[group('dev')]
sync-all:
    {{inv}} dev.sync-all

[group('dev')]
live:
    {{inv}} dev.live

[group('dev')]
local-prod:
    {{inv}} dev.prod

[group('dev')]
release:
    {{inv}} dev.release

[group('dev')]
mac:
    {{inv}} dev.mac
