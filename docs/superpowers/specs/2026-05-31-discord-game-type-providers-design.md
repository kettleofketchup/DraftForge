# Discord Game-Type Providers — Design

**Date:** 2026-05-31
**Branch:** `refactor/discord-game-type-providers`
**Status:** Approved design (revised after two multi-agent review rounds), pending implementation plan

## Problem

The Discord event-signup UI and its business logic are entangled across game
types. `discordbot/components.py` (1052 lines) mixes game-agnostic RSVP
controls with Dota-specific MMR / position / Battle Cup flows and Deadlock
text-field flows in one file. `events/discord/handlers.py` branches on
`event.game_type` while the rank / medal / Battle Cup handlers are implicitly
Dota-only with no marker saying so. The internal-API response schema
(`SignupActionResponse`) is a god-envelope that flattens eight Dota-specific
config flags plus write-only `medal` / `tier` into one model regardless of game.

Adding or maintaining a game type means editing scattered `if game_type ==`
branches in multiple files. The goal is to make per-game behavior easy to add
and maintain by giving each game type an operation-owning provider behind a
registry, with each interaction dispatched to a provider method via a typed
Pydantic custom-id.

## The process boundary (load-bearing constraint)

`discordbot/` runs in the **bot process** and must never import the Django ORM
(documented in `internal_client/signup_actions.py` — overlay-fs / page-cache
divergence). `events/discord/` runs in the **backend process** with ORM access.
They communicate only over HTTP via `signup_actions.py`.

Consequence: there is **no single `DotaProvider` class**. "Dota" is realized as
a *pair* of operation-owning objects across the boundary, plus its codecs:

- `DotaComponents` (bot process) — owns Dota's **interaction/render** operations
  as methods; calls the HTTP client; holds no ORM.
- `DotaHandler` (backend process) — owns Dota's **persistence** operations as
  methods; reads/writes the ORM.
- Dota codec subclasses in `discordbot/custom_ids.py` — the typed wire format.

They share only the `GameType` key and the typed `SignupActionResponse` /
`SignupModalConfig` HTTP contract. "Adding a game" therefore means: a module in
each layer + codecs + one registration per layer. The spec is explicit about
this 2-objects-plus-codecs reality rather than chasing an impossible
single-class facade.

## Goals

- An operation-owning provider per game in each layer. Adding a game touches a
  bounded, enumerated set of ~6 sites (see "Adding a game type") — not literally
  "two files," but a short, documented checklist with tests that fail loudly on
  a missed step.
- No `if game_type ==` branching in `bot.py` or `handlers.py`.
- A `default`/general provider for any game type without a dedicated module.
- Deadlock kept as its own provider alongside Dota and default.
- **Composition spine:** each interaction is dispatched to a provider method
  via a typed Pydantic custom-id (see "Dispatch & composition").
- **No behavior change** except documented exceptions — (a) `game_type` for
  modal submit resolves from `event.game_type` not the client-sent value (see
  Handler layer); (b) two in-flight bug fixes for issue #268 (see "Bugs fixed
  in-flight") — and **no custom-id wire-format change**, so already-posted
  Discord messages keep working after deploy.

## Non-Goals

- No change to embed builders (`events/discord/embeds.py`) or the
  announcement-message builder (`events/discord/components.py` raw-dict path).
- No new game types (Dota + Deadlock + default only).
- No discriminated-union `SignupActionResponse` (deferred). Only the eight
  config flags collapse into a nested `modal_config`.
- No change to `RankFlowStateResponse` (separate model, stays flat).
- No change to `discordbot/schemas.py` request schemas unless the modal `values`
  shape changes (see Open Items).

## Dispatch & composition (the spine)

**The "custom-id router" is per-callback typed decode + bound-method delegation,
NOT a central dispatcher.** The Dota follow-up views are **ephemeral,
session-scoped in-memory views** (`timeout=300`), registered in discord.py's
view store by `store_view` at the moment they are sent
(`interaction.response.send_message(view=...)` / `edit_message(view=...)`, e.g.
`components.py:67-68,459,569,682`). They are NOT persistent (`add_view` /
`timeout=None`) and do NOT survive a bot restart — discord.py dispatches their
child-component callbacks directly while the bot process still holds them,
without going through `on_interaction`. (The RSVP buttons are different: the
announcement is posted via the **raw-dict `components=` path** in
`discordbot/utils.py`, never handed to discord.py as a `ui.View`, so they are
reconstructed from `custom_id` on every interaction in `on_interaction`
— `bot.py:167-182`.)

A central router in `on_interaction` for the ephemeral-view components would be
a *second, competing* dispatcher; for any component with an overridden callback
it both duplicates work and loses the documented 40060 ACK race (the HTTP
round-trip to the backend is ~200ms, so discord.py ACKs first). See
`bot.py:183-190` and the `MedalSelect.callback` scar at `components.py:748-754`.

So composition is realized as: **each Dota View/Select callback decodes its own
typed `CustomId` and delegates to a bound `DotaComponents` method, forwarding
the View's transient state as explicit kwargs.** Per-interaction state
(`rank_status`, `require_screenshot`, `min_mmr`, `selected_medal`) lives on the
View instance as it does today — it is NOT in the custom-id and cannot be
reconstructed from `cid` alone — so the provider methods receive it per-call.
The provider itself stays a stateless singleton (it stores nothing on `self`).
The relocated body MUST carry its `discord_log_context(...)` wrapper and
`ctx.set_outcome`/`ctx.add` telemetry with it, or structured tracing is lost.

