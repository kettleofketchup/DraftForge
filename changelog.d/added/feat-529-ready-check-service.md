- Ready check service and API (#529): starting roll call opens a ready check, and operators can view,
  open, escalate, close and resolve it and confirm members on their behalf; members confirm themselves
  through `POST /api/events/<id>/ready/`. Nothing is scheduled or messaged yet, and automatic mode stays
  staff-verified on this site until members get a Ready button. Until line placement ships, Maybe RSVPs
  are not asked and freed seats are filled in waitlist order.
- The event host and helpers can run the event's ready check, with a required reason to resolve a held
  check, and a member who confirms too late is told to contact the host by name.
- The event host and helpers see and resolve the event's ops notices on the event page.
