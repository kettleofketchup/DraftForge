# PR1 — Fix `view=None` crash in DM-disabled signup fallback (#268 bug 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `respond_to_signup_user` from raising `TypeError` when a user with DMs disabled signs up and no `view`/`embed` was passed.

**Architecture:** discord.py's `Webhook.send` (the `interaction.followup.send` fallback path) rejects a literal `None` for `view`/`embed` (`None` is not `MISSING` and has no `__discord_ui_view__`). The DM path (`Messageable.send`) tolerates `None`. Fix: pass `discord.utils.MISSING` instead of `None` on the `followup.send` path **only** (the DM send stays unchanged — it tolerates `None` and an existing test asserts it).

**Tech Stack:** Python, discord.py, Django `SimpleTestCase`, run via `just test::run`.

**Spec:** `docs/superpowers/specs/2026-05-31-discord-game-type-providers-design.md` → "Bugs fixed in-flight (issue #268)" bug 1. This is the first PR in the 3-PR stack; it is independent of the refactor.

---

### Task 1: Use the MISSING sentinel for view/embed in `respond_to_signup_user`

**Files:**
- Modify: `backend/discordbot/signup_responses.py` (`respond_to_signup_user`, lines ~75-98)
- Test: `backend/discordbot/tests/test_signup_responses.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/discordbot/tests/test_signup_responses.py` (the file already has `_make_interaction` and `_make_forbidden` helpers and imports `discord`, `ResponseChannel`, `respond_to_signup_user`):

```python
class RespondToSignupUserNoViewFallbackTest(SimpleTestCase):
    async def test_forbidden_fallback_with_no_view_does_not_raise_typeerror(self):
        """#268 bug 1: DM-disabled + no view/embed must fall back cleanly.

        Webhook.send rejects a literal None view (None is not MISSING and lacks
        __discord_ui_view__). The fallback must pass MISSING, not None.
        """
        interaction = _make_interaction(user_id=999)
        interaction.user.create_dm.side_effect = _make_forbidden(50007)

        # Make followup.send assert it never receives a literal None view/embed,
        # mirroring discord.py's Webhook.send behavior.
        def _send(*args, **kwargs):
            if kwargs.get("view", discord.utils.MISSING) is None:
                raise TypeError("expected view parameter to be of type View not NoneType")
            if kwargs.get("embed", discord.utils.MISSING) is None:
                raise TypeError("expected embed parameter to be of type Embed not NoneType")
        interaction.followup.send = AsyncMock(side_effect=_send)

        channel = await respond_to_signup_user(interaction, content="✅ You're signed up!")

        assert channel == ResponseChannel.EPHEMERAL
        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert kwargs["ephemeral"] is True
        assert kwargs["content"].startswith("<@999>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses.RespondToSignupUserNoViewFallbackTest -v 2'`
Expected: FAIL — `TypeError: expected view parameter to be of type View not NoneType` (the current code passes `view=None`).

- [ ] **Step 3: Apply the MISSING-sentinel fix**

In `backend/discordbot/signup_responses.py`, add the import near the top (with the other imports):

```python
from discord.utils import MISSING
```

Then in `respond_to_signup_user`, change ONLY the `followup.send` fallback (the
crash site). Leave the DM `dm_channel.send` unchanged — `Messageable.send`
tolerates `None`, and an existing test asserts the DM send receives `view=None`:

```python
    try:
        dm_channel = await interaction.user.create_dm()
        await dm_channel.send(content=content, embed=embed, view=view)  # unchanged
        try:
            await interaction.delete_original_response()
            log.info(
                "signup_interaction_placeholder_deleted",
                system="discord",
                subsystem="interaction",
                tags=["events", "signup"],
                tags_csv="events,signup",
                user_id=user_id,
                event_id=event_id,
            )
        except discord.NotFound:
            pass
        channel = ResponseChannel.DM
    except discord.Forbidden as e:
        if getattr(e, "code", None) == 50007:
            mention = f"<@{user_id}>"
            text = f"{mention} {content}".strip() if content else mention
            # Webhook.send rejects a literal None view/embed — pass MISSING.
            await interaction.followup.send(
                content=text,
                embed=embed if embed is not None else MISSING,
                view=view if view is not None else MISSING,
                ephemeral=True,
            )
            channel = ResponseChannel.EPHEMERAL
        else:
            log.error(
                "signup_response_failed",
                system="discord",
                subsystem="interaction",
                tags=["events", "signup"],
                tags_csv="events,signup",
                user_id=user_id,
                event_id=event_id,
                channel_id=channel_id,
                source_message_id=source_message_id,
                error=str(e),
            )
            raise
```

(`send_embed`/`send_view` are computed once before the `try`. Leave the rest of the function — the deferral block above it and the `signup_response_sent` log below it — unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses.RespondToSignupUserNoViewFallbackTest -v 2'`
Expected: PASS.

- [ ] **Step 5: Run the full signup_responses suite (no regression)**

Run: `just test::run 'python manage.py test discordbot.tests.test_signup_responses -v 2'`
Expected: all PASS (including the existing DM-success placeholder-deletion regression test).

- [ ] **Step 6: Commit**

```bash
git add backend/discordbot/signup_responses.py backend/discordbot/tests/test_signup_responses.py
git commit -m "fix(discord): MISSING sentinel for view/embed in DM-disabled signup fallback (#268)"
```

---

## Self-Review
- **Spec coverage:** Implements "Bugs fixed in-flight → bug 1" and its test bullet. ✓
- **Placeholders:** none — full test + full replacement block.
- **Type consistency:** `MISSING` imported; sentinel applied inline on the `followup.send` call only.
- **Scope:** single file + its test; independent of the refactor; safe to ship first.
