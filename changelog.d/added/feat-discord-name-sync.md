- Each org membership now stores the member's nickname in that org's Discord server, and
  every user carries their Discord global display name. Org, league, tournament and
  draft payloads include both alongside the username.
- Discord names stay in sync: orgs in use are refreshed from their Discord server every
  30 minutes, an org nobody has used for 3 days is refreshed again the first time
  someone opens its members, and Discord login updates the global name.
- User search matches Discord global names, and org-scoped searches also match that
  org's server nicknames.
