- Move user account, display-name, Steam/Discord identity, social-auth pipeline,
  serializer, payload-cache, profile-update, search, SSR, avatar, internal-client
  and management-command code into `backend/user/`. `is_site_admin` now lives in
  `user.permissions`; `SOCIAL_AUTH_PIPELINE` uses `user.pipelines.*`.
  HTTP paths, payloads and tables are unchanged; this preparation adds no migrations.
- Install `user` deliberately in the Celery worker for serializer model references
  and task autodiscovery, while preserving its original web app registration order.
  Split backend migration tests into `migrations-draft` and `migrations-user` CI groups.
- Rename six Celery tasks: `app.tasks.avatar_refresh.refresh_discord_avatars`,
  `app.tasks.avatar_refresh.refresh_single_user_avatar`,
  `app.tasks.avatar_refresh.refresh_avatars_batched`,
  `app.tasks.avatar_refresh.refresh_all_discord_data`,
  `app.tasks.discord_name_sync.sync_active_org_discord_names` and
  `app.tasks.discord_name_sync.sync_org_discord_names` now use the corresponding
  `user.tasks.*` names. Both beat schedules follow the new names. During deployment,
  new web messages can reach an old worker and queued old names can reach a new
  worker; either direction drops unregistered tasks. After `just dev::release`,
  check worker logs for "unregistered task" naming `sync_org_discord_names` during
  that window and run `manage.py sync_discord_names --org <id>` for each affected
  org. Avatar refreshes and active-org name sync recur on their schedules; inactive
  orgs need the manual recovery.
- Moved modules' logger names now use `user.*`, and moved views' `drf_error_response`
  `view` fields use their new user-module paths. Update logger/view-path filters;
  log `system` and `subsystem` values remain unchanged.
