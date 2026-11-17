# Notification Message Types

Every member message DraftForge sends is listed in one place:
`backend/notifications/registry.py`. The frontend never hard-codes message types. It
reads them from `frontend/app/lib/notifications/messageTypes.generated.ts`, which is
generated from the registry, so a new message type appears as an opt-out option
without a frontend change.

!!! note
    The registry is the catalogue only. Delivery, opt-out preferences and org policy
    are built on top of it in later work (epic #486).

## Concepts

| Name | What it is |
|---|---|
| `MessageGroup` | A set of related messages that members opt out of together (`roster_changes`, `pre_game_reminders`, ...). `opt_outable_default` says whether members may opt out when the org has no policy. |
| `MessageType` | One message: `key`, `group`, `label`, `description`, `audience`, `channels`, `essential_default`, `essential_locked`, `urgent`. |
| `Channel` | Where it can be delivered: `dm`, `ephemeral` (an interaction reply) or `channel_post`. |
| `Audience` | Who receives it: `signup`, `subscriber`, `tournament_participant`, `match_player`. |
| Essential | Delivered even when the member opted out. Orgs can change the essential set, except for `essential_locked` types. |
| `conduct` group | Reserved and locked: every type in it must be `essential_locked`. |

The registry is plain Python with no Django imports, so the exporter and the CI check
run with `python3 -I` and no virtualenv.

## Adding a message type

1. Add a member to `MessageKey` in `backend/notifications/registry.py`. Keys are
   `area.name` in lower snake case, for example `rsvp.promotion`.
2. Add a `MessageType` entry to `MESSAGE_TYPES` (and a `MessageGroup` to `GROUPS` if you
   need a new group, plus a `GroupKey` member). The order of `MESSAGE_TYPES` must match
   `MessageKey`.
3. Regenerate the frontend file and commit it with the registry change:

    ```bash
    just py::gen-message-types
    ```

4. Run the registry tests:

    ```bash
    just test::run 'python manage.py test notifications.tests -v 2'
    ```

`validate_registry()` enforces the rules below; the exporter refuses to write an invalid
registry and the tests fail on one.

- keys are unique and well formed;
- every type's group exists;
- `essential_locked` implies `essential_default`;
- every `conduct` type is locked, and a locked group cannot be opt-outable;
- a type delivered only as a `channel_post` cannot sit in an opt-outable group;
- label, description and channels are not empty.

## The generated file

`messageTypes.generated.ts` holds:

- const arrays: `MESSAGE_CHANNELS`, `MESSAGE_AUDIENCES`, `MESSAGE_GROUP_KEYS`, `MESSAGE_KEYS`;
- Zod schemas and inferred types: `MessageKeySchema`, `MessageGroupKeySchema`,
  `MessageGroupSchema`, `MessageTypeSchema` (and the channel/audience enums);
- the catalogue itself: `MESSAGE_GROUPS` and `MESSAGE_TYPES`, with camelCase fields.

The exporter formats the file the way Prettier does, so it passes `prettier --check`,
and two runs produce identical bytes. Never edit it by hand.

## CI freshness check

```bash
just ci::message-types-check
```

This runs `python3 -I backend/notifications/export_schema.py --check`, which writes
nothing and exits 1 with a unified diff when the committed file differs from what the
registry produces. The `unit` job in `.github/workflows/playwright.yml` runs it, so a
registry change without a regenerated file fails CI. `--out PATH` points either mode at
another file.
