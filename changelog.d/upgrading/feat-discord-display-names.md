This release stops reading and writing site nicknames; the database columns stay until a
later release drops them. No migration needs to run by hand.

Rolling back to the previous release is a plain redeploy, but users who signed up while
this release was live have no site nickname, and the previous release rejects them for
profile-complete events. After rolling back, run the one-off backfill from the pull
request description once in the backend container.
