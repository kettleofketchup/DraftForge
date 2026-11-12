- An organization's member list (and the MMR it carries) is no longer public:
  `GET /api/organizations/<pk>/users/` now answers only org members and org
  staff, and the Users tab is hidden from everyone else.
