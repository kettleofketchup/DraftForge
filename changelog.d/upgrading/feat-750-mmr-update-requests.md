This release adds Pillow, and migrations run on the host venv. On the release host,
after `git pull`, install the new dependency before deploying:

```bash
just update::python      # or: .venv/bin/poetry sync
just dev::release
```

MMR screenshots are stored in `backend/media`, bind-mounted into the backend container.
`just dev::release` creates the directory and warns unless uid 1000 owns it; fix it with
`sudo chown 1000:1000 backend/media`. Back up `backend/media` together with
`backend/prod.db.sqlite3`.

Migration `org.0020` marks existing Dota org MMRs that already had an active verification
date as Official (with no verifier). Helm previews store media at `/data/media`.
