- Start Draft and Restart Draft now reset each team to its captain in place
  instead of deleting and recreating it. When games or other records use the
  teams, staff get a second confirmation, and referenced teams are never
  deleted. The success message says how many teams were reset, dropped or left
  out of the draft (#572).
- `POST /tournaments/draft-rebuild` on a draft with no rounds yet resets teams
  the same way: besides cutting each roster to its captain it clears the deputy,
  drop-in and left members, league entries, points and placement.
