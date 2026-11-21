- The `Organization` and `OrgLog` models moved from `app` into the `org`
  Django app. The migrations are state-only: the tables keep their
  `app_organization`, `app_orglog` and `app_organization_*` names and no
  schema changes on deploy.
- The two ContentType rows are relabelled from `app` to `org`, so the
  permission labels change from `app.*_organization` and `app.*_orglog` to
  `org.*_organization` and `org.*_orglog`. Existing user and group grants
  carry over.
- The cacheops profile key `app.organization` is renamed to
  `org.organization`, with the same profile.
- No admin URL changes, since neither model is registered in admin. No
  logger name, HTTP or WebSocket path, payload or `_meta.label`-derived key
  changes either.
