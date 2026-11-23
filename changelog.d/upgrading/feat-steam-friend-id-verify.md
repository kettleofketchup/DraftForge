Two migrations run on deploy: `app.0116_customuser_steam_account_verified` adds four
nullable verification columns to users, and `events.0041_eventsignup_self_made` adds
`EventSignup.self_made` (default `False`, with a database default so containers still on
the old image can insert signups during the deploy). Neither backfills anything.

Every existing Friend ID starts unverified and not checked against Steam. Every existing
signup starts with `self_made=False`, because earlier releases did not record who made a
signup, so event and league staff can verify those members only after the members sign
up to one of their events themselves. Site staff can verify anyone straight away.

The Steam existence check uses `STEAM_API_KEY`. Without it the check fails open: IDs are
saved and shown as "Not checked against Steam". Set `STEAM_ACCOUNT_LOOKUP_ENABLED=false`
to turn the check off; it defaults to on, and to off in the test stack.
