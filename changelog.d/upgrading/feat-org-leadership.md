Migration `org.0020_leadership` adds a `track` column to the contribution ledger (`org_contributionentry`). On SQLite this rebuilds the whole table under a write lock; it is quick at current row counts, but deploy in a quiet window. Existing rows read `track="contribution"`, so no data changes.

The new Leadership feature is locked for every organization until a site admin unlocks it.
