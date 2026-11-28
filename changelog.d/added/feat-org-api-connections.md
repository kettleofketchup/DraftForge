- Org API connections: org admins add named connections in **Org Settings → API
  connections**, each with its own inbound key (hashed, shown once, rotate or revoke)
  and grants, plus independently switched MMR push, MMR pull and promotion push. New
  connections start disabled with no key and no grants. See
  docs/features/org-api-connections.md.
- New key grants `promotion:read` (a bound event's contact receipt history, through
  `GET integration/v1/contact-receipts/`) and `promotion:write` (receipt import, like
  `promotion:import`). Existing keys keep exactly their grants.
- MMR push posts each assigned-MMR change, with an org-wide revision and an idempotency
  key, to the connection's HTTPS endpoint, retries timeouts, `408`, `429` and `5xx`, and
  pauses on auth or schema errors until an admin resumes or resyncs from the Recovery
  tab. Changes are not echoed back to the connection they came from.
- MMR pull fetches org members' MMRs from a configured endpoint (method, query and body
  placeholders, response paths, page or cursor paging), manually or every 15 minutes to
  7 days. It stages every page before writing, reports unmatched and conflicting
  members, never adds members, and only overwrites per the chosen policy. Test
  configuration checks a saved, still disabled connection without writing anything.
- Outbound credentials are encrypted, write-only and bound to the destination origin,
  and outbound requests only reach public HTTPS hosts on port 443, without redirects.
- `GET mmr-sync/` returns each member's `revision`, and `POST mmr-sync/` entries accept
  an optional `expected_revision` that reports a conflict instead of overwriting.
