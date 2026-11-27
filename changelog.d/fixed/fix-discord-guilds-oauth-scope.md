- Discord login now also requests the `guilds` scope, which `/api/discord/user-guilds/` needs to list
  a user's servers; the Discord consent screen asks to share the server list, and existing users get
  the new scope the next time they log in (#990).
