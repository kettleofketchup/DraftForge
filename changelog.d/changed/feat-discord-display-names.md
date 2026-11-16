- Users are shown by their Discord names everywhere. On org, league, tournament and
  draft pages a member shows as their nickname in that org's Discord server, then their
  Discord display name, then their username; elsewhere as their Discord display name,
  then their username. A user with none of these shows as "User <id>".
- User search no longer matches site nicknames; it matches usernames, Discord display
  names and, in an org, that org's server nicknames.
- A profile is complete once it has a Steam ID and a linked Discord account; a nickname
  is no longer required for profile-complete events.
- CSV user import ignores the `name` column. The template no longer includes it, and
  files that still have it import as before with that column marked ignored.
