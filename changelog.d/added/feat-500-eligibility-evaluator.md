- Signups held for approval now record why: each unmet event requirement is
  stored as a reason with a code, a message, the rule it enforces and, where the
  player can fix it, a link to their profile. Event staff and the player see the
  reasons on the signup; other members do not (#500).
- Staff can re-check a signup's requirements with
  `POST /api/events/signups/<id>/recheck/`, and players can ask
  `GET /api/events/<id>/eligibility/?intent=main|maybe` what they are missing
  without joining the organization (#500).
- Refused web signups now return `reasons` alongside `error` (#500).
