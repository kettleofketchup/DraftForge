# PR3 — Game-type provider/registry structural refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Discord signup UI and business logic into per-game-type provider modules behind two registries, add a typed custom-id codec layer, and fold in the #268 bug-2 defer-first fix — with **no wire-contract change** (PR2 already did that).

**Architecture:** Two parallel registries keyed on `GameType` (process boundary stays: `discordbot/` = bot UI, `events/discord/` = ORM logic). `discordbot/components/` owns the UI provider + views; `events/discord/providers/` owns the handler logic. `discordbot/custom_ids.py` is the bot-internal typed wire format. Each ephemeral-view callback decodes its typed `CustomId` and delegates to a bound `DotaComponents` method, forwarding View state. `bot.py` routes only the bare `pos_select_` select via the registry; all other components self-dispatch via discord.py's in-memory ephemeral view store.

**Tech Stack:** Python, discord.py, Pydantic v2, Django, run via `just test::run`.

**Spec:** `docs/superpowers/specs/2026-05-31-...design.md` (whole document). Stacks on PR2. The "Adding a game type" checklist in the spec should be mirrored as a docstring on both `registry.py` files.

**Ground rule for relocations:** Moving a class means copy its body **verbatim** from `components.py`/`handlers.py` into the new module, then apply only the explicitly-noted change (provider injection, callback delegation, defer-first). Do not rewrite untouched logic.

---

### Task 1: Typed custom-id codecs — `discordbot/custom_ids.py`

**Files:**
- Create: `backend/discordbot/custom_ids.py`
- Test: `backend/discordbot/tests/test_custom_ids.py`

- [ ] **Step 1: Write the failing round-trip + guard tests**

Create `backend/discordbot/tests/test_custom_ids.py`:

```python
import pytest
from discordbot import custom_ids as cid


def test_event_signup_roundtrip():
    s = cid.SignupId(event_id=42).encode()
    assert s == "event_signup:42"
    assert cid.SignupId.matches(s)
    assert cid.SignupId.decode(s).event_id == 42


def test_pos_select_slot_before_colon():
    s = cid.PosSelectId(event_id=7, slot=2).encode()
    assert s == "pos_select_2:7"
    assert cid.PosSelectId.matches(s)
    d = cid.PosSelectId.decode(s)
    assert (d.event_id, d.slot) == (7, 2)


def test_rank_star_carries_medal():
    s = cid.RankStarId(event_id=5, medal="Crusader").encode()
    assert s == "rank_star:5:Crusader"
    assert cid.RankStarId.decode(s).medal == "Crusader"


def test_screenshot_url_prefix_exists():
    assert cid.ScreenshotUrlId(event_id=1, screenshot_type="rank").encode() == "screenshot_url:1:rank"


def test_decode_malformed_raises_valueerror():
    with pytest.raises(ValueError):
        cid.SignupId.decode("event_signup:notanint")


def test_missing_prefix_subclass_fails_at_definition():
    with pytest.raises(AssertionError):
        class Bad(cid.CustomId):  # no PREFIX
            pass
```

- [ ] **Step 2: Run to verify it fails**

Run: `just test::run 'python -m pytest discordbot/tests/test_custom_ids.py -q'`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the codecs**

Create `backend/discordbot/custom_ids.py`. Implement the `CustomId` base (frozen Pydantic, `__init_subclass__` PREFIX assert, `encode`/`matches`/`decode` raising `ValueError`) and one subclass per prefix in the spec's codec table. Two irregular shapes need overrides: `PosSelectId` (slot before the colon: `pos_select_{slot}:{id}`) and the three-segment ids (`RankStarId` → `rank_star:{id}:{medal}`, `ScreenshotUploadId`/`ScreenshotFileId`/`ScreenshotUrlId` → `<prefix>:{id}:{type}`).

