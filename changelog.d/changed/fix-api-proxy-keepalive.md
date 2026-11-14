- nginx now reuses its connections to the backend for `/api` and the other backend
  routes (`/admin`, `/static`, `/login`, `/logout`, `/complete`, `/disconnect`,
  `/discord/`), as it already did for the frontend. Before, it opened and closed a
  backend connection for every request, leaving several hundred sockets in `TIME_WAIT`
  during a `17-auth` run. WebSocket upgrades on `/api` (draft, herodraft and
  tournament) are unchanged.
