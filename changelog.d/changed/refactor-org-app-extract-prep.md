- Organization backend code moved from `app` into the `org` Django app,
  ahead of the model move. `app.permissions_org` is split: org role helpers
  and `IsOrgOwner`/`IsOrgAdmin`/`IsOrgStaff` are now in `org.permissions`,
  and the league, tournament, game and lobby checks stay in `app` as
  `app.permissions_tournament`. `OrganizationView` is now in
  `org.views_organization`, `OrganizationSerializer` in `org.serializers`,
  the organization SSR view in `org.ssr`, the org admin/staff/member
  endpoints in `org.views_admin_team` and the organization signal receivers
  in `org.signals`.
- The `view` field of `drf_error_response` logs for these endpoints now
  reads `org.views_organization.OrganizationView`, `org.views_admin_team.*`
  and `org.ssr.*` instead of `app.views_main.*`, `app.views.admin_team.*`
  and `app.views.ssr.*`. Log queries that filter on it need updating.
- No HTTP path, URL name, payload or model change.