```python
# discordbot/components/dota.py
class DotaComponents(GameComponentProvider):
    """Stateless singleton. Owns Dota's interaction operations as methods. No ORM.
    Transient flow-state is passed per call (it lives on the View, not here)."""
    async def signup_event(self, interaction, cid: SignupId) -> None: ...
    async def rank_status_select(self, interaction, cid: RankStatusId) -> None: ...   # cid-only: clean
    async def rank_medal_select(self, interaction, cid: RankMedalId, *,
                                rank_status: str, require_screenshot: bool) -> None: ...
    async def rank_star_select(self, interaction, cid: RankStarId, *, rank_status: str) -> None: ...
    async def battle_cup_select(self, interaction, cid: BattleCupTierId) -> None: ...  # screenshot is server-driven
    async def position_confirm(self, interaction, cid: PosConfirmId, *,
                               rank_status: str, require_screenshot: bool, min_mmr: int | None) -> None: ...
    async def position_select(self, interaction, cid: PosSelectId) -> None: ...        # bare select
    async def screenshot_upload(self, interaction, cid: ScreenshotUploadId) -> None: ...

class StarSelect(ui.Select):
    def __init__(self, event_id, provider, *, rank_status, ...):
        super().__init__(custom_id=RankStarId(event_id=event_id, medal=...).encode(), ...)
        self._provider, self.rank_status = provider, rank_status
    async def callback(self, interaction):          # discord.py dispatches HERE — no race
        await self._provider.rank_star_select(
            interaction, RankStarId.decode(self.custom_id), rank_status=self.rank_status)
```

`rank_status_select` and `battle_cup_select` need only `cid` (their callbacks
read only `self.event_id`/`self.values`; the Battle Cup screenshot branch is
server-driven via `result["screenshot_type"]`). `position_confirm`,
`rank_medal_select`, and `rank_star_select` forward View state. The ORM-bearing
methods (`position_confirm`, `rank_medal_select`, `rank_star_select`,
`battle_cup_select`) **defer first** then `edit_original_response` — the issue
#268 bug-2 fix, see "Bugs fixed in-flight." This
gives the requested `DotaComponents.<operation>(...)` composition keyed by typed
Pydantic custom-ids, while the dispatch stays exactly where discord.py already
puts it — so the 40060 race is never reintroduced.

**The one genuine central-lookup case — bare selects.** `pos_select_` is a bare
`ui.Select` with no overridden callback (discord.py's default callback is a
no-op), so discord.py will NOT self-dispatch it. Only this prefix needs
`on_interaction` to find a provider:

```python
# bot.py:on_interaction
else:
    for provider in iter_component_providers():
        for id_type in provider.bare_select_ids:     # ONLY codecs whose component has NO overridden callback
            if id_type.matches(custom_id):
                try: cid = id_type.decode(custom_id)
                except ValueError: return            # malformed -> unhandled no-op
                await provider.dispatch_bare_select(interaction, cid)  # -> self.position_select(...)
                return
```

`bare_select_ids` is named to carry the invariant: it lists ONLY codecs whose
components have no overridden callback. `DotaComponents.bare_select_ids =
(PosSelectId,)`; every other provider `= ()`. No "register all my codecs"
convenience may populate it, or the self-dispatching components would get
double-dispatched and resurrect 40060.

## Architecture

```
backend/
  discordbot/
    custom_ids.py                 # NEW: typed custom-id codecs (pydantic, bot-internal)
    components/                    # NEW package (replaces components.py)
      __init__.py                 # re-exports public View classes for back-compat
      base.py                     # shared: EventSignupView, RSVP buttons,
                                  #   ScreenshotUpload* infra, send_modal_v2,
                                  #   build_friend_id_input
      dota.py                     # DotaComponents (operation-owning) + Dota views
      deadlock.py                 # DeadlockComponents + Deadlock modal
      default.py                  # DefaultComponents (minimal modal)
      registry.py                 # get_component_provider / iter_component_providers

  events/
    schemas.py                    # EXTENDED: SignupModalConfig + game subclasses;
                                  #   dota_require_screenshot(); SignupActionResponse tidied
    discord/
      handlers.py                 # thin dispatcher to provider registry
      _shared.py                  # NEW: _get_org_user, _load_event, _direct_signup,
                                  #   _log_signup, _log_interaction
      providers/                  # NEW package
        __init__.py
        base.py                   # GameSignupHandler protocol + DefaultHandler
        dota.py                   # DotaHandler (owns rank-flow ops as concrete methods)
        deadlock.py               # DeadlockHandler
        registry.py               # get_signup_handler
```

### Protocols (two, not three)

**`GameComponentProvider`** (UI layer):

- `build_signup_modal(event_id, prefill, config: SignupModalConfig) -> ui.Modal`
- `bare_select_ids: tuple[type[CustomId], ...]` — see Dispatch (Dota: `(PosSelectId,)`; others `()`).
- `dispatch_bare_select(interaction, cid) -> None` — routes a bare-select codec
  to the owning method (Dota: `position_select`).
- Plus the game's interaction-operation methods (the composition spine) and its
  follow-up View classes, all in the game module.

**`GameSignupHandler`** (logic layer, `providers/base.py`) — the four genuinely
game-agnostic operations only:

- `profile_complete(org_user, event) -> bool`   (Default: `True`)
- `prefill(org_user) -> dict`                    (Default: `{}`)
- `modal_config(event) -> SignupModalConfig`     (Default: `SignupModalConfig()`)
- `apply_modal_submit(org_user, user, event, values) -> SignupActionResponse`

**No `RankFlowHandler` protocol.** The eight Dota rank-flow operations are
**concrete methods on `DotaHandler`** (a single-implementer Protocol would be
ceremony and would fragment the "one class owns its methods" composition). The
rank-flow entry functions in `handlers.py` resolve the handler and guard with
`isinstance(handler, DotaHandler)`, returning an `error` response otherwise — so
non-Dota games reject stray rank-flow calls without stubbing anything.

### Registry + drift guard

```python
COMPONENT_PROVIDERS = {GameType.DOTA2: DotaComponents(), GameType.DEADLOCK: DeadlockComponents()}
def get_component_provider(game_type) -> GameComponentProvider:
    provider = COMPONENT_PROVIDERS.get(game_type)
    if provider is None:
        log.error("provider_fallback", layer="components", game_type=game_type)
        return DefaultComponents()
    return provider
```

`GameType` is `models.IntegerChoices` (an `IntEnum`), so `COMPONENT_PROVIDERS`
keyed on `GameType` members is looked up correctly with the bare
`int` `resp.game_type` (`GameType.DOTA2 == 1` and hashes equal). The handler
registry mirrors this. Unregistered type → default provider + a loud
`provider_fallback` `log.error` (never a silent degrade).

