- Tournament changes now reach other open browsers over the tournament WebSocket
  instead of waiting for the next poll (#964): bracket saves, setting or unsetting a
  winner, Steam match link/unlink and hero-draft create/reset send `bracket_update`;
  team creation and management, placements, adding/removing players, CSV import and
  tournament settings send `tournament_update` with the kind of change. Pages refetch
  the affected bracket, tournament and team data.
- A staff member with unsaved bracket edits keeps them when the server bracket changes,
  and sees a notice offering to discard the edits and load the latest bracket.
