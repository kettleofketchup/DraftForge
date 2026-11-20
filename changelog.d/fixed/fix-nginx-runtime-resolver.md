- nginx now reloads when the frontend or backend container gets a new IP, so
  restarting either one no longer leaves the site serving only the app shell while
  nginx proxies to the old address.
