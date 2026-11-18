- A friend ID on either game profile or a linked Steam account now satisfies
  "Require Friend ID" on the web signup, so players with a linked account are no
  longer asked for it again; Dota and Deadlock friend IDs are validated the same
  way on the web and in Discord (#574).
- Saving a Dota profile, by the player or by staff, now refuses an unknown rank
  status, a malformed friend ID or a friend ID another user already holds, with
  a 400 error naming the problem. Resaving the ID already on the profile, or one
  the same person uses in another organization, is still accepted.
