- Test stacks keep Redis data on a named volume (`<project>_redis_data`) instead of a
  bind mount under the worktree, so a compose run from another worktree no longer
  recreates the test stack's `redis` container and drops its connections.
- Backend test runs (`manage.py test`, pytest) give each process its own Redis
  namespace for channel-layer groups, draft heartbeat/tick keys, the Discord
  rate-limit bucket and cache keys, so concurrent runs no longer receive each other's
  websocket events. Production key names are unchanged.
- Backend test runs no longer flush the Redis DB the running test stack uses for its
  cache and Celery broker, and run Celery tasks eagerly instead of enqueueing them
  onto that broker.
- A bare `python manage.py test` (no labels) discovers the backend tests again instead
  of failing with `No module named 'app.backend'`.
