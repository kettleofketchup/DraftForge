- `just test::slot-reap` can now remove the `df-run-<hex>` project (usually a lone
  `redis-run-<hex>` container) that a killed `just test::run` leaves behind. A project
  counts as orphaned once no one-off container runs in it and the process that created
  it is gone; `just test::slot-reap --stale` and every slotless `just test::run` sweep
  such projects. `just test::run` also cleans up on SIGTERM and SIGHUP, not only Ctrl-C.
