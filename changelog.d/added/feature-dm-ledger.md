- Discord DM ledger: every Discord DM the platform sends (signup reminders, signup
  confirmations, tournament draft and hero draft links, lobby info, leadership review
  DMs) is recorded before it is sent, with its status, error and button clicks. A DM
  is never sent twice for the same reason, and none is sent while the ledger is
  unreachable. Admins can browse it read-only in the Django admin; existing signup
  reminder and tournament DM records were copied in.
- Leadership: **Send review DMs** (off by default) DMs each teammate a Discord message
  with a row of 1–5 buttons per trait when an event closes, so they can score their
  captain from Discord. Orgs with more than 5 active traits get two messages. Each
  teammate is DMed once per captain; reopening and re-closing an event sends nothing
  new.
- Leadership: **Show captains their feedback** (on by default) lets an org hide
  captains' own rating, trait scores, per-event results and rating points from them.
  Staff and the public ranking are unaffected.