**Drift guard:** a single test asserts `set(COMPONENT_PROVIDERS) ==
set(SIGNUP_HANDLERS)` (both importable in the backend test env). No separate
`SUPPORTED_GAME_TYPES` manifest — the two dicts are the sources of truth and the
equality test catches the "added to one layer, forgot the other" failure mode.

Provider instances are module-level singletons and **must be stateless** — every
call passes `event_id`/`prefill`/`config`/`cid` and returns fresh
objects. Storing per-interaction state on a provider would race across
concurrent users. The protocol docstring states this; the per-game module
docstrings cross-reference their counterpart in the other layer.

## Component layer (`discordbot/components/`)

**`base.py`** — game-agnostic, behavior unchanged:

- `EventSignupView` (+ `SignupButton`, `NotifyButton`, `TentativeButton`,
  `DeclineButton`). The RSVP button callbacks decode their typed codec and call
  the HTTP client directly (game-agnostic; not Dota-specific).
- `send_modal_v2`; `ScreenshotUploadPromptView` / `ScreenshotUploadButton` /
  `ScreenshotUploadModal` generic upload infra (param: `screenshot_type`,
  `example_url`).
- `build_friend_id_input(event_id, prefill, required) -> ui.TextInput | None` —
  shared helper, single label **"Steam Friend ID"**. **Preserves current
  behavior exactly:** returns `None` (field omitted) when
  `prefill.get("unverified_friend_id")` is set or `required` is False; else
  renders with `default=prefill.get("unverified_friend_id", "")`. Prefill key
  stays `unverified_friend_id` end-to-end.
- `SignupButton.callback`: on `needs_modal`, asks the component registry for
  `resp.game_type` and calls `provider.build_signup_modal(event_id,
  resp.prefill, resp.modal_config)`.
- **Module-level bindings preserved for test patching:** `signup_button`,
  `respond_to_signup_user`, `save_positions`, `set_position` remain
  importable/patchable at their new defining modules (see Testing).

**`dota.py`** — `DotaComponents` (operation-owning, per Dispatch spine):

- `build_signup_modal()` returns `DotaSignupModal`, which **stashes the full
  `DotaModalConfig` on `self`** — `min_mmr` and the screenshot flags are read at
  the *follow-up* step, not at render. `on_submit` extracts Dota values and
  builds the follow-up chain (`PositionSelectView` → `RankDetailsView`).
- Screenshot-required is computed by the shared pure function
  `dota_require_screenshot(rank_status, config)` (in `events/schemas.py`, see
  below) — NOT a duplicated ternary.
- Owns `PositionSelectView`, `PositionConfirmButton`, `RankStatusSelectView`,
  `RankStatusSelect`, `RankDetailsView`, `MedalSelect`, `StarSelect`,
  `BattleCupTierSelect`, the `DOTA_POSITIONS`/`DOTA_MEDALS`/`DOTA_STARS`
  constants + option builders. Each ephemeral-view callback delegates to a
  `DotaComponents` method (forwarding its View state per call).
- **`StarSelect` sentinel logic stays in the callback, not the codec:**
  `medal_part = selected_medal or "Herald"`; on decode `parts[2] == "Herald"`
  means "unset — scan sibling `MedalSelect.values`"; `"Immortal"` suppresses the
  star. `RankStarId` round-trips the literal string only (one-line codec
  docstring notes the sentinel lives in the callback).
- `bare_select_ids = (PosSelectId,)`; `dispatch_bare_select` → `position_select`
  (defer + `set_position`, exactly as today).

**`deadlock.py`** — `DeadlockComponents`: `build_signup_modal()` →
`DeadlockSignupModal` (friend-id + rank/date inputs); direct signup, no
follow-up; `bare_select_ids = ()`.

**`default.py`** — `DefaultComponents`: minimal modal (friend-id only, or none
if `config.require_steam_id` is False); `bare_select_ids = ()`.

**Back-compat (`components/__init__.py`):** re-exports every symbol any importer
or test uses: `EventSignupView`, `SignupButton`, `NotifyButton`,
`TentativeButton`, `DeclineButton`, `PositionSelectView`, `PositionConfirmButton`,
`RankDetailsView`, `MedalSelect`, `StarSelect`, `BattleCupTierSelect`,
`RankStatusSelect`, `RankStatusSelectView`, plus patchable bindings
`signup_button` / `save_positions` / `set_position` / `respond_to_signup_user`.
`EventSignupModal` is removed; the test importing it builds via the Dota provider.

## Handler layer (`events/discord/providers/`)

`handlers.py` keeps **every** public entry function with **unchanged names and
`/discord/...` route bindings** — thin dispatchers. The complete 13-endpoint
surface (matching `internal_client/signup_actions.py`) and where each lands:

| Entry function (`handlers.py`) | Lands on |
|---|---|
| `handle_signup_button` | shared dispatch → `handler.profile_complete` / `_direct_signup` / `needs_modal` |
| `handle_signup_modal_submit` | shared dispatch → `handler.apply_modal_submit` |
| `handle_notify_button` | shared (game-agnostic RSVP) |
| `handle_decline_button` | shared (game-agnostic RSVP) |
| `handle_tentative_button` | shared (game-agnostic RSVP) |
| `handle_rank_status_select` | `DotaHandler` (concrete method) |
| `handle_rank_medal_select` | `DotaHandler` |
| `handle_previous_rank_submit` | `DotaHandler` |
| `handle_battle_cup_submit` | `DotaHandler` |
| `handle_screenshot_upload` | `DotaHandler` |
| `handle_save_positions` | `DotaHandler` |
| `handle_set_position` | `DotaHandler` |
| `handle_get_rank_flow_state` | `DotaHandler` (returns `RankFlowStateResponse`, unchanged) — **dead-but-retained** |

