- Promotion contact sync (event promotion only): contacts an external contact log recorded
  for a bound event are imported by the adaptor and show as a read-only "Contact recorded
  externally" tick in the Promotion tab, marked "Delivery not verified", with no undo.
  Message and Mark as sent are disabled for those players, Hide messaged hides them, and a
  configured org sees a non-blocking "History may be incomplete" notice. Messaging stays
  manual; the sync never sends a DM, creates an account or membership, or awards points
  for an imported contact.
  See docs/features/promotion-contact-sync.md.
- Every DM marked as sent, including repeat sends that earn nothing and sends later
  undone, gets its own retained receipt for the external contact log. The new
  `python manage.py dispatch_promotion_contacts` command sends due receipts to the
  adaptor (off unless `PROMOTION_ADAPTOR_ENABLED` and the adaptor's key are set); the
  send banner shows the external state on its own line and says "Recorded externally"
  only for a confirmed write. Writing to the external contact log is not enabled yet: the
  adaptor answers that writeback is disabled and the receipt is kept as paused, which is
  not a successful sync.
- App tokens get operation grants (`mmr:read`, `mmr:write`, `promotion:read`,
  `promotion:import`), chosen per token in Org Settings → API access.
  API access now appears when the MMR sync API or Promotion is unlocked, so an org
  admin can issue an adaptor token without the MMR sync API feature.
- Integration API under `/api/organizations/<id>/integration/v1/` for the adaptor: event
  recipients and contact receipt import.
- New backend settings `PROMOTION_SYNC_BINDINGS` (org to external guild, event to
  external occasion; empty by default, and unbound orgs and events are left out) and
  `PROMOTION_ADAPTOR_*`.
