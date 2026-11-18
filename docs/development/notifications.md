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

The registry is a set of frozen pydantic models with no Django imports, so the exporter
runs with `python -I`. Its field constraints and validators are also the source of the
frontend's Zod schemas; see [Pydantic to Zod](pydantic-zod.md).

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

Building `REGISTRY` (a `MessageRegistry`) at import enforces the rules below, so an
invalid registry fails on import, in the exporter and in the tests.

| Rule | Enforced by | Reaches Zod |
|---|---|---|
| label and description not blank, at least one channel | `Field` constraints | yes |
| keys, groups, audiences and channels are known values | the `StrEnum`s | yes |
| no unknown fields | `extra="forbid"` | yes (`.strict()`) |
| no duplicate channels; `essential_locked` implies `essential_default`; a locked group is not opt-outable | model validators on `MessageType` / `MessageGroup` | no |
| keys unique and well formed; every type's group exists; every `conduct` type locked; a `channel_post`-only type is not in an opt-outable group | `registry_errors()`, run by `MessageRegistry` | no |

## The generated file

`messageTypes.generated.ts` holds:

- a Zod schema and inferred type per model and enum: `MessageKeySchema`,
  `GroupKeySchema`, `ChannelSchema`, `AudienceSchema`, `MessageGroupSchema`,
  `MessageTypeSchema`, `MessageRegistrySchema` (enum values via `.options`);
- the catalogue itself: `MESSAGE_REGISTRY`, typed as `MessageRegistry`, with camelCase
  fields (`MESSAGE_REGISTRY.messageTypes`, `MESSAGE_REGISTRY.groups`).

It is formatted with the frontend's Prettier config, and two runs produce identical
bytes. Never edit it by hand.

## CI freshness check

```bash
just py::gen-message-types --check
```

This writes nothing and exits 1, naming the first differing line, when the committed
file differs from what the registry produces. The `unit` job in
`.github/workflows/playwright.yml` runs it, so a registry change without a regenerated
file fails CI.
