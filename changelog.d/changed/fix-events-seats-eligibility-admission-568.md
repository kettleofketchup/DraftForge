- Tentative and waitlisted signups no longer take event seats, and one cancellation
  now fills every seat it frees from the waitlist (#568).
- Signup counts on the event list, the event page and the Discord scheduled event
  drop, because tentative and waitlisted players no longer count as signed up.
- Operators run `python manage.py rebalance_event_waitlists` once after deploying;
  it may promote waitlisted players into seats tentative players were holding.
