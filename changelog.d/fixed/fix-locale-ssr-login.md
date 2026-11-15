- Signed-out visitors now get the localized "Login with Discord" button in the
  server-rendered page instead of a placeholder that swapped in after load. nginx
  now caches signed-in and signed-out HTML separately, so neither copy reaches
  the other.
