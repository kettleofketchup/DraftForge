- **Podman container detection (contributors).** The backend now recognises podman
  containers (`/run/.containerenv`, `libpod` cgroups) as well as Docker, so Redis,
  cacheops and Channels use the `redis` service under rootless podman instead of
  `localhost` (#311).
