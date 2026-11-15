- Removed the unused `/ajax-auth/<backend>/` login endpoint, which crashed on every
  request. Discord login is unaffected.
- The hourly limit on the public avatar refresh at `/api/avatars/refresh/` now claims
  its slot atomically, so simultaneous page loads can no longer queue the refresh twice.
