- `just dev::release` no longer starts production with Django's public development secret
  key. When `backend/.env` has no `DJANGO_SECRET_KEY` (or an empty one), it prints a warning,
  generates a random key and saves it there before the containers start.
