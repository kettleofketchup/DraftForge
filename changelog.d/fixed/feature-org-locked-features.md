- Multi-day events were auto-closed a day after they started; they now close a day
  after they end.
- Org staff could set an event's `state` directly with a PATCH, skipping the
  normal transitions. `state` is now read-only on the event API.
- Org staff could move an event to another organization by PATCHing its
  `organization`; that is now rejected.
- Editing an event from a browser in a different timezone than the event no
  longer shifts its start time when the form is saved.
