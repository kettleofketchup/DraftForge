Migrations `org.0013`, `org.0014` and `org.0015` move org MMR to one row per game:
every non-zero `OrgUser.mmr` is copied to the Dota 2 org MMR, then the `OrgUser.mmr`
column is dropped. Values outside 0–20000 are copied as they are, and the migration
prints a `WARNING: N OrgUser mmr values outside 0..20000 copied verbatim` line with
their OrgUser ids. Fix or
clear those values from the organization Users tab after the deploy; the edit form
shows an error on such a field until it is fixed.

This release must be deployed stop-first. `just dev::release` migrates before it pulls
images and recreates containers, and the old containers fail on every org member query
once the column is gone. From the repo root on the release host, after `git pull`:

```bash
just docker::release::pull
scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release down
just dev::release
```

The site is down from the second command until the third finishes (seconds of
migration plus container start).

During the deploy, a browser still running the old page gets a 400 "mmr requires
mmr_game_type; reload the page" when it saves an org MMR. Reloading the page fixes it.

Rollback (Deadlock org MMR values are lost; Dota 2 values are restored to
`OrgUser.mmr`):

1. Stop the release stack:
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release down`
2. From this release's checkout (migrations run from the host), run
   `just db::manage release migrate org 0012`.
3. Remove the old version's cached keys so the old image cannot serve pre-upgrade
   member data. Start only Redis and delete the keys, replacing `0.15.0` with the
   version you are going back to:
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release up -d redis`, then
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release exec -T redis sh -c "redis-cli --scan --pattern 'dtx-v0.15.0:*' | xargs -r redis-cli unlink"`.
   Alternatively, start the old version with a new `DEPLOY_VERSION` in
   `docker/.env.release` so it reads an empty cache prefix.
4. Check out the old version and run `just dev::release`.
