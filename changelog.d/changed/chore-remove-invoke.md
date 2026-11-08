- **Task runner.** Every invoke task moved into the `just` modules under `just/`; logic
  that needs Python is now plain CLIs (`scripts/demo.py`, `scripts/version.py`,
  `scripts/compose.py`). Recipes pass arguments through with their quoting intact, so
  `just test::pw::grep 'title with spaces'` and `just test::run '<cmd with | pipes>'` work.
- **Playwright.** `DF_BASE_URL_SOURCE` is `runner` instead of `invoke`.
- **New recipes** for tasks that were only reachable through invoke:
  `db::populate::bracket-unset-winner`, `csv-import`, `user-edit`, `shuffle-tie`,
  `test::pw::run`, `test::pw::grep`, `docker::*::pull` and `docker::*::run`.
- **Demos.** `just demo::gifs`, `demo::trim` and `demo::quick` exit non-zero when ffmpeg is
  missing or a conversion fails; the record-demos workflow installs ffmpeg.
