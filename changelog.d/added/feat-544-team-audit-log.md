- Teams: every change to a tournament team's roster or leadership is now recorded in a
  read-only team audit log (Django admin: Team logs), with who made it, from where, the
  reason and the roster before and after. Captain successions, kept empty teams and team
  deletions done by the system are recorded too. A team service backs the upcoming staff
  team management tools: change captain or deputy, mark a dropout, restore a member,
  add, remove or sub in a stand-in, and rename, with a reason required when acting on
  someone else and a staff override for the stand-in limit and eligibility (#544).
- Team drafts: the event feed shows when a team's captain or roster changes mid-draft
  (#544).
