The `app` and `events` migrations up to 0.17.0 are squashed and the replaced files are
deleted. A database at 0.17.0 or later needs nothing: `migrate` records the squashed
migrations as applied without running them. A database older than 0.17.0 cannot
migrate on this release; upgrade it to 0.17.0 first, then to this release.
