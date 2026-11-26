- Promotion contact sync (event promotion only): the adaptor imports every contact an
  external contact log holds for the bound guild's players, of any reason, occasion or
  date, once per external contact ID. Edits and deletions made in the external log are
  applied as updates and retractions on the next import, with an org log entry for each
  update. Contacts retain their latest source-scan timestamp, so an overlapping older
  import cannot overwrite, reinstate or retract newer state. An imported invitation for a
  bound event shows as a read-only "Contact recorded externally" tick in the Promotion tab,
  marked "Delivery not verified", with no
  undo. Message and Mark as sent are disabled for those players, Hide messaged hides
  them, and a configured org sees a non-blocking "History may be incomplete" notice.
  Messaging stays manual; the sync never sends a DM or creates an account, membership or
  send. See docs/features/promotion-contact-sync.md.
- One promotion point per event and player across both systems: an imported invitation on
  a bound event holds the point and credits the external promoter when their Discord ID
  belongs to an org member. If a local send already earned that point, the external
  entry wins and the local point is voided by a new "Promotion point voided" ledger
  entry; the send stays recorded. When the external contact changes or is deleted, the
  point moves to the next imported contact or the local point comes back as a
  "Promotion point restored" entry. Voids and restores are never deleted, net to zero in
  the month of the entry they reverse, and are recorded in the org log. Restoration also
  finds sends voided during an account merge, follows replacement duplicate holders, and
  waits until no external holder remains for the merged recipient.
- Every DM marked as sent, including repeat sends that earn nothing and sends later
  undone, gets its own retained receipt for the external contact log. The new
  `python manage.py dispatch_promotion_contacts` command sends due receipts to the
  adaptor (off unless `PROMOTION_ADAPTOR_ENABLED` and the adaptor's key are set); the
  send banner shows the external state on its own line and says "Recorded externally"
  only for a confirmed write. Writing to the external contact log is not enabled yet: the
  adaptor answers that writeback is disabled and the receipt is kept as paused, which is
  not a successful sync.
- App tokens get operation grants (`mmr:read`, `mmr:write`, `promotion:import`), chosen
  per token in Org Settings → API access. `promotion:import` ("Import external contact
  history and promotion points") records external contacts and awards and voids
  promotion points.
- Integration API under `/api/organizations/<id>/integration/v1/` for the adaptor:
  `POST contact-receipts/` imports a range of external contacts.
- New backend settings `PROMOTION_SYNC_BINDINGS` (org to external guild, event to
  external occasion; empty by default, and unbound orgs and events are left out) and
  `PROMOTION_ADAPTOR_*`. After changing a binding, run a full adaptor import so stored
  contacts move to the newly bound events.
