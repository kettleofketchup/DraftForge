# Production environment commands

root := source_directory() / ".."
inv := ". " + root / ".venv/bin/activate && cd " + root + " && inv"

[group('prod')]
up:
    {{inv}} prod.up

[group('prod')]
upd:
    {{inv}} prod.upd

[group('prod')]
down:
    {{inv}} prod.down

[group('prod')]
logs:
    {{inv}} prod.logs

[group('prod')]
ps:
    {{inv}} prod.ps

[group('prod')]
restart:
    {{inv}} prod.restart

[group('prod')]
stop:
    {{inv}} prod.stop

[group('prod')]
build:
    {{inv}} prod.build

[group('prod')]
pull:
    {{inv}} prod.pull

[group('prod')]
top:
    {{inv}} prod.top

[group('prod')]
exec service cmd:
    {{inv}} prod.exec --service {{service}} --cmd '{{cmd}}'

[group('prod')]
run cmd service="backend":
    {{inv}} prod.run --service {{service}} --cmd '{{cmd}}'

[group('prod')]
certbot:
    {{inv}} prod.certbot
