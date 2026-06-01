# PR2 — Pydantic `modal_config` contract (discriminated union) on the monolith

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the eight flat Dota config flags (and the write-only `medal`/`tier`) on `SignupActionResponse` with a single `kind`-discriminated `modal_config` sub-model, tighten the envelope to `extra:"forbid"`, and centralize the screenshot-required ternary — all in place on the current monolith, behavior-preserving.

**Architecture:** With `modal_config: SignupModalConfig | None`, Pydantic v2 serializes by the declared base type and drops subclass fields on the `model_validate→model_dump` wire path (empirically verified). A `kind`-discriminated union (`DotaModalConfig | DeadlockModalConfig | SignupModalConfig`) round-trips intact. Producers in `handlers.py` nest the config; the consumer in `components.py` reads `result["modal_config"]`. No structural file moves here — that is PR3.

**Tech Stack:** Pydantic v2, Django, discord.py, run via `just test::run`.

**Spec:** `docs/superpowers/specs/2026-05-31-...design.md` → "Pydantic data layer", "Per-game modal config", "Tidied response envelope", "dota_require_screenshot". Depends on nothing; PR3 stacks on this.

**Deploy note:** `extra:"forbid"` turns a backend↔bot version skew into a crash. This PR's two containers MUST deploy from the same release tag (the existing release model). See spec "Deploy-skew note".

---

### Task 1: Add the config models + union + `dota_require_screenshot` to `events/schemas.py`

**Files:**
- Modify: `backend/events/schemas.py`
- Test: `backend/events/tests/test_signup_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/events/tests/test_signup_schema.py`:

```python
from typing import get_args

from events.schemas import (
    DeadlockModalConfig,
    DotaModalConfig,
    SignupModalConfig,
    dota_require_screenshot,
)


def test_dota_modal_config_has_kind_dota():
    cfg = DotaModalConfig(min_mmr=3000, allow_active_mmr=False)
    assert cfg.kind == "dota"
    assert cfg.min_mmr == 3000


def test_deadlock_modal_config_kind():
    assert DeadlockModalConfig().kind == "deadlock"


def test_base_modal_config_kind_default():
    assert SignupModalConfig().kind == "default"


def test_dota_require_screenshot_truth_table():
    cfg = DotaModalConfig(require_rank_screenshot=True, require_battlecup_screenshot=True)
    assert dota_require_screenshot("active", cfg) is True
    assert dota_require_screenshot("never", cfg) is True
    assert dota_require_screenshot("previous", cfg) is False
    cfg_off = DotaModalConfig(require_rank_screenshot=False, require_battlecup_screenshot=False)
    assert dota_require_screenshot("active", cfg_off) is False
    assert dota_require_screenshot("never", cfg_off) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `just test::run 'python -m pytest events/tests/test_signup_schema.py -k modal_config -q'`
Expected: FAIL — `ImportError: cannot import name 'DotaModalConfig'`.

- [ ] **Step 3: Add the models + function to `backend/events/schemas.py`**

Near the top, ensure these imports exist (the module already imports from `pydantic`):

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field
```

Add (place above `SignupActionResponse`):

```python
class SignupModalConfig(BaseModel):
    """Base / default game config carried in the needs_modal response."""

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


# Discriminated union — required so model_validate(dict)->model_dump() keeps
# subclass fields. A plain `SignupModalConfig` annotation drops them.
ModalConfig = Annotated[
    DotaModalConfig | DeadlockModalConfig | SignupModalConfig,
    Field(discriminator="kind"),
]


def dota_require_screenshot(rank_status: str, cfg: DotaModalConfig) -> bool:
    """Single home for the screenshot-required rule (was duplicated in
    components.py and handle_get_rank_flow_state)."""
    if rank_status == "active":
        return cfg.require_rank_screenshot
    if rank_status == "never":
        return cfg.require_battlecup_screenshot
    return False
```

- [ ] **Step 4: Run to verify it passes**

Run: `just test::run 'python -m pytest events/tests/test_signup_schema.py -k modal_config -q'`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/events/schemas.py backend/events/tests/test_signup_schema.py
git commit -m "feat(schemas): add discriminated ModalConfig union + dota_require_screenshot (#268)"
```

---

### Task 2: Reshape `SignupActionResponse` (nest modal_config, drop medal/tier, forbid)

**Files:**
- Modify: `backend/events/schemas.py` (`SignupActionResponse`, lines ~266-308)
- Test: `backend/events/tests/test_signup_schema.py`

- [ ] **Step 1: Write the failing round-trip test**

Append to `backend/events/tests/test_signup_schema.py`:

```python
from events.schemas import SignupActionResponse


