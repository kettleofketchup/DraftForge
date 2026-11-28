# Staff Overrides

Staff actions sometimes break a rule on purpose: placing a player on a full roster,
admitting someone below an MMR gate, going over a team's stand-in cap. Every endpoint
that lets staff do this uses one contract, in `backend/events/overrides.py`: one policy
check, one `409` body, one request shape and one frontend dialog. Endpoints never invent
their own confirm flag or error body.

The policy settings live in [Organization Settings](../features/organization-settings.md#staff-placement).

## Violations

A service describes each broken rule as a `Violation`:

| Field | Meaning |
|---|---|
| `code` | stable machine code, e.g. `over_capacity`, `below_min_mmr` |
| `rule` | rules-register name, e.g. `override-warning`, `staff-override` |
| `message` | server-rendered English naming the rule and the value ("MMR 2,400 is below Roster A's 3,000 gate") |
| `category` | `seating`, `eligibility` or `team` |
| `blocking` | set by the policy check, never by the caller |
| `params` | structured values so the client can format or translate later |

## Policy

`check_overrides(violations, *, org_settings, acknowledged, reason)` applies the org's
`staff_override_policy` and returns the overridden codes. `resolve_overrides` takes the
same arguments and also returns which codes were prompted and the trimmed reason
(`None` when nothing was prompted). `org_settings=None` means the defaults: `silent`,
every code ticked.

| Violation | `silent` | `confirm` | `block` |
|---|---|---|---|
| Seating code (in `ALL_CODES`), ticked in the warning set | passes | prompts until acknowledged | refused (`blocking: true`) |
| Seating code, unticked | passes | passes | passes |
| Eligibility or team code (outside `ALL_CODES`) | prompts | prompts | prompts |

- Codes that pass without a prompt are still returned as overridden, with a `null`
  reason, so the ledger records them.
- One blocking violation refuses the whole action. The `409` then lists every
  prompted and blocking violation, so staff see everything at once.
- A reason is required only when something was prompted: trimmed, 1 to 500 characters.
- Acknowledging a code that was not raised is ignored. A violation that appears between
  the prompt and the retry is not covered by the earlier acknowledgement and prompts
  again.
- Recording the overridden codes and reason (event ledger, `TeamLog`) is the caller's
  job.

Blocks go through `notify_override_blocked`, which logs `override_blocked`
(`system="events"`, `subsystem="overrides"`). Every check logs `override_checked`.
An operations notice for blocks follows once notice routing (#561) lands.

## Wire format

Request fields, read by `parse_override_request(request.data)` (or nest
`OverrideRequestSerializer`):

```json
{"acknowledged_codes": ["over_capacity"], "reason": "Captain asked for a sixth"}
```

Both are optional. There is no boolean confirm field.

The global DRF exception handler (`app.exception_handler`) renders the two exceptions,
so a view or service only has to raise them:

=== "409 OverrideRequired"

    ```json
    {
      "code": "override_required",
      "blocked": false,
      "violations": [
        {
          "code": "below_min_mmr",
          "rule": "staff-override",
          "category": "eligibility",
          "message": "MMR 2,400 is below Roster A's 3,000 gate",
          "blocking": false,
          "params": {"mmr": 2400, "min_mmr": 3000}
        }
      ]
    }
    ```

=== "400 OverrideReasonRequired"

    ```json
    {"code": "override_reason_required"}
    ```

`blocked` is true when any violation is blocking. A blocked override is a `409`, not a
`403`, so the client has one code path.

## Backend usage

```python
from events.overrides import parse_override_request, resolve_overrides

parsed = parse_override_request(request.data)
result = resolve_overrides(
    violations,
    org_settings=get_org_settings(event.organization_id),
    acknowledged=parsed.acknowledged_codes,
    reason=parsed.reason,
)
# perform the action, then record result.overridden and result.reason
```

`events/tests/test_overrides.py` has a complete example view.

## Frontend usage

- `~/components/api/overridesAPI` holds the Zod schemas and the guards
  `getOverrideRequired(err)`, `isOverrideRequiredError(err)` and
  `isOverrideReasonRequiredError(err)`.
- `useOverrideRetry(action)` calls `action({acknowledged_codes: []})` first, opens the
  dialog on a `409`, and resends `{acknowledged_codes, reason}` with every code
  acknowledged so far when staff confirm. The first attempt has no `reason` key.
- `OverrideWarningDialog` lists each violation by rule and message and requires a
  reason. When `blocked` is true it marks the blocking rows, has no Confirm button, and
  links org admins to the Staff placement settings; other staff are told to ask an org
  admin.

```tsx
const retry = useOverrideRetry(
  (ack) => placePlayer(eventId, { user_id, ...ack }),
  { onSuccess: () => toast.success('Placed') },
);

<PrimaryButton onClick={() => void retry.run()}>Place</PrimaryButton>
<OverrideWarningDialog {...retry.dialogProps} organization={organization} />
```

An endpoint that takes its own `reason` (a staff note on the action) shares the field
with the override contract. Put the caller's reason first and spread `ack` after it:
the first attempt sends the caller's reason, and a retry sends the dialog's reason.

```tsx
const retry = useOverrideRetry((ack) =>
  removePlayer(eventId, { user_id, reason: staffNote, ...ack }),
);
```

## Consumers

- [Team management](../api/endpoints.md#team-management) (`/api/teams/{id}/...`): every
  action accepts `acknowledged_codes` and records overridden codes in the team audit log.
  Only `standins/` and `replace-captain/` can answer `409`. Both check the event eligibility
  codes; the stand-in limit (`team_standin_cap`) applies only to `standins/`, and
  `replace-captain/` checks eligibility only for a new captain who is not already on the team.
- [Voiding a withdrawal](../features/events.md#voiding-a-withdrawal)
  (`/api/events/signups/{id}/void-withdrawal/`): raises `over_capacity` when the restored
  status holds a seat on a full event, and records the overridden codes in the signup
  ledger's `rules_overridden`. Staff `reinstate/` never answers `409`; it does not delegate
  to the void when that would seat the member over capacity.