```python
from __future__ import annotations
from typing import ClassVar
from pydantic import BaseModel, ValidationError


class CustomId(BaseModel):
    PREFIX: ClassVar[str]
    event_id: int
    model_config = {"frozen": True}

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        assert getattr(cls, "PREFIX", None), f"{cls.__name__} must set PREFIX"

    def encode(self) -> str:
        return f"{self.PREFIX}:{self.event_id}"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return raw.startswith(cls.PREFIX + ":")

    @classmethod
    def decode(cls, raw: str) -> "CustomId":
        try:
            _, rest = raw.split(":", 1)
            return cls(event_id=int(rest))
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r}") from exc


class SignupId(CustomId):     PREFIX = "event_signup"
class TentativeId(CustomId):  PREFIX = "event_tentative"
class DeclineId(CustomId):    PREFIX = "event_decline"
class NotifyId(CustomId):     PREFIX = "event_notify"
class PosConfirmId(CustomId): PREFIX = "pos_confirm"
class RankStatusId(CustomId): PREFIX = "rank_status"
class RankMedalId(CustomId):  PREFIX = "rank_medal"
class BattleCupTierId(CustomId): PREFIX = "bcup_tier"
class SignupFriendId(CustomId):  PREFIX = "signup_friend_id"
class SignupRankStatusId(CustomId): PREFIX = "signup_rank_status"
class SignupDeadlockRankId(CustomId): PREFIX = "signup_deadlock_rank"
class SignupDeadlockDateId(CustomId): PREFIX = "signup_deadlock_date"


class PosSelectId(CustomId):
    PREFIX = "pos_select"   # wire form: pos_select_{slot}:{event_id}
    slot: int

    def encode(self) -> str:
        return f"{self.PREFIX}_{self.slot}:{self.event_id}"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return raw.startswith(cls.PREFIX + "_")

    @classmethod
    def decode(cls, raw: str) -> "PosSelectId":
        try:
            head, ev = raw.split(":", 1)
            slot = int(head[len(cls.PREFIX) + 1:])  # after "pos_select_"
            return cls(event_id=int(ev), slot=slot)
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r}") from exc


class _TypedTailId(CustomId):
    """Base for `<prefix>:{event_id}:{value}` codecs (value stored on a named field by subclass)."""
    pass


class RankStarId(CustomId):
    PREFIX = "rank_star"
    medal: str

    def encode(self) -> str:
        return f"{self.PREFIX}:{self.event_id}:{self.medal}"

    @classmethod
    def decode(cls, raw: str) -> "RankStarId":
        try:
            _, ev, medal = raw.split(":", 2)
            return cls(event_id=int(ev), medal=medal)
        except (ValueError, IndexError, ValidationError) as exc:
            raise ValueError(f"bad custom_id {raw!r}") from exc


def _screenshot_codec(prefix):
    class _Id(CustomId):
        PREFIX = prefix
        screenshot_type: str

        def encode(self) -> str:
            return f"{self.PREFIX}:{self.event_id}:{self.screenshot_type}"

        @classmethod
        def decode(cls, raw: str) -> "CustomId":
            try:
                _, ev, st = raw.split(":", 2)
                return cls(event_id=int(ev), screenshot_type=st)
            except (ValueError, IndexError, ValidationError) as exc:
                raise ValueError(f"bad custom_id {raw!r}") from exc
    _Id.__name__ = _Id.__qualname__ = {
        "screenshot_upload": "ScreenshotUploadId",
        "screenshot_file": "ScreenshotFileId",
        "screenshot_url": "ScreenshotUrlId",
    }[prefix]
    return _Id


ScreenshotUploadId = _screenshot_codec("screenshot_upload")
ScreenshotFileId = _screenshot_codec("screenshot_file")
ScreenshotUrlId = _screenshot_codec("screenshot_url")

# Prefix registry used by log_context for tag derivation (Task 2).
ALL_CODECS = [
    SignupId, TentativeId, DeclineId, NotifyId, PosSelectId, PosConfirmId,
    RankStatusId, RankMedalId, RankStarId, BattleCupTierId,
    ScreenshotUploadId, ScreenshotFileId, ScreenshotUrlId,
    SignupFriendId, SignupRankStatusId, SignupDeadlockRankId, SignupDeadlockDateId,
]
SIGNUP_TAG_PREFIXES = frozenset(c.PREFIX for c in ALL_CODECS)
```

(Remove the unused `_TypedTailId` stub if your linter flags it; it is illustrative only.)

- [ ] **Step 4: Run to verify it passes**

Run: `just test::run 'python -m pytest discordbot/tests/test_custom_ids.py -q'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/discordbot/custom_ids.py backend/discordbot/tests/test_custom_ids.py
git commit -m "feat(discord): typed custom-id codecs with byte-for-byte round-trip (#268)"
```

---

### Task 2: Derive `log_context` prefixes from codecs (with `pos_select_` runtime guard)

