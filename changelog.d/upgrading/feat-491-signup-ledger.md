Migration `events.0026_backfill_signup_line` gives every existing signup a place in line
and a `backfilled` signup record. Signups that the old containers create while migrations
run have no place in line and sort last until the backfill runs again. After the release
stack is recreated, run it once:

```bash
just dev::run 'python manage.py backfill_signup_line'
```

The command is safe to rerun.
