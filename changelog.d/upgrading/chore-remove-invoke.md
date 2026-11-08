Invoke is gone: `inv`/`invoke` commands, `tasks.py` and `backend/tasks.py` no longer
exist, and `invoke`, `toml`, `semver` and `alive-progress` are no longer dependencies.
Every task has a `just` recipe of the same name with `::` separators (`inv db.migrate.all`
is `just db::migrate::all`); `just --list --list-submodules` lists them. Run
`poetry install --sync` (or `./dev`) after pulling to drop the removed packages.
Deploys are unchanged: `just dev::release`.

`just` recipes now load `docker/.env.<env>` by sourcing it, so a value in the env file
overrides the same variable already exported in your shell (python-dotenv kept the
shell's value).