**Dead-but-retained endpoints:** `handle_get_rank_flow_state` and
`handle_previous_rank_submit` have **no live bot-side caller** today (the
`pos_confirm` flow reads state off the View; the "previous" rank path routes
through `rank_medal_select`). They remain wired to endpoints + tests, so they
relocate to `DotaHandler` for completeness but get no new logic — in particular
the `dota_require_screenshot` extraction is driven by the **live** copy at
`components.py:444-452`; touching `handle_get_rank_flow_state` is dead-code
hygiene only. Mark them dead in the plan so the per-endpoint round-trip test
matrix doesn't imply they're live paths.

**Producers return `.model_dump()` dicts, not Pydantic instances.** The DRF
view layer (`internal_signup_views.py`) does `result.get("action")` then
`Response(result)` — both require a plain dict (a `BaseModel` has no `.get()`
and DRF's `JSONRenderer` has no Pydantic hook). So every handler builds the
typed model for validation/safety and `.model_dump()`s it at the `return`,
preserving the dict contract that `internal_signup_views.py` and the consumer's
`signup_actions.py:43` (`model_validate(resp.json())`) both depend on.

```python
def handle_signup_button(event_id, discord_user_id, discord_username):
    event = _load_event(event_id)                          # _shared
    org_user, user = _get_org_user(event, discord_user_id) # _shared
    ...                                                     # _shared dedupe check
    handler = get_signup_handler(event.game_type)
    if handler.profile_complete(org_user, event):
        return _direct_signup(event, user)                 # _shared (already dict)
    return SignupActionResponse(action="needs_modal", game_type=event.game_type,
                                prefill=handler.prefill(org_user),
                                modal_config=handler.modal_config(event)).model_dump()

def handle_rank_medal_select(event_id, discord_user_id, medal):
    handler = get_signup_handler(_load_event(event_id).game_type)
    if not isinstance(handler, DotaHandler):
        return SignupActionResponse(action="error", message="Not applicable.").model_dump()
    return handler.rank_medal_select(...)   # also returns .model_dump()
```

**`game_type` resolution — an intentional tightening.** Today
`handle_signup_modal_submit` branches on the **client-sent** `game_type`
(`handlers.py:301,339`; `SignupModalSubmitRequest.game_type`), which the modal
stashed from `handle_signup_button`. The new dispatch resolves the handler from
**`event.game_type`** (server truth) and ignores the client-sent value. In the
normal flow they always agree; resolving from the event removes a drift window
(event re-typed between modal-open and submit). This is a deliberate, safe
tightening — not strictly "no behavior change" — and makes
`SignupModalSubmitRequest.game_type` vestigial (keep it accepted-but-ignored;
see Open Items).

- **`DefaultHandler` (base.py):** the four common methods with safe defaults.
- **`DotaHandler` (dota.py):** `_check_dota_profile_complete`, `DotaModalConfig`
  assembly, `apply_modal_submit`, and the eight rank-flow operations as concrete
  methods.
- **`DeadlockHandler` (deadlock.py):** `_check_deadlock_profile_complete`,
  `apply_modal_submit` (save `PlayerDeadlockProfile` → direct signup).

**`events/discord/_shared.py`:** `_get_org_user`, `_load_event`,
`_direct_signup`, `_log_signup`, `_log_interaction`, dedupe check — imported by
`handlers.py` and every provider (no provider→dispatcher inversion).
`events/discord/__init__.py` `__all__` is updated so the re-exported helpers
(`_check_dota_profile_complete`, `_check_deadlock_profile_complete`,
`_get_org_user`) source from their new modules. **Load-bearing invariant:** the
existing `events.services → events.discord(__init__) → handlers` cycle
(`handlers.py:21`) is broken today by keeping all `from events.services import …`
calls **function-local**. `_shared.py` (`_get_org_user` needs
`resolve_or_create_org_user`; `_direct_signup` needs `process_rsvp`) and the
providers MUST preserve that function-local discipline — a top-level
`events.services` import in either re-introduces the cycle at import time.

## Pydantic data layer

### Typed custom-id codecs — `discordbot/custom_ids.py`

Pydantic `BaseModel` subclasses, bot-internal. The Discord custom-id is a
`prefix:field` **colon string** (100-char cap), so the wire uses `encode()`,
**not** `model_dump()` JSON. (`model_dump()` is for the HTTP models below — the
FastAPI-style "Pydantic model is the contract, dump to JSON on the wire" pattern
that `signup_actions.py` already hand-rolls under DRF.)

```python
class CustomId(BaseModel):
    PREFIX: ClassVar[str]
    event_id: int
    model_config = {"frozen": True}
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        assert getattr(cls, "PREFIX", None), f"{cls.__name__} must set PREFIX"
    def encode(self) -> str: ...
    @classmethod
    def matches(cls, raw: str) -> bool: ...           # raw.startswith(PREFIX + ":")
    @classmethod
    def decode(cls, raw: str) -> "CustomId":
        try: ...                                       # split + int + construct
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r}") from exc
```

`decode` raises `ValueError` uniformly; routers/callers treat any `decode`
exception as "unhandled". One subclass per existing prefix, byte-for-byte:

| Model | Wire format | Owner |
|---|---|---|
| `SignupId` / `TentativeId` / `DeclineId` / `NotifyId` | `event_signup:{id}`, `event_tentative:{id}`, `event_decline:{id}`, `event_notify:{id}` | base |
| `PosSelectId(slot)` | `pos_select_{slot}:{id}` | dota |
| `PosConfirmId` | `pos_confirm:{id}` | dota |
| `RankStatusId` | `rank_status:{id}` | dota |
| `RankMedalId` | `rank_medal:{id}` | dota |
| `RankStarId(medal)` | `rank_star:{id}:{medal}` | dota |
| `BattleCupTierId` | `bcup_tier:{id}` | dota |
| `ScreenshotUploadId(screenshot_type)` | `screenshot_upload:{id}:{type}` | base |
| `ScreenshotFileId(screenshot_type)` | `screenshot_file:{id}:{type}` | base |
| `ScreenshotUrlId(screenshot_type)` | `screenshot_url:{id}:{type}` | base |
| `SignupFriendId` | `signup_friend_id:{id}` | base |
| `SignupRankStatusId` | `signup_rank_status:{id}` | dota |
| `SignupDeadlockRankId` / `SignupDeadlockDateId` | `signup_deadlock_rank:{id}`, `signup_deadlock_date:{id}` | deadlock |

`PosSelectId` carries the slot **before** the colon, so it overrides
`encode`/`decode`/`matches`. `ScreenshotUrlId` is the `FileUpload`-absent
fallback (`components.py:986`) — a live prefix, must be included. Codecs live
centrally in `custom_ids.py` (not per-game module) so the wire format has one
home and `log_context.py` can derive from it.

A **byte-for-byte round-trip test** asserts every model's `.encode()` equals the
current literal and `.decode()` recovers fields; malformed input raises
`ValueError`. **Single source of truth for prefixes:** `log_context.py`
(`_SIGNUP_TAG_PREFIXES`) is refactored to derive its prefix list from
`custom_ids.py`. **Mind the `pos_select_` slot shape:** `_SIGNUP_TAG_PREFIXES`
today lists three literals `pos_select_1/2/3`, and `log_context._prefix()` does
`custom_id.split(":",1)[0]` → `"pos_select_1"`. But `PosSelectId.PREFIX` is
`"pos_select"` (slot is before the colon), so a naive derivation would yield
`{"pos_select"}` and the runtime membership check `"pos_select_1" in {...}` would
**fail**, silently dropping the `["events","signup"]` tags on position selects.
The derivation must normalize/expand the `pos_select_{slot}` shape (e.g. match by
`startswith("pos_select_")`), and `test_log_context` must assert the **runtime
`_prefix("pos_select_1:42")` membership**, not merely set-equality of the two
prefix lists.

### Per-game modal config + shared selection logic — `events/schemas.py`

Each config carries a `kind` **discriminator** literal so the models survive the
HTTP `model_validate(dict) → model_dump()` round-trip in `signup_actions.py:43`.
This is required: with a plain base annotation (`modal_config: SignupModalConfig`)
Pydantic v2 serializes by the declared base type and **silently drops every Dota
field** — empirically verified, `model_dump()` yields only
`{'require_steam_id': True}`, losing `min_mmr` / `allow_*` / screenshot flags.
`SerializeAsAny` does not fix it (validation coerces to base before dump). A
discriminated union is the form that round-trips exactly.

```python
from typing import Literal
from pydantic import Field

class SignupModalConfig(BaseModel):           # base / default
    kind: Literal["default"] = "default"
    require_steam_id: bool = True
class DotaModalConfig(SignupModalConfig):
    kind: Literal["dota"] = "dota"
    require_rank_screenshot: bool = False
    require_battlecup_screenshot: bool = False
    min_mmr: int | None = None
    allow_active_mmr: bool = True
    allow_previous_rank: bool = True
    allow_battlecup_rating: bool = True
class DeadlockModalConfig(SignupModalConfig):
    kind: Literal["deadlock"] = "deadlock"

# discriminated union alias used by the response envelope
ModalConfig = Annotated[
    DotaModalConfig | DeadlockModalConfig | SignupModalConfig,
    Field(discriminator="kind"),
]

def dota_require_screenshot(rank_status: str, cfg: DotaModalConfig) -> bool:
    if rank_status == "active": return cfg.require_rank_screenshot
    if rank_status == "never":  return cfg.require_battlecup_screenshot
    return False                                   # previous
```

`dota_require_screenshot` is the **single** home for the screenshot-required
ternary (replacing the byte-identical copies at `components.py:444-452` and
`handlers.py:799-807`). It's a pure function over the transported config, so
both processes call it: the UI side passes the stashed `DotaModalConfig`;
`handle_get_rank_flow_state` builds a `DotaModalConfig` from the event and calls
the same function. (Keeping two *config flags* is fine and required — only the
*selection logic* is deduplicated.) Both layers already import `events.schemas`
(`signup_actions.py:27`), so no new dependency edge.

`handler.modal_config(event) -> SignupModalConfig` returns the typed game
config (a concrete subclass). A test pins the **producer-side** result —
`DotaHandler.modal_config()` returns a `DotaModalConfig`, `DeadlockHandler` a
`DeadlockModalConfig` — and a separate round-trip test asserts a
`DotaModalConfig` survives `SignupActionResponse.model_validate(resp.model_dump()).modal_config`
with all six Dota fields intact (this is what the `kind` discriminator buys).

### Tidied response envelope — `events/schemas.py`

**Minimal, safe change:** only the eight flat config flags collapse into nested
`modal_config`. `screenshot_type` stays **flat** (the unchanged
`StarSelect`/`BattleCupTierSelect` callbacks read `result["screenshot_type"]`
with a bracket index at `components.py:825,875` — nesting would `KeyError`). The
write-only-never-read `medal` / `tier` fields are **dropped**.

```python
class SignupActionResponse(BaseModel):
    action: str | None = None
    status: str | None = None
    message: str | None = None
    game_type: int | None = None              # bare int for wire compat; GameType is IntEnum
    prefill: dict | None = None
    modal_config: ModalConfig | None = None           # discriminated union (was 8 flat Dota flags)
    screenshot_type: str | None = None                # stays FLAT (bracket-indexed by views)
    subscribed: bool | None = None
    success: bool | None = None
    signed_up: bool | None = None
    positions: list[int] | None = None
    model_config = {"extra": "forbid"}                # was "ignore"
```

**CRITICAL — atomic with producer edits.** `extra: "forbid"` + dropping
`medal`/`tier` means the three producers that currently return those keys
(`handle_rank_medal_select` `handlers.py:433-437`, `handle_previous_rank_submit`
`:490-494`, `handle_battle_cup_submit` `:545-549`) MUST stop emitting `medal=` /
`tier=` in the same change — otherwise `model_validate` raises `ValidationError`
(uncaught by `_validated()`) and the needs-screenshot flow crashes. No consumer
reads `medal`/`tier` (verified: zero `result["medal"]`/`["tier"]` reads), so
simply remove those keys from the three return dicts. **Equally fatal under
`forbid`:** `handle_signup_button` currently returns the seven flat config flags
(`require_steam_id` … `allow_battlecup_rating`); that return dict must be
rewritten to `modal_config=DotaModalConfig(...)` in the same atomic change, or
`forbid` rejects it too. The per-endpoint round-trip test (Testing) catches any
producer still emitting a removed key.

`extra: "forbid"` makes a missed producer key fail loudly in tests rather than
silently become `None`.

**Deploy-skew note (blast radius).** The producer (`handlers.py`) runs in the
backend container; the consumer (`signup_actions.py` `model_validate`) runs in
the discord-bot container. `extra:"forbid"` turns a version-skew window between
the two containers into a hard `ValidationError` (signup crash), not a degrade.
This is acceptable **because DraftForge builds all images at one `pyproject`
version and deploys them together** — the only skew window is the restart, when
the bot is already unavailable and signup interactions already fail. Requirement:
**PR2 (the contract change) must deploy backend + bot from the same release tag**
(the existing release model already does this). Do not hand-deploy one container
ahead of the other.

### Producer / consumer migration surface (atomic, one release)

- **Producers** (`handlers.py`/`DotaHandler`): `handle_signup_button` emits
  `modal_config=DotaModalConfig(...)` (was 8 flat flags); the three
  needs-screenshot producers keep flat `screenshot_type` and **drop**
  `medal`/`tier`.
- **Pass-through:** `internal_signup_views.py` returns `Response(result)`;
  `signup_actions.py:43` does `SignupActionResponse.model_validate(...).model_dump()`.
- **Consumers** (`components.py`): the ~8 `result.get(<flag>)` /
  `event_config.get(<flag>)` sites (`:171-185,307,367,445,448,457`) read the
  nested `modal_config` dict instead. `result["screenshot_type"]`
  (`:825,875`) unchanged.

## Error handling

- Unknown game_type → default provider + loud `provider_fallback` `log.error`.
- Malformed custom-id → `decode` raises `ValueError`; router try/excepts → no-op.
- Missing codec `PREFIX` → `__init_subclass__` assert fails at import.
- Non-Dota handler receiving a rank-flow call → `isinstance(handler,
  DotaHandler)` guard returns an `error` response.
- Existing modal `on_error` handlers preserved per game modal.

## Bugs fixed in-flight (issue #268)

Two production bugs (Grafana-traced) live in code this refactor relocates.
Fixing them in place during the move avoids refactor-then-refix, but they are
**intentional behavior changes** layered on the behavior-preserving refactor.

**Bug 1 — `view=None` crashes the DM-disabled ephemeral fallback**
(`signup_responses.py:96`). `respond_to_signup_user`'s `Forbidden(50007)`
fallback passes `view=view`/`embed=embed` (often `None`) to
`interaction.followup.send` (discord.py `Webhook.send`), which raises
`TypeError: expected view parameter to be of type View not NoneType` — `None`
is not `MISSING` and lacks `__discord_ui_view__`. The DM path (`Messageable.send`)
tolerates `None`, so only the fallback crashes. **Fix:** use the
`discord.utils.MISSING` sentinel (`view if view is not None else MISSING`, same
for embed) on the `followup.send` call **only** — the DM `Messageable.send` path
tolerates `None` (an existing test asserts the DM send receives `view=None`), so
it stays unchanged. `signup_responses.py` is not split by the refactor, so this
is a small self-contained edit on the branch; `base.py`'s RSVP confirmation path
depends on it.

**Bug 2 — `pos_confirm` double-ACK 40060 from slow ORM before defer**
(`components.py:682`, `PositionConfirmButton.callback`). The callback runs
`sync_to_async(save_positions)` (slow ORM) **before** any ACK, then
`interaction.response.edit_message(...)`; exceeding the ~3s window makes Discord
redeliver and the second delivery 40060s. This is a **distinct 40060 source**
from the router race the Dispatch section discusses (that one is a competing
dispatcher; this one is slow-work-before-ACK in a single callback). **Fix
(baked into the relocated provider methods):** the relocated `position_confirm`
— and its ORM-bearing siblings `rank_medal_select` / `rank_star_select` /
`battle_cup_select` — must **`await interaction.response.defer()` first** (plain
`defer()` = type-6 `DEFERRED_MESSAGE_UPDATE`, which updates the source ephemeral;
**not** `thinking=True`, which would spawn a new message — see
`signup_responses.py:8-23`), then do the ORM call, then
`interaction.edit_original_response(...)` instead of `response.edit_message(...)`.
Add a double-click guard (disable the Confirm button/selects on first activation
before the await). The bare `pos_select_` path is unaffected (it already defers
in `on_interaction`).

This means the composition spine's relocated methods change the ACK pattern
(defer-first) — a deliberate fix, not pure relocation. The "no behavior change"
goal already carries documented exceptions; these two join that list.

## Adding a game type (the extension checklist)

The DX goal is that a developer adding game type #3 (say CS2) months from now
follows a checklist and copies `dota.py`/`deadlock.py` as a template — without
re-reading the subsystem. The honest touch-point list (mirror this as a docstring
on **both** `registry.py` files so the dev finds it where they land):

1. `discordbot/components/<game>.py` — `<Game>Components` (build_signup_modal,
   `bare_select_ids`, operation methods + any follow-up View classes).
2. `events/discord/providers/<game>.py` — `<Game>Handler` (profile_complete,
   prefill, modal_config, apply_modal_submit; rank-flow methods only if needed).
3. `events/schemas.py` — `<Game>ModalConfig(SignupModalConfig)` with
   `kind: Literal["<game>"]`, **AND add it to the `ModalConfig` discriminated
   union alias.** (Skipping the union edit is silent — the config routes to base
   and loses its fields. The parametrized round-trip test below catches it.)
4. `app/models.py` `GameType` — add the member, **and sync
   `frontend/app/components/game/constants.ts`** per the enum's own docstring.
5. Register in `discordbot/components/registry.py` (`COMPONENT_PROVIDERS`).
6. Register in `events/discord/providers/registry.py` (`SIGNUP_HANDLERS`).
   (Steps 5+6 are guarded by the keyset-equality test — miss one and it goes red.)
7. `discordbot/custom_ids.py` — only if the game has unique interaction flows
   needing new codecs (a text-field game like Deadlock needs none).

Most steps fail loudly if missed (import asserts, the keyset test, the
parametrized round-trip test). Step 4's frontend sync and step 3's union edit are
the two that need the checklist + the round-trip test to stay safe.

## Logging & observability

The refactor relocates every logging-bearing callback and handler, so it must
preserve the `system`/`subsystem`/`tags` taxonomy and interaction correlation
(`telemetry.logging` / `discord_log_context`). Requirements:

1. **`discord_log_context` relocates with the operation body.** Each Dota
   component callback today wraps its whole body in `async with
   discord_log_context(interaction, custom_id=..., event_id=...) as ctx:` and
   calls `ctx.set_outcome(...)` / `ctx.add(...)`. When the body moves into a
   `DotaComponents.<operation>` method, **the method owns the CM** (it has the
   `interaction` + decoded `cid`) and keeps the `ctx` plumbing. The bound fields
   (`system="discord"`, `subsystem="interaction"`, `interaction_id`, `tags`,
   `event_id`, …) and the `interaction_started/finished/failed` bookends must be
   byte-identical. RSVP button callbacks in `base.py` keep their existing
   `discord_log_context` wrapping unchanged.

2. **`log_context.py` codec derivation covers all THREE uses, not just tags.**
   `_prefix()` feeds `resolve_tags()` (the `["events","signup"]` tags +
   `tags_csv`), `parse_event_id()` (the bound `event_id`), and `span_name()`
   (the OTel span `discord.interaction.<prefix>`). All three currently
   `custom_id.split(":")`. Route them through `custom_ids.py`: `event_id` from
   `CustomId.decode(...).event_id`, tags/span from a codec-derived prefix. The
   `pos_select_{slot}` shape (slot before the colon) is the trap (see Pydantic
   layer): with codec `PREFIX="pos_select"`, `span_name` becomes
   `discord.interaction.pos_select` (was `…pos_select_1`) — an acceptable
   granularity change, but `resolve_tags` membership must still match
   `pos_select_1:42` at runtime (`startswith("pos_select_")`), tested via the
   runtime `_prefix(...)` membership assertion.

3. **Give the relocated handler-layer logs `system`/`subsystem` + tags (fixes a
   pre-existing gap).** `handlers.py` logs (`handler_invoked`,
   `signup_persisted`, `signup_rejected`) carry **no `system`/`subsystem`** today
   — they run in the backend process and don't inherit the bot-process
   contextvars across the HTTP boundary. As these move into `providers/dota.py`
   etc., bind `system="discord"`, **`subsystem="interaction"`** (keep the
   subsystem stable — a Discord interaction spans concerns; do NOT mint a
   per-flow subsystem like `signup`), and differentiate the flow type via the
   **`tags`** list (`["events","signup"]`, plus `tags_csv`) — the multi-value
   cross-cutting axis. New interaction types add a tag, not a subsystem.
   Preserve the existing `bind_contextvars(org_user_id=..., user_id=...)` calls;
   `bind_contextvars` at handler entry is the natural place to set
   system/subsystem/tags since the bot-process context doesn't cross the HTTP
   boundary.

4. **Update the `logging` skill taxonomy doc in lockstep.** The skill's
   system/subsystem table (`.claude/skills/logging/SKILL.md`) names
   `discordbot/components.py` and `discordbot/log_context.py` under
   `discord`/`interaction` (tags `["events","signup"]`). After the split those
   paths become `discordbot/components/{base,dota,deadlock,default}.py` and
   `events/discord/providers/` — all still `discord`/`interaction`, tag-
   differentiated. Update the "Where" paths in the existing row; no new
   subsystem row. Same lockstep discipline as the brand skill.

## Testing

New:
- **Custom-id round-trip** (`discordbot/tests/`): `.encode()`/`.decode()`
  byte-for-byte; malformed → `ValueError`.
- **Registry keyset equality:** `set(COMPONENT_PROVIDERS) == set(SIGNUP_HANDLERS)`.
- **Parametrized modal_config round-trip (auto-covers new games):** iterate
  `SIGNUP_HANDLERS`, call each `handler.modal_config(<stub event>)`, and assert it
  survives `SignupActionResponse.model_validate(model_dump()).modal_config` with
  its subclass fields intact. A game added without the `ModalConfig` union edit
  (checklist step 3) fails this test immediately — turning the silent footgun into
  a red test for free.
- **`modal_config` type pin:** `DotaHandler.modal_config()` → `DotaModalConfig`;
  `DeadlockHandler` → `DeadlockModalConfig`.
- **`log_context` prefix parity** with the codec set, including the runtime
  `_prefix("pos_select_1:42") in _SIGNUP_TAG_PREFIXES` membership assertion (not
  just set-equality) and `parse_event_id`/`span_name` codec routing.
- **Handler-log taxonomy:** relocated provider/handler logs emit
  `system="discord"`, `subsystem="interaction"`, `tags=["events","signup"]`
  (via `capture_logs`), and the `discord_log_context` bookends still bind
  `interaction_id`/`tags`/`event_id`.
- **Per-endpoint forbid round-trip:** a representative payload from each of the
  13 producers passes `SignupActionResponse.model_validate` under
  `extra:"forbid"` (catches any producer still emitting a dropped key).
- **`dota_require_screenshot`** truth table (active/previous/never × flags).
- **Issue #268 bug 1:** `respond_to_signup_user` with `Forbidden(50007)` and no
  `view`/`embed` returns `EPHEMERAL`, calls `followup.send(ephemeral=True)` with
  the `<@user_id>` mention, and raises no `TypeError` (MISSING sentinel).
- **Issue #268 bug 2:** the ORM-bearing provider methods `defer()` *before* the
  `sync_to_async` call and use `edit_original_response` (not
  `response.edit_message`); a second delivery / double-click is a no-op.
- **Registry fallback path:** `get_component_provider(<unregistered>)` returns
  the default provider AND emits the `provider_fallback` `log.error` (assert via
  `capture_logs`). Same for `get_signup_handler`.
- **Rank-flow guard:** calling a rank-flow entry function
  (`handle_rank_medal_select` etc.) for a non-Dota event returns an `error`
  `SignupActionResponse` (the `isinstance(handler, DotaHandler)` guard).
- **Codec import guard:** a `CustomId` subclass without `PREFIX` raises at import
  (the `__init_subclass__` assert).

Update (enumerated from audit):
- `discordbot/tests/test_components.py` — imports + `EventSignupModal` →
  provider-built modal; patch target `discordbot.components.save_positions`.
- `discordbot/tests/test_signup_logging.py` — **patch-target migration:**
  `patch("discordbot.components.signup_button"|".respond_to_signup_user")` and
  `patch("events.discord.handlers._get_org_user")` → new defining modules.
- `discordbot/tests/test_log_context.py` — prefixes derived from codecs.
- `events/tests/test_signup_interactions.py` — largest handler test; imports 8
  handlers incl. `handle_set_position` / `handle_get_rank_flow_state`.
- `events/tests/test_signup_schema.py` — nested `modal_config`, `extra:"forbid"`,
  dropped `medal`/`tier`.
- `tests/test_events_discord.py` — imports 4 handlers.
- `app/tests/test_discord_reclaim.py` — `_get_org_user` now from `_shared`.

Regression: `just test::run 'python manage.py test app.tests events.tests discordbot.tests tests -v 2'`.

## PR sequencing (stacked, not big-bang)

To keep blast radius low and each change independently reviewable/revertible,
ship as three stacked PRs rather than one:

- **PR1 — bug 1 (`signup_responses.py` MISSING sentinel).** ~10 lines,
  independent of everything else, fixes live issue #268 (DM-disabled signup
  crash) immediately. Ship first.
