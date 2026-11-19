- Teams: staff and system changes to a tournament team's leadership and roster are now
  recorded in a read-only team audit log (Django admin: Team logs), with who made it,
  from where, the reason and the roster before and after. This covers the team
  management service, the existing team edit (PATCH), and captain successions, kept
  empty teams and team deletions done by the system; it does not cover team creation,
  draft resets or plain member removals done by the system. A team service backs the
  upcoming staff team management tools: change captain or deputy, mark a dropout,
  restore a member, add, remove or sub in a stand-in, and rename, with a reason required
  when acting on another player and a staff override for the stand-in limit and
  eligibility (#544).
- Team drafts: the event feed shows when a team's captain changes mid-draft (#544).
- Team drafts: stand-ins and dropouts can no longer be drafted, undoing a pick refuses
  when the picked player has since been made captain, and rebuilding teams from the
  draft picks refuses once staff have changed a team (#544).
