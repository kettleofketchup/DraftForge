- Test stacks keep Redis data on a named volume (`<project>_redis_data`) instead of a
  bind mount under the worktree, so a compose run from another worktree no longer
  recreates the test stack's `redis` container and drops its connections.
- Backend test runs (`manage.py test`, pytest) give each process its own Redis
  namespace for channel-layer groups, draft heartbeat/tick keys and cache keys, so
  concurrent runs no longer receive each other's websocket events. A test run also no
  longer flushes the cache DB the running test stack uses on startup. Production key
  names are unchanged.
