Migration `org.0018` drops the `OrgUser.mmr` column. Org MMR has been stored one row
per game since 0.17.0, whose `org.0015` and `org.0016` copied every non-zero
`OrgUser.mmr` to the Dota 2 org MMR and kept the column in sync; nothing is copied
in this release.

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

Rollback (per-game org MMR rows, including Deadlock, are kept; `OrgUser.mmr` is
refilled from the Dota 2 values):

1. Stop the release stack:
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release down`
2. From this release's checkout (migrations run from the host), run
   `just db::manage release migrate org 0017_retarget_default_league_to_league`.
3. Remove the old version's cached keys so the old image cannot serve pre-upgrade
   member data. Start only Redis and delete the keys, replacing `0.17.0` with the
   version you are going back to:
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release up -d redis`, then
   `scripts/in-env.sh release . .venv/bin/python -m scripts.slots --root . compose --stack release exec -T redis sh -c "redis-cli --scan --pattern 'dtx-v0.17.0:*' | xargs -r redis-cli unlink"`.
   Alternatively, start the old version with a new `DEPLOY_VERSION` in
   `docker/.env.release` so it reads an empty cache prefix.
4. Check out the old version and run `just dev::release`.
