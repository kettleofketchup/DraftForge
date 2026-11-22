- `PATCH /api/users/<id>/` ignores changes to `is_staff`, `is_superuser` and
  `is_active` unless the caller is a superuser. Before, any user could create an
  organization and make themselves a superuser.
- Clearing a member's Friend ID from the organization Users tab or the user edit dialog
  now persists; before, the old ID was silently restored on save.
