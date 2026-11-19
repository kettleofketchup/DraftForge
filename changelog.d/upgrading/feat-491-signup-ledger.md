Migration `events.0027_backfill_signup_line` gives every existing signup a place in line
and a `backfilled` signup record. Signups that the old containers create while migrations
run have no place in line and sort last until the backfill runs again. After the release
stack is recreated, run it once in the release stack's backend container:

```bash
docker exec <backend-container> python manage.py backfill_signup_line
```

Use `docker exec`, not `just dev::run` (that starts a container on the dev stack) or
`just db::manage` (it disables the cache, so the command's cached signup flush does nothing).
The command is safe to rerun.
