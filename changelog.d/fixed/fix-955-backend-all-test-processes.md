- `just test::backend::all` now honours the local `DJANGO_TEST_PROCESSES` cap (6 by
  default) like `just test::run`, instead of starting one worker per CPU thread for
  each backend group (#955).
