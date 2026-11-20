- Team draft backend code (the `Draft`, `DraftRound`, `DraftEvent` and
  `DraftOptions` models, team draft services, the shared tick runner, the
  `DraftConsumer` WebSocket consumer, serializers, views, routes and
  permissions) moved from `app` into the `draft` Django app. The migrations
  are state-only: tables keep their `app_*` names and no schema changes on
  deploy. The four team draft ContentType rows are relabelled from `app` to
  `draft`, so their permission codenames now live under the `draft` label and
  existing grants carry over.
- Team draft logger names follow the new module paths: `app.models` (draft
  methods) is now `draft.models.team`, `app.functions.tournament` (draft
  setup) is `draft.views.team_setup`, `app.functions.teamdraft` is
  `draft.services.team`, `app.functions.teamdraft_timeout` is
  `draft.services.team_timeout`, `app.functions.teamdraft_views` is
  `draft.views.team`, `app.functions.draft_picks` is `draft.views.team_picks`,
  `app.broadcast` is `draft.services.team_broadcast`, `app.tasks.draft_tick`
  is `draft.tasks.draft_tick`, `app.tasks.teamdraft_tick` is
  `draft.tasks.team_tick`, `app.consumers` (`DraftConsumer`) is
  `draft.consumers.team` and `app.consumers_base` is `draft.consumers.base`.
  The INFO level overrides in settings moved with them. `system=`/`subsystem=`
  log fields are unchanged.
- The OpenTelemetry instrumentation scopes `app.tasks.draft_tick` and
  `app.consumers_base` are now `draft.tasks.draft_tick` and
  `draft.consumers.base`. Span names are unchanged.
- No HTTP or WebSocket path, payload or `_meta.label`-derived key changes.