- **PR2 — Pydantic contract tidy.** `DotaModalConfig`/`kind`/`ModalConfig`
  discriminated union + `extra:"forbid"` on `SignupActionResponse` + the
  producer edits (`handlers.py`: nest `modal_config`, drop `medal`/`tier`).
  Behavior-preserving, small diff, lands before the structural churn so the
  contract is stable when the providers arrive.
- **PR3 — the structural refactor.** `components/` + `providers/` packages,
  `custom_ids.py`, `log_context` rewrite, `bot.py` routing, `_shared.py`, and
  bug 2 (defer-first) — which lives in the relocated `position_confirm` /
  rank-flow methods, so it rides along naturally.

Each PR is green before the next stacks on it. A regression reverts one PR, not
all five changes.

## Caching invariants (cacheops)

The write models the providers touch are all in `CACHEOPS` (`settings.py`, 1h
TTL): `org.playerdeadlockprofile`, `org.playerdotaprofile`, `org.orguser`,
`events.event`, `events.eventsignup`, `events.eventrepeater`. The refactor is
invalidation-**neutral** — it adds no new cached model or `@cached_as` site —
but PR3's relocation must **preserve the three existing `invalidate_obj` calls**
(Deadlock profile save `:346`, Dota per-click `set_position` write `:773`,
event_repeater subscriber count `:670`). `handle_save_positions` invalidates via
`events.services` (`invalidate_after_commit`, not relocated) — not a direct call.
They are direct `invalidate_obj` (correct: the saves are outside
`transaction.atomic`; do not convert to `invalidate_after_commit`). A guard test
spies `invalidate_obj` on each relocated write path so a dropped call fails CI
instead of silently serving stale data for an hour.

