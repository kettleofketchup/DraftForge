Run migrations. `app.0112_widen_steam_account_id` widens the user Friend ID column to
hold every Steam account ID. `app.0113_copy_profile_friend_ids` copies the Friend ID
from each player's Dota 2 and Deadlock profiles onto their account when the account
has none yet. A player whose profiles hold different IDs, or whose ID another account
already holds, is skipped and logged as `steam_friend_id_backfill_skipped` with the
user id and reason (`ambiguous` or `taken`); set those by hand in the admin.
`org.0015_remove_unverified_friend_id` then drops the profile Friend ID column, so
take a database backup first if you want to keep the skipped values. Reversing 0113
is a no-op; reversing 0015 restores an empty column.
