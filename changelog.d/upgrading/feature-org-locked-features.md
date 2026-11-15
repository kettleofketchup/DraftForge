Run the new migrations: `app` 0104, `org` 0007, 0008 and 0009, and `events` 0021.

Contributions and Promotion start locked for every organization. A site admin
unlocks them per org, either in the Django admin (Org features) or from the Locked
features panel on the organization page.

Stale events now auto-close a day after their end time (`ends_at`) when one is
set, and a day after their start otherwise.
