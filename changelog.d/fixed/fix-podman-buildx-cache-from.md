- `just docker::all-build` (and so `just test::setup`) works under podman again: the
  BuildKit registry cache flags, which podman rejects, are skipped when `docker` is podman.
