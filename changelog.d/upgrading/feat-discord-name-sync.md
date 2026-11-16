After deploying, backfill Discord names once from the backend container:

```bash
docker exec <backend-container> python manage.py sync_discord_names --all
```

Run it with `docker exec`, not `just py::shell` or `py::script`: the command refuses to
run when the cache is disabled (`DISABLE_CACHE`), since cached payloads would keep the
old names. Use `--org <id>` to sync a single org.

Rolling back is a plain redeploy of the previous image.
