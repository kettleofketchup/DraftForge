Run migrations: `events.0032` adds `eligibility_reasons` and
`eligibility_checked_at` to event signups. Existing signups start with no stored
reasons; they fill in the next time the player's profile changes or staff
re-check the signup.
