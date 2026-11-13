- Test stack slots N ≥ 1 now have their own hostname, `https://sN.localhost:1N443`,
  so each slot gets its own browser cookie jar. Slot 0 and CI stay on
  `https://localhost`. The self-signed dev cert now covers `*.localhost`, the slot
  hostnames and `nginx`; trust it again if your browser trusted the old one.
- Test stack slots use Django's default cookie names again. The per-slot names
  (`sessionid-sN`, `csrftoken-sN`, from #373) and the `X-CSRF-Cookie-Name` header are
  gone: per-slot hostnames already keep every cookie apart, `df-locale` and
  Django's `messages` included.