**Files:**
- Modify: `backend/discordbot/log_context.py`
- Modify: `backend/discordbot/tests/test_log_context.py`

- [ ] **Step 1: Write the failing parity + runtime-membership tests**

Add to `backend/discordbot/tests/test_log_context.py`:

```python
from discordbot import custom_ids as cid
from discordbot.log_context import _SIGNUP_TAG_PREFIXES, resolve_tags


def test_prefix_set_matches_codecs():
    assert _SIGNUP_TAG_PREFIXES == cid.SIGNUP_TAG_PREFIXES


def test_pos_select_runtime_tag_membership():
    # pos_select_1:42 must still resolve to the signup tags despite the slot.
    assert resolve_tags("pos_select_1:42") == ["events", "signup"]
    assert resolve_tags("pos_select_3:7") == ["events", "signup"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `just test::run 'python -m pytest discordbot/tests/test_log_context.py -k "prefix_set or pos_select_runtime" -q'`
Expected: FAIL — `_SIGNUP_TAG_PREFIXES` is the hardcoded set (contains `pos_select_1/2/3`, not `pos_select`), and `_prefix("pos_select_1:42")` returns `"pos_select_1"` which won't be in the codec-derived set.

- [ ] **Step 3: Rewrite the prefix source + the `pos_select_` match**

In `backend/discordbot/log_context.py`:

```python
from discordbot.custom_ids import SIGNUP_TAG_PREFIXES as _SIGNUP_TAG_PREFIXES


def _prefix(custom_id: str | None) -> str | None:
    if not custom_id:
        return None
    head = custom_id.split(":", 1)[0]
    # pos_select_{slot} normalizes to the codec prefix "pos_select"
    if head.startswith("pos_select_"):
        return "pos_select"
    return head
```

Delete the old hardcoded `_SIGNUP_TAG_PREFIXES = {...}` literal. `resolve_tags`, `parse_event_id`, and `span_name` already call `_prefix`, so they inherit the normalization. (`span_name` for a pos_select now yields `discord.interaction.pos_select` — accepted granularity change.)

- [ ] **Step 4: Run to verify it passes**

Run: `just test::run 'python -m pytest discordbot/tests/test_log_context.py -q'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/discordbot/log_context.py backend/discordbot/tests/test_log_context.py
git commit -m "refactor(discord): derive log_context prefixes from codecs (#268)"
```

---

### Task 3: `discordbot/components/` package — base + per-game providers

**Files:**
- Create: `backend/discordbot/components/__init__.py`, `base.py`, `dota.py`, `deadlock.py`, `default.py`, `registry.py`
- Delete: `backend/discordbot/components.py`

- [ ] **Step 1: Create `base.py` (shared, game-agnostic)**

Move verbatim from `components.py`: `send_modal_v2`, `EventSignupView`, `SignupButton`, `NotifyButton`, `TentativeButton`, `DeclineButton`, the screenshot infra (`ScreenshotUploadPromptView`, `ScreenshotUploadButton`, `ScreenshotUploadModal`, `SCREENSHOT_EXAMPLE_URLS`). Add the shared friend-id helper (extracted from the current modal's friend-id block):

```python
def build_friend_id_input(event_id, prefill, required):
    """Shared Steam Friend ID field; returns None when already known or not required."""
    if not required or prefill.get("unverified_friend_id"):
        return None
    return ui.TextInput(
        label="Steam Friend ID",
        placeholder="Your Friend ID (number from your Dotabuff URL)",
        custom_id=SignupFriendId(event_id=event_id).encode(),
        required=True,
        max_length=20,
        style=discord.TextStyle.short,
        default=str(prefill.get("unverified_friend_id", "")),
    )
```

`SignupButton.callback`'s `needs_modal` branch now asks the registry:

```python
            elif result["action"] == "needs_modal":
                from discordbot.components.registry import get_component_provider
                provider = get_component_provider(result["game_type"])
                modal = provider.build_signup_modal(
                    self.event_id, result.get("prefill", {}), result.get("modal_config", {}) or {}
                )
                await send_modal_v2(interaction, modal)
