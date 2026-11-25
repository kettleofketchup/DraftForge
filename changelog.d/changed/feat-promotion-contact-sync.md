- Undoing a promo send (`DELETE /api/organizations/<id>/promotion/sends/<send_pk>/`) now
  returns `200` with `{"writeback": {...}}` instead of `204` with no body; external
  callers that expect `204` must accept `200`. Undo removes the local send and its points
  but keeps the DM's external receipt, because the message cannot be unsent.
- `POST .../promotion/events/<event_id>/sends/` responses add `writeback`, and the
  send is refused with `409 contact_already_recorded` when the external contact log
  already recorded a contact with that player for the event. Candidate rows add
  `contact_recorded` and `external_contact`, the candidate list adds `contact_sync`, and
  `hide_messaged` also hides players with an external contact.
- After an account merge, open external receipts follow the kept account, but their frozen
  payloads keep the user ID recorded at send time (the adaptor writes from Discord IDs).
  Deleting the kept account later cancels those receipts and redacts their payloads; a
  request already sent to the adaptor cannot be recalled.
- Tokens that existed before operation grants keep exactly `mmr:read` and `mmr:write`.
- The API access token list shows each token's creation time under its prefix instead of
  in a separate Created column, so names stay readable beside their operations.
