- Team API writes now reject a captain or deputy who is not on the team, and a
  deputy who is also the captain. Approving an account claim keeps the claimed
  account's captaincy on the claimer instead of handing it to another player,
  and an event team can no longer be moved to a different event. A new
  read-only `audit_team_leadership` command lists existing teams with broken
  leadership (#571).