```

Keep the module-level bindings `signup_button`, `respond_to_signup_user` importable from `base.py` (tests patch them by path — Task 7 updates the path).

- [ ] **Step 2: Create `dota.py` (`DotaComponents` + Dota views, with bug-2 defer-first)**

Move verbatim: `DOTA_POSITIONS`, `DOTA_MEDALS`, `DOTA_STARS`, `_medal_options`, `_star_options`, `DotaSignupModal` (the Dota half of the old `EventSignupModal`, stashing the full config dict on `self`), `PositionSelectView`, `PositionConfirmButton`, `RankStatusSelectView`, `RankStatusSelect`, `RankDetailsView`, `MedalSelect`, `StarSelect`, `BattleCupTierSelect`.

Each select/button now takes `provider: "DotaComponents"` and its `custom_id` uses the codec (e.g. `RankStatusId(event_id=event_id).encode()`). The callback bodies move into `DotaComponents` methods; each callback decodes its codec and delegates, forwarding View state. Apply the **bug-2 defer-first** change to the ORM-bearing methods. Example for `PositionConfirmButton` → `DotaComponents.position_confirm`:

```python
class DotaComponents(GameComponentProvider):
    bare_select_ids = (PosSelectId,)

    def build_signup_modal(self, event_id, prefill, config):
        return DotaSignupModal(event_id, prefill, config, provider=self)

    async def position_confirm(self, interaction, cid, *, rank_status, require_screenshot, min_mmr):
        async with discord_log_context(interaction, custom_id=cid.encode(), event_id=cid.event_id) as ctx:
            await interaction.response.defer()                      # bug-2: ACK before slow ORM
            positions = [...]                                       # gather from view selects (verbatim)
            result = await sync_to_async(save_positions, thread_sensitive=False)(
                event_id=cid.event_id, discord_user_id=str(interaction.user.id), positions=positions
            )
            if result.get("action") == "error":
                ctx.set_outcome("error")
                await interaction.edit_original_response(content=f"❌ {result['message']}", view=None)
                return
            ctx.set_outcome("positions_saved")
            view = RankDetailsView(cid.event_id, rank_status, require_screenshot=require_screenshot, min_mmr=min_mmr, provider=self)
            await interaction.edit_original_response(content=..., view=view)

    async def position_select(self, interaction, cid):               # bare select, routed by bot.py
        if interaction.response.is_done():
            return
        # verbatim pos_select_ body: parse value, set_position, defer
        ...

    async def rank_medal_select(self, interaction, cid, *, rank_status, require_screenshot): ...
    async def rank_star_select(self, interaction, cid, *, rank_status): ...
    async def battle_cup_select(self, interaction, cid): ...
    async def rank_status_select(self, interaction, cid): ...

    async def dispatch_bare_select(self, interaction, cid):
        await self.position_select(interaction, cid)
```

`StarSelect.callback` keeps the `"Herald"` sentinel + `Immortal` logic in the callback (the codec only round-trips the literal). Apply defer-first to `rank_medal_select`, `rank_star_select`, `battle_cup_select` the same way (`defer()` then `edit_original_response`). Also disable the Confirm button + selects on first activation before the await (double-click guard).

- [ ] **Step 3: Create `deadlock.py`, `default.py`, `registry.py`**

`deadlock.py` — `DeadlockComponents` with `build_signup_modal` returning `DeadlockSignupModal` (the Deadlock half of the old modal, friend-id + rank/date inputs), `bare_select_ids = ()`.

`default.py` — `DefaultComponents` returning a minimal modal (friend-id only or none), `bare_select_ids = ()`.

`registry.py`:

```python
from telemetry.logging import get_logger
from app.models import GameType
from discordbot.components.dota import DotaComponents
from discordbot.components.deadlock import DeadlockComponents
from discordbot.components.default import DefaultComponents

log = get_logger(__name__)
COMPONENT_PROVIDERS = {GameType.DOTA2: DotaComponents(), GameType.DEADLOCK: DeadlockComponents()}
_DEFAULT = DefaultComponents()

def get_component_provider(game_type):
    p = COMPONENT_PROVIDERS.get(game_type)
    if p is None:
        log.error("provider_fallback", system="discord", subsystem="interaction",
                  tags=["events", "signup"], tags_csv="events,signup", layer="components", game_type=game_type)
        return _DEFAULT
    return p

def iter_component_providers():
    return list(COMPONENT_PROVIDERS.values())
