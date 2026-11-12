- Migration `0099_backfill_draftoptions_timer_off` gives every existing tournament
  without draft options a `DraftOptions` row with the pick timer off, so drafts already
  running or rebuilt on old tournaments stay untimed. Tournaments created after the
  upgrade still get the timer on by default; `sync_prod_tournaments` and
  `import_prod_tournament` create theirs with the timer off.
