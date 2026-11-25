- SFG promotion sync (event promotion only): contacts SFG recorded for a bound event are
  imported by the sfg-adapter and show as a read-only "Contact recorded in SFG" tick in
  the Promotion tab, marked "Delivery not verified", with no undo. Message and Mark sent
  are disabled for those players, Hide messaged hides them, and a configured org sees a
  non-blocking "History may be incomplete" notice. Messaging stays manual; the sync never
  sends a DM, creates an account or membership, or awards points for an imported contact.
  See docs/features/sfg-promotion-sync.md.
- Every DM marked as sent, including repeat sends that earn nothing and sends later
  undone, gets its own retained receipt for SFG's contact log. The new
  `python manage.py dispatch_promotion_contacts` command sends due receipts to the
  adaptor (off unless `PROMOTION_ADAPTOR_ENABLED` and the adaptor's `sfga_` key are set);
  the send banner shows the SFG state on its own line and says "Recorded in SFG" only for
  a confirmed write. Writing to SFG is not enabled yet: the adaptor answers that writeback
  is disabled and the receipt is kept as paused, which is not a successful sync.
- App tokens get operation grants (`mmr:read`, `mmr:write`, `promotion:read`,
  `promotion:import`, `contributions:read`), chosen per token in Org Settings → API access.
  API access now appears when any feature with token operations is unlocked, so an org
  admin can issue an SFG adaptor token without the MMR sync API feature.
- Integration API under `/api/organizations/<id>/integration/v1/` for the adaptor: event
  recipients, contact receipt import, and all-time contribution-track totals (zero and
  negative totals exact; members without a usable Discord ID reported as unavailable).
- New backend settings `SFG_PROMOTION_BINDINGS` (org to SFG guild, event to SFG
  occasion; empty by default, and unbound orgs and events are left out) and
  `PROMOTION_ADAPTOR_*`.
