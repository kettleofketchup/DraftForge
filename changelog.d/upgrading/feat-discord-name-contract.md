This release drops the `app_customuser.guildNickname` and `user_baseuserprofile.nickname`
columns, and the site nicknames in them are lost. Before deploying, back up the SQLite
database (`backend/prod.db.sqlite3`) and, while the previous release is still running,
archive the site nicknames and copy the file out next to the backup (the container's
filesystem is not persisted):

```bash
docker exec <backend-container> python manage.py archive_site_nicknames --out /tmp/site-nicknames-<date>.json
docker cp <backend-container>:/tmp/site-nicknames-<date>.json backend/site-nicknames-<date>.json
```

This release's image no longer has that command, so run it before the upgrade. Then
deploy as usual with `just dev::release`: the previous release never reads these
columns, so dropping them while its containers are still up is safe.

Rolling back to the previous release needs no migration. Rolling back two releases
needs the columns back: before switching images, run
`python manage.py migrate app 0106` and `python manage.py migrate user 0005` in this
release's backend container. The columns come back empty; the archive holds the old
site nicknames.
