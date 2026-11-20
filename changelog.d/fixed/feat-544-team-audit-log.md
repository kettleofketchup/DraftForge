- Teams: a team used by bracket games or hero drafts is no longer deleted when its last
  member is removed, which used to delete those games and drafts with it. Saving a team
  with no members is refused for such a team (#544, follow-up to #604).
- Teams: replacing a team's whole roster in one save no longer deletes the team, and a
  save that does delete an unreferenced team no longer fails with a server error (#544).
- Drafts: when a team's captain changes, that team's draft rounds now follow the new
  captain, and a former captain or a stand-in can no longer be drafted onto a second
  team (#544).