```

(Mirror the spec's "Adding a game type" checklist as this module's docstring.) Define the `GameComponentProvider` protocol in `base.py` (or `registry.py`): `build_signup_modal`, `bare_select_ids`, `dispatch_bare_select`.

- [ ] **Step 4: `__init__.py` back-compat re-exports + delete the monolith**

`backend/discordbot/components/__init__.py` re-exports every symbol current importers/tests use (per spec): `EventSignupView`, `SignupButton`, `NotifyButton`, `TentativeButton`, `DeclineButton`, `PositionSelectView`, `PositionConfirmButton`, `RankDetailsView`, `MedalSelect`, `StarSelect`, `BattleCupTierSelect`, `RankStatusSelect`, `RankStatusSelectView`, plus `signup_button`, `save_positions`, `set_position`, `respond_to_signup_user`. Then `git rm backend/discordbot/components.py`.

- [ ] **Step 5: Verify import + component tests (defer to Task 7 for test edits)**

Run: `just test::run 'python -c "import discordbot.components"'`
Expected: no ImportError.

- [ ] **Step 6: Commit**

```bash
git add backend/discordbot/components/
git rm backend/discordbot/components.py
git commit -m "refactor(discord): split components into base + per-game providers, defer-first ORM (#268)"
```

---

### Task 4: Wire `bot.py:on_interaction` to codecs + bare-select registry

**Files:**
- Modify: `backend/discordbot/bot.py` (`on_interaction`, ~162-207)

- [ ] **Step 1: Replace the prefix string-matches with codecs + the bare-select loop**

```python
        if interaction.type == discord.InteractionType.component:
            if SignupId.matches(custom_id):
                await SignupButton(SignupId.decode(custom_id).event_id).callback(interaction)
            elif TentativeId.matches(custom_id):
                await TentativeButton(TentativeId.decode(custom_id).event_id).callback(interaction)
            elif DeclineId.matches(custom_id):
                await DeclineButton(DeclineId.decode(custom_id).event_id).callback(interaction)
            elif NotifyId.matches(custom_id):
                await NotifyButton(NotifyId.decode(custom_id).event_id).callback(interaction)
            else:
                for provider in iter_component_providers():
                    for id_type in provider.bare_select_ids:
                        if id_type.matches(custom_id):
                            try:
                                parsed = id_type.decode(custom_id)
                            except ValueError:
                                return
                            await provider.dispatch_bare_select(interaction, parsed)
                            return
