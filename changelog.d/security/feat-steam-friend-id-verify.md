- `PATCH /api/users/<id>/` ignores changes to `is_staff`, `is_superuser` and
  `is_active` unless the caller is a superuser. Before, any user could create an
  organization and make themselves a superuser.
- Clearing a member's Friend ID from the organization Users tab or the user edit dialog
  now persists; before, the old ID was silently restored on save.
- A verified Friend ID can only be changed or cleared by staff of the organization that
  verified it, or by site staff. Other organizers get a 403
  (`steam_account_verified_elsewhere`) instead of silently wiping the verification.