def test_modal_config_survives_validate_then_dump():
    """The wire path is model_validate(dict).model_dump() in signup_actions.py."""
    resp = SignupActionResponse(
        action="needs_modal",
        game_type=1,
        modal_config=DotaModalConfig(min_mmr=2500, require_rank_screenshot=True),
    )
    wire = resp.model_dump()
    rt = SignupActionResponse.model_validate(wire).model_dump()
    assert rt["modal_config"]["kind"] == "dota"
    assert rt["modal_config"]["min_mmr"] == 2500
    assert rt["modal_config"]["require_rank_screenshot"] is True


def test_response_forbids_legacy_flat_keys():
    with pytest.raises(PydanticValidationError):
        SignupActionResponse.model_validate(
            {"action": "needs_modal", "game_type": 1, "min_mmr": 3000}
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `just test::run 'python -m pytest events/tests/test_signup_schema.py -k "modal_config_survives or forbids_legacy" -q'`
Expected: FAIL — current model has flat `min_mmr` and `extra:"ignore"`.

- [ ] **Step 3: Reshape the model**

Replace the field block in `SignupActionResponse` (everything from `prefill: dict | None = None` through `positions: list[int] | None = None` and `model_config`) with:

```python
    prefill: dict | None = None
    modal_config: "ModalConfig | None" = None      # was 8 flat Dota flags
    screenshot_type: str | None = None              # stays FLAT (views bracket-index it)
    subscribed: bool | None = None
    success: bool | None = None
    signed_up: bool | None = None
    positions: list[int] | None = None

    model_config = {"extra": "forbid"}              # was "ignore"
```

(Removes `require_steam_id`, `require_rank_screenshot`, `require_battlecup_screenshot`, `min_mmr`, `allow_active_mmr`, `allow_previous_rank`, `allow_battlecup_rating`, `medal`, `tier`. `ModalConfig` is defined above in this module, so the forward-ref string resolves; if the module already calls `model_rebuild()` anywhere keep it, otherwise no rebuild is needed since `ModalConfig` is in scope.)

- [ ] **Step 4: Run to verify it passes**

Run: `just test::run 'python -m pytest events/tests/test_signup_schema.py -q'`
Expected: PASS (all schema tests).

- [ ] **Step 5: Commit**

```bash
git add backend/events/schemas.py backend/events/tests/test_signup_schema.py
git commit -m "feat(schemas): nest modal_config, drop medal/tier, extra:forbid on SignupActionResponse (#268)"
```

---

### Task 3: Update producers in `handlers.py` (nest config, drop medal/tier)

**Files:**
- Modify: `backend/events/discord/handlers.py` — `handle_signup_button` (~256-275), `handle_rank_medal_select` (~433-437), `handle_previous_rank_submit` (~490-494), `handle_battle_cup_submit` (~545-549), `handle_get_rank_flow_state` (~799-807)

- [ ] **Step 1: Update `handle_signup_button`'s needs_modal return**

Add to the imports at the top of `handlers.py` (module-level, not function-local):

```python
from events.schemas import DeadlockModalConfig, DotaModalConfig, SignupModalConfig
```

Replace the `return {"action": "needs_modal", ...}` block (the dict with the 8 flat flags) with a per-game config build, then nest its dump:

```python
    if event.game_type == GameType.DOTA2:
        modal_config = DotaModalConfig(
            require_steam_id=event.require_steam_id,
            require_rank_screenshot=event.discord_require_rank_screenshot,
            require_battlecup_screenshot=event.discord_require_battlecup_screenshot,
            min_mmr=event.min_mmr,
            allow_active_mmr=event.allow_active_mmr,
            allow_previous_rank=event.allow_previous_rank,
            allow_battlecup_rating=event.allow_battlecup_rating,
        )
    elif event.game_type == GameType.DEADLOCK:
        modal_config = DeadlockModalConfig(require_steam_id=event.require_steam_id)
    else:
        modal_config = SignupModalConfig(require_steam_id=event.require_steam_id)

    _log_interaction(event_id, "signup_modal_opened", discord_user_id, discord_username)
    return {
        "action": "needs_modal",
        "game_type": event.game_type,
        "prefill": {
            "unverified_friend_id": getattr(
                getattr(org_user, "dota_profile", None), "unverified_friend_id", ""
            )
            or getattr(
                getattr(org_user, "deadlock_profile", None), "unverified_friend_id", ""
            )
            or "",
        },
        "modal_config": modal_config.model_dump(),
    }
```

- [ ] **Step 2: Drop `medal`/`tier` from the three screenshot producers**

In `handle_rank_medal_select` and `handle_previous_rank_submit`, the `needs_screenshot` return currently includes `"medal": medal`. Remove that key:

```python
            return {"action": "needs_screenshot", "screenshot_type": "rank"}
```

In `handle_battle_cup_submit`, remove `"tier": tier`:

```python
            return {"action": "needs_screenshot", "screenshot_type": "battlecup"}
```

(The `medal`/`tier` locals are still used elsewhere in those functions for persistence — only the returned response keys are dropped.)

- [ ] **Step 3: Route `handle_get_rank_flow_state` through `dota_require_screenshot`**

Replace its inline ternary (the `require_screenshot = ( ... if rank_status == "active" else ... )` block) with:

```python
    from events.schemas import DotaModalConfig, dota_require_screenshot

    cfg = DotaModalConfig(
        require_rank_screenshot=event.discord_require_rank_screenshot,
        require_battlecup_screenshot=event.discord_require_battlecup_screenshot,
    )
    require_screenshot = dota_require_screenshot(rank_status, cfg)
```

- [ ] **Step 4: Run the handler interaction tests**

Run: `just test::run 'python manage.py test events.tests.test_signup_interactions -v 2'`
Expected: tests that assert the old flat keys will FAIL — fix them in Task 5. Tests not asserting on config shape PASS. Note which fail.

- [ ] **Step 5: Commit**

```bash
git add backend/events/discord/handlers.py
git commit -m "feat(discord): producers emit nested modal_config, drop medal/tier (#268)"
```

---

### Task 4: Update the consumer in `components.py` (read nested modal_config)

**Files:**
- Modify: `backend/discordbot/components.py` — `SignupButton.callback` (~169-188), `EventSignupModal.__init__`/`_add_dota_fields` (~307, ~367), `EventSignupModal.on_submit` (~444-457)

- [ ] **Step 1: Read modal_config in `SignupButton.callback`**

The `needs_modal` branch currently builds `event_config={...}` from `result.get("require_steam_id")` etc. Replace that dict construction with the nested config:

```python
            elif result["action"] == "needs_modal":
                modal = EventSignupModal(
                    event_id=self.event_id,
                    game_type=result["game_type"],
                    prefill=result.get("prefill", {}),
                    event_config=result.get("modal_config", {}) or {},
                )
                await send_modal_v2(interaction, modal)
```

(`event_config` is now the `modal_config` dict, whose keys are the same names — `require_steam_id`, `min_mmr`, `require_rank_screenshot`, etc. — so the existing `self.event_config.get("...")` reads downstream keep working unchanged.)

- [ ] **Step 2: Replace the inline screenshot ternary in `on_submit`**

In `EventSignupModal.on_submit`, the `needs_rank_details` branch computes `require_screenshot` via a nested ternary on `self.event_config`. Replace it with the shared function:

```python
            if result["action"] == "needs_rank_details":
                from events.schemas import DotaModalConfig, dota_require_screenshot

                rank_status = values.get("rank_status", "never")
                cfg = DotaModalConfig(**{
                    k: v for k, v in self.event_config.items()
                    if k in DotaModalConfig.model_fields
                })
                require_screenshot = dota_require_screenshot(rank_status, cfg)
                view = PositionSelectView(
                    self.event_id,
                    rank_status,
                    require_screenshot=require_screenshot,
                    min_mmr=self.event_config.get("min_mmr"),
                )
                ...
```

(Keep the rest of the branch — the `send_message(..., view=view, ephemeral=True)` — unchanged.)

- [ ] **Step 3: Run the component + signup-logging suites**

Run: `just test::run 'python manage.py test discordbot.tests.test_components discordbot.tests.test_signup_logging -v 2'`
Expected: PASS (these don't assert the wire config shape; verify no regression).

- [ ] **Step 4: Commit**

```bash
git add backend/discordbot/components.py
git commit -m "feat(discord): consume nested modal_config in signup modal (#268)"
```

---

### Task 5: Fix handler tests that asserted the old flat shape

**Files:**
- Modify: `backend/events/tests/test_signup_interactions.py`, `backend/tests/test_events_discord.py` (only the assertions that read flat config/`medal`/`tier`)

- [ ] **Step 1: Update assertions**

For any test asserting `result["min_mmr"]` / `result["require_steam_id"]` / etc. on a `needs_modal` response, change to `result["modal_config"]["min_mmr"]` etc. For tests asserting `result["medal"]`/`result["tier"]` on a `needs_screenshot` response, delete those assertions (the keys are intentionally gone; assert `result["screenshot_type"]` instead).

- [ ] **Step 2: Run the full affected suite**

Run: `just test::run 'python manage.py test events.tests.test_signup_interactions tests.test_events_discord events.tests.test_signup_schema -v 2'`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/events/tests/test_signup_interactions.py backend/tests/test_events_discord.py
git commit -m "test(discord): update assertions for nested modal_config (#268)"
```

---

## Self-Review
- **Spec coverage:** config models + union (Task 1), envelope reshape + forbid (Task 2), producers (Task 3), consumer + dedup ternary (Task 4), test migration (Task 5). ✓
- **Placeholders:** none — full code for models, function, edits, tests.
- **Type consistency:** `DotaModalConfig`/`DeadlockModalConfig`/`SignupModalConfig`/`ModalConfig`/`dota_require_screenshot` used consistently across schemas, handlers, components.
- **Behavior:** wire shape changes, runtime behavior preserved (same modal fields, same screenshot logic). PR3 will move this code without touching the contract again.
