Run migrations: `org.0021_api_tokens` adds the API token, daily usage and per-org limit
tables. The per-minute limit uses the Redis cache; if Redis is unreachable the minute limit
is skipped (logged as `org_api_rate_cache_unavailable`) while the daily limit still applies.
