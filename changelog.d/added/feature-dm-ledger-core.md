- Discord DM ledger: every Discord DM the platform sends (signup reminders, signup
  confirmations, tournament draft and hero draft links, lobby info) is recorded before
  it is sent, with its status, error and button clicks. A DM is never sent twice for
  the same reason, and none is sent while the ledger is unreachable. Admins can browse
  it read-only in the Django admin; existing signup reminder and tournament DM records
  were copied in.
