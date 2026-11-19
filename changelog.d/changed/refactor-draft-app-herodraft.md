- Hero draft backend code (models, services, tick driver, WebSocket consumer,
  serializers, views, admin and signals) moved from `app` into the new `draft`
  Django app. The migrations are state-only: tables keep their `app_*` names and
  no schema changes on deploy; the hero draft ContentType rows are relabelled
  from `app` to `draft` so existing admin permissions carry over.
- The team `references` payload key `app.DraftTeam.tournament_team` is now
  `draft.DraftTeam.tournament_team`.
- Hero draft logger names follow the new module paths (for example
  `app.functions.herodraft` is now `draft.services.hero`), and so does the
  OpenTelemetry instrumentation scope on `herodraft.*` spans. Span names and
  `system=`/`subsystem=` log fields are unchanged.
- Hero draft admin pages moved from `/admin/app/herodraft/` to
  `/admin/draft/herodraft/`.
