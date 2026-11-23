The prod and release stacks now keep the SQLite database in `backend/data/` (mounted at
`/app/backend/data`, with `SQLITE_PATH=data/prod.db.sqlite3` in `docker/.env.prod` and
`docker/.env.release`). Move the existing database there once, with the backend
stopped so nothing is left only in the write-ahead log. `just dev::release` refuses to
run until this is done.

Release stack (the database is `backend/prod.db.sqlite3` on the host):

```bash
git pull
docker compose --project-directory . -f docker/docker-compose.release.yaml stop backend
mkdir -p backend/data
mv backend/prod.db.sqlite3 backend/data/
mv backend/prod.db.sqlite3-wal backend/prod.db.sqlite3-shm backend/data/ 2>/dev/null || true
chown -R 1000:1000 backend/data   # the image's appuser; use sudo if needed
just dev::release
```

The `-wal`/`-shm` files on the host are normally absent: before this change they lived
inside the backend container, and stopping it cleanly checkpoints them into the main
file. Stop the container rather than killing it. The prod stack
(`docker/docker-compose.prod.yaml`) used `backend/db.sqlite3`; move that file to
`backend/data/prod.db.sqlite3` the same way.
