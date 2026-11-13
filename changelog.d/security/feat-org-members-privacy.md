- An organization's member list (and the MMR it carries) is no longer public:
  `GET /api/organizations/<pk>/users/` now answers only org members and org
  staff, and the Users tab is hidden from everyone else.
- A league's member list follows the same rule: `GET /api/leagues/<pk>/users/`
  answers league staff, the league's own members, and anyone who may see the
  linked org's members. A private org list doesn't hide a league's list from
  that league's members. The league Users tab is hidden from everyone else.
- Event signups no longer show a player's org MMR (`org_user_mmr`) to viewers
  who may not see the org's member list; players still see their own.
