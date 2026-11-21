- Deleting an event or event series in the Django admin now runs the same cleanup as
  the site: the Discord scheduled event and the event's tournament are removed, and a
  deleted series no longer leaves its upcoming events behind (#740).
