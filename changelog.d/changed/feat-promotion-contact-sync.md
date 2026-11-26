- Undoing a promo send (`DELETE /api/organizations/<id>/promotion/sends/<send_pk>/`) now
  returns `200` with `{"writeback": {...}}` instead of `204` with no body; external
  callers that expect `204` must accept `200`. Undo removes the local send and its points
  but keeps the DM's external receipt, because the message cannot be unsent.
- `POST .../promotion/events/<event_id>/sends/` responses add `writeback`, and the
  send is refused with `409 contact_already_recorded` when the external contact log
  already recorded an invitation to that player for the event or holds the event's
  promotion point for them. Candidate rows add `contact_recorded` and `external_contact`,
  the candidate list adds `contact_sync`, and `hide_messaged` also hides players with an
  external contact.
- After an account merge or an approved claim request, the kept account's local point
  for an event is voided when an imported contact holds that point for either Discord
  ID, so the merged player has one live point. Open external receipts follow the kept
  account, but their frozen payloads keep the user ID recorded at send time (the adaptor
  writes from Discord IDs). Deleting the kept account later cancels those receipts and
  redacts their payloads; a request already sent to the adaptor cannot be recalled.
- Changing the promotion point value with "apply to past" also rescores promotion point
  voids and restores. Deleting an event releases the promotion points its imported
  contacts held.
- The member contribution breakdown and the admin ledger show each entry's points with
  their sign, so a negative entry such as a void reads `-1`. Voided entries and their reversals
  no longer count toward a member's leaderboard entries.
- Org Settings → API access is shown to org admins when the MMR sync API or Promotion is
  unlocked, so an org admin can issue an adaptor token without the MMR sync API feature.
  An org with only Contributions unlocked does not see the section.
- Tokens that existed before operation grants keep exactly `mmr:read` and `mmr:write`.
- The API access token list shows each token's creation time under its prefix instead of
  in a separate Created column, so names stay readable beside their operations.
