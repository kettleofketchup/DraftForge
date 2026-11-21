- API: the event signup endpoint no longer accepts `profile.unverified_friend_id`, and
  the org Dota 2 profile endpoints read and write `steam_account_id` (the player's
  Friend ID, a number) instead of `unverified_friend_id` (#717).