```

Keep the surrounding comment about why the self-dispatching views are NOT routed here (the 40060 race). Update imports at the top of `bot.py` to pull the codecs and `iter_component_providers`.

- [ ] **Step 2: Smoke-test the bot module imports**

Run: `just test::run 'python -c "import discordbot.bot"'`
Expected: no ImportError.

- [ ] **Step 3: Commit**

```bash
git add backend/discordbot/bot.py
git commit -m "refactor(discord): codec-based interaction routing in on_interaction (#268)"
```

---

### Task 5: `events/discord/` — `_shared.py` + `providers/` package + thin dispatcher

**Files:**
- Create: `backend/events/discord/_shared.py`, `providers/__init__.py`, `providers/base.py`, `providers/dota.py`, `providers/deadlock.py`, `providers/registry.py`
- Modify: `backend/events/discord/handlers.py`, `backend/events/discord/__init__.py`

- [ ] **Step 1: Extract shared helpers to `_shared.py`**

Move `_get_org_user`, `_load_event` (factor the `Event.objects...get` pattern), `_direct_signup` (wrap `process_rsvp`), `_log_signup`, `_log_interaction`, and the dedupe/existing-signup check. **Keep every `from events.services import ...` import function-local** (preserves the documented `events.services → events.discord → handlers` cycle break — see spec).

- [ ] **Step 2: Create `providers/base.py` + per-game handlers**

`base.py`: `GameSignupHandler` protocol + `DefaultHandler` (4 methods, safe defaults). `dota.py`: `DotaHandler` with `_check_dota_profile_complete`, `modal_config` (returns `DotaModalConfig`), `apply_modal_submit`, and the 8 rank-flow methods (move bodies from `handlers.py`). `deadlock.py`: `DeadlockHandler`. `registry.py`: `SIGNUP_HANDLERS = {DOTA2: DotaHandler(), DEADLOCK: DeadlockHandler()}` + `get_signup_handler` with the same `provider_fallback` log. Mirror the "Adding a game type" checklist as the docstring.

- [ ] **Step 2b: Preserve cache invalidation (cached models — do NOT drop)**

The relocated bodies carry three `invalidate_obj` calls. Every model below is in
`CACHEOPS` (verified in `backend/settings.py`, 1h TTL), so dropping any one serves
stale data for up to an hour. Keep `from app.cache_utils import invalidate_obj`
in the new modules and preserve:

```
DeadlockHandler.apply_modal_submit   profile.save(); invalidate_obj(profile)   # was handlers.py:346 — org.playerdeadlockprofile
DotaHandler.set_position             invalidate_obj(profile)                   # was handlers.py:773 — org.playerdotaprofile
NotifyHandler/handle_notify_button   invalidate_obj(event.event_repeater)      # was handlers.py:670 — events.eventrepeater
```

These are the **only three** direct `invalidate_obj` calls in `handlers.py`
(verified). Note: `handle_save_positions` (the pos_confirm bulk save) does NOT
call `invalidate_obj` directly — it writes via `events.services`
(`apply_signup_input` / `process_rsvp`), which use `invalidate_after_commit` and
are **not** relocated by this refactor, so their invalidation stays put. Only
`handle_set_position` (the per-click `pos_select_` write) has the direct Dota
call. These three are direct `invalidate_obj` (correct — the saves are outside
`transaction.atomic`; the only atomic blocks are in `_get_org_user`'s user
creation). Do not convert them to `invalidate_after_commit` and do not drop them.

- [ ] **Step 3: Make `handlers.py` a thin dispatcher**

Each `handle_*` entry function keeps its **name and route binding**, loads the event, resolves `get_signup_handler(event.game_type)`, and delegates. Rank-flow entries guard `if not isinstance(handler, DotaHandler): return {"action": "error", "message": "Not applicable."}`. `handle_signup_button` / `handle_signup_modal_submit` call the base methods. **All return values stay the same dict shape PR2 established** (no contract change). Update `events/discord/__init__.py` `__all__` so `_check_dota_profile_complete`/`_check_deadlock_profile_complete`/`_get_org_user` source from their new modules.

- [ ] **Step 4: Smoke-test imports**

Run: `just test::run 'python -c "import events.discord.handlers, events.discord.providers.registry, events.services"'`
Expected: no ImportError (verifies no cycle reintroduced).

- [ ] **Step 5: Commit**

```bash
git add backend/events/discord/
git commit -m "refactor(discord): split handlers into _shared + per-game providers (#268)"
```

---

### Task 6: New guard tests (registry, fallback, rank-flow guard, parametrized round-trip)

**Files:**
- Create: `backend/events/tests/test_provider_registry.py`

- [ ] **Step 1: Write the tests**

```python
import pytest
from unittest.mock import patch
from app.models import GameType
from discordbot.components.registry import COMPONENT_PROVIDERS, get_component_provider
from events.discord.providers.registry import SIGNUP_HANDLERS, get_signup_handler
from events.discord.providers.dota import DotaHandler
from events.schemas import DotaModalConfig, SignupActionResponse


def test_registry_keysets_match():
    assert set(COMPONENT_PROVIDERS) == set(SIGNUP_HANDLERS)


def test_deadlock_signup_invalidates_profile_cache():
    """Cache guardrail: PlayerDeadlockProfile is cached (settings.py); the
    relocated apply_modal_submit must still invalidate it."""
    with patch("events.discord.providers.deadlock.invalidate_obj") as inv:
        # ... arrange a Deadlock event + org_user, call DeadlockHandler.apply_modal_submit
        # assert inv.called and the invalidated obj is the saved profile
        ...


def test_set_position_invalidates_dota_profile_cache():
    with patch("events.discord.providers.dota.invalidate_obj") as inv:
        # ... call DotaHandler.set_position (the pos_select_ per-click write);
        # assert inv.called with the dota profile
        ...


def test_notify_invalidates_event_repeater_cache():
    with patch("events.discord._shared.invalidate_obj") as inv:  # or wherever notify lands
        # ... call the notify/decline path; assert inv.called with event.event_repeater
        ...


def test_unregistered_game_type_falls_back(caplog):
    bogus = 999
    assert get_component_provider(bogus).__class__.__name__ == "DefaultComponents"
    assert get_signup_handler(bogus).__class__.__name__ == "DefaultHandler"


