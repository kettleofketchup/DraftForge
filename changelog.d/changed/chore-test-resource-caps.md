- Local test runs share one CPU and memory budget, so several sessions testing at
  once no longer saturate the machine. Test-stack containers, `just test::run`,
  `just test::pw::*` and `just py::test` run inside the `df-tests.slice` systemd user
  slice, capped at 16 cores and 40G by default (`DF_TEST_CPUS`, `DF_TEST_MEM`;
  `DF_TEST_LIMITS=0` turns it off). `just test::limits` shows the cap and current
  usage. `just test::run` defaults Django's `--parallel auto` to 6 workers
  (`DJANGO_TEST_PROCESSES`), and local Vitest to 4 (`VITEST_MAX_WORKERS`). CI is
  unchanged.
