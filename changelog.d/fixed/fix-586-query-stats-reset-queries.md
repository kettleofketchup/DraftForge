- Backend tests that count queries with `assertNumQueries` or `CaptureQueriesContext`
  now see every query across test-client requests; the query stats middleware no longer
  clears the query log at the start of each request (#586).