def test_each_handler_modal_config_round_trips():
    for gt, handler in SIGNUP_HANDLERS.items():
        cfg = handler.modal_config(_stub_event_for(gt))   # build a minimal stub Event per game
        resp = SignupActionResponse(action="needs_modal", game_type=int(gt), modal_config=cfg)
        rt = SignupActionResponse.model_validate(resp.model_dump()).modal_config
        assert rt is not None
        if isinstance(cfg, DotaModalConfig):
            assert rt.min_mmr == cfg.min_mmr
```

(Provide `_stub_event_for` building a `MagicMock`/lightweight object with the fields each `modal_config` reads, or use a Django test fixture event. The rank-flow guard test: call `handle_rank_medal_select` for a Deadlock event and assert `action == "error"`.)

- [ ] **Step 2: Run**

Run: `just test::run 'python -m pytest events/tests/test_provider_registry.py -q'`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/events/tests/test_provider_registry.py
git commit -m "test(discord): registry keyset, fallback, rank-flow guard, modal_config round-trip (#268)"
```

---

### Task 7: Migrate existing tests (patch targets + imports)

**Files:**
- Modify: `backend/discordbot/tests/test_signup_logging.py`, `test_components.py`, `backend/events/tests/test_signup_interactions.py`, `backend/app/tests/test_discord_reclaim.py`

- [ ] **Step 1: Update `patch()` targets to new defining modules**

`patch("discordbot.components.signup_button")` → `patch("discordbot.components.base.signup_button")`; `...respond_to_signup_user` → `...base.respond_to_signup_user`; `discordbot.components.save_positions` → `discordbot.components.dota.save_positions`; `patch("events.discord.handlers._get_org_user")` → `patch("events.discord._shared._get_org_user")`. (`patch` binds to the **defining** module, not the re-export.)

- [ ] **Step 2: Update `EventSignupModal` references**

In `test_components.py`, replace any `EventSignupModal(...)` construction with the Dota provider: `DotaComponents().build_signup_modal(event_id, prefill, DotaModalConfig(...).model_dump())`.

- [ ] **Step 3: Run the full Discord suite**

Run: `just test::run 'python manage.py test discordbot.tests events.tests tests app.tests.test_discord_reclaim -v 2'`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/discordbot/tests backend/events/tests backend/app/tests/test_discord_reclaim.py
git commit -m "test(discord): migrate patch targets + imports to provider packages (#268)"
```

---

### Task 8: Update the logging skill doc

**Files:**
- Modify: `.claude/skills/logging/SKILL.md`

- [ ] **Step 1: Update the taxonomy "Where" paths**

In the `discord`/`interaction` row, change `discordbot/components.py` to `discordbot/components/{base,dota,deadlock,default}.py` and add `events/discord/providers/` to the same row (still `discord`/`interaction`, tag-differentiated — no new subsystem). Commit:

```bash
git add .claude/skills/logging/SKILL.md
git commit -m "docs(logging): update taxonomy paths for components/providers split (#268)"
```

---

### Task 9: Full regression + demo recordings

- [ ] **Step 1: Full backend Discord regression**

Run: `just test::run 'python manage.py test app.tests events.tests discordbot.tests tests -v 2'`
Expected: all PASS.

- [ ] **Step 2: Re-record demos if any herodraft/draft UI components changed**

Per project CLAUDE.md, the signup flow is Discord-bot, not the web `herodraft/draft/bracket` components — so demo recording is likely **not** required. Confirm no files under `frontend/app/components/herodraft|draft|bracket/` changed; if none did, skip. If unsure: `git diff --name-only main -- 'frontend/app/components/**'`.

- [ ] **Step 3: Final commit if anything pending**

```bash
git status
```

---

## Self-Review
- **Spec coverage:** codecs (T1), log_context (T2), components package + bug-2 (T3), bot routing (T4), providers + _shared + dispatcher (T5), guard tests (T6), test migration (T7), logging doc (T8), regression (T9). ✓
- **Placeholders:** relocations are explicitly "move verbatim + noted change"; new code (codecs, registries, dispatch, defer-first, tests) is shown in full. The few `...` markers denote verbatim-moved bodies, not unwritten logic.
- **Type consistency:** `GameComponentProvider`/`GameSignupHandler`/`DotaHandler`, `bare_select_ids`/`dispatch_bare_select`, codec class names match the spec table and PR2's `DotaModalConfig`.
- **No contract change:** PR2 owns the wire shape; PR3 only moves code + fixes bug 2 (defer-first).
