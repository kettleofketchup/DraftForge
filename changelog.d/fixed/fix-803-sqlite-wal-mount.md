- Prod and release deploys no longer lose recent database writes when the backend
  container is recreated: the SQLite write-ahead log now sits on the host next to the
  database (#803).
