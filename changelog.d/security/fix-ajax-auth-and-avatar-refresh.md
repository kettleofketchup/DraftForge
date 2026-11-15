- Only site staff can trigger the bulk Discord avatar refresh at `/api/avatars/refresh/`.
  Before this, anyone, even while logged out, could queue a refresh of every user's
  avatar. The hourly limit is unchanged, and the daily Celery job still refreshes
  avatars on its own. Loading the users list no longer fires the refresh.
- Removed the unused `/ajax-auth/<backend>/` login endpoint, which crashed on every
  request. Discord login is unaffected.