## Migration / rollout

Pure internal reorganization. No DB migration. No custom-id format change
(round-trip test enforces it) — and no `add_view()`/startup view-registration
exists to update: RSVP buttons are posted as raw dicts and rebuilt from
`custom_id` per interaction in `on_interaction`, and the Dota follow-up views are
ephemeral (`timeout=300`, `store_view`'d on send), so neither survives restart by
design. The response change
(8 flags → nested `modal_config`, drop `medal`/`tier`) ships atomically with its
producers and consumers in one release; `extra:"forbid"` + the per-endpoint
round-trip test catch any miss. Old import paths preserved via
`components/__init__.py`; `patch()` targets updated where they bind to relocated
defining modules.

## Open items (resolve during planning)

- **Request schemas (`discordbot/schemas.py`):** if per-game `apply_modal_submit`
  changes the modal `values` shape, `SignupModalSubmitRequest.values` (untyped
  `dict`) may warrant a typed per-game model. Default: leave untyped (no
  behavior change). Also: `SignupModalSubmitRequest.game_type` becomes vestigial
  (dispatch now uses `event.game_type`) — keep it accepted-but-ignored, or drop
  it in a follow-up.
- **Stale working docs:** `docs/superpowers/plans/2026-05-03-...`,
  `2026-05-25-...` reference moved line numbers. Gitignored working docs —
  update only if convenient.

## Worktree parallelization (within PR3)

PRs are sequential (PR1 → PR2 → PR3). Within **PR3** there are two largely
independent lanes that can be built in parallel worktrees and merged:

| Lane | Modules | Depends on |
|---|---|---|
| A | `discordbot/custom_ids.py`, `discordbot/components/`, `discordbot/log_context.py`, `bot.py` | PR2 contract |
| B | `events/discord/providers/`, `events/discord/_shared.py`, `handlers.py` dispatch | PR2 contract |

Both lanes depend on PR2's `events/schemas.py` contract (the shared types), so
PR2 lands first; then A and B proceed in parallel and integrate at the
`signup_actions` HTTP boundary. Conflict risk is low (disjoint app directories);
the only shared file is `events/schemas.py`, already frozen by PR2.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run (internal refactor) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | scope reduced to 3-PR stack; 1 arch finding (deploy-skew) resolved; 3 test gaps added |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | CLEAR | TRIAGE, add-a-game lens: 5/10 → 8/10 (checklist + parametrized round-trip test) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a (backend) |
| Independent rounds | (Claude multi-agent) | Correctness/contract | 4 | CLEAR | 2 BLOCKERs caught + fixed (modal_config stripping, view-state loss); 1 DRF-serialization HIGH; bug fixes folded in |

- **UNRESOLVED:** 0
- **VERDICT:** ENG + DX CLEARED — ready to implement as the 3-PR stack (PR1 bug
  fix → PR2 contract → PR3 structural refactor).
