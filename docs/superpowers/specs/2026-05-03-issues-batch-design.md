# Issues Batch — Tournament Edit, Signup Writethrough, Discord Ergonomics, Captain Typo

**Date:** 2026-05-03
**Status:** Design
**Issues:** [#197](https://github.com/kettleofketchup/DraftForge/issues/197), [#196](https://github.com/kettleofketchup/DraftForge/issues/196), [#195](https://github.com/kettleofketchup/DraftForge/issues/195), [#194](https://github.com/kettleofketchup/DraftForge/issues/194), [#192](https://github.com/kettleofketchup/DraftForge/issues/192), [#191](https://github.com/kettleofketchup/DraftForge/issues/191), [#200](https://github.com/kettleofketchup/DraftForge/issues/200)
**Out of scope (already covered by separate plan):** [#188](https://github.com/kettleofketchup/DraftForge/issues/188) is Phase 5 of `2026-05-03-discord-dota-mmr-range-plan.md`.

## Summary

Bundle seven open issues into a single PR. Three Discord-bot ergonomic fixes (DM-fallback for signup messages, embed user-list capacity, ephemeral lifetime), two tournament-edit data-flow fixes (org MMR field visibility, signup→user writethrough including Discord guild nick), one tournament lifecycle fix (post-roll-call "Start Tournament" creating an empty/missing tournament), and one typo. No DB migrations, no API-shape breaks, no env-var changes.

## Problems & fixes

### 1. Captain typo (#197)

`frontend/app/components/tournament/captains/UpdateCaptainButton.tsx:61` — the non-staff fallback button reads `"Change Cpatain"`. One-character typo. Fix: `"Change Captain"`.

### 2. Org MMR not editable in tournament context (#195)

`frontend/app/pages/tournament/hasErrors.tsx:48-54` derives `editScope` as `'league'` if a league is present, otherwise `'global'`. `frontend/app/components/user/userCard/editModal.tsx:47` hides the MMR field when scope is `'global'`. Result: a tournament that belongs to an **org but no league** never shows the MMR field — staff cannot fix the very condition (`No MMR`) that the panel flags.

**Fix:** add an `'org'` branch. The full `OrganizationType` object is sourced from `useOrgStore.currentOrg` (`frontend/app/store/orgStore.ts`) — that store is already the canonical org context for the tournament view, so no extra fetch is needed. New scope derivation order: `league` → `org` → `global`:

```tsx
const currentOrg = useOrgStore((state) => state.currentOrg);

const editScope = useMemo<EditUserScope>(
  () =>
    league
      ? { kind: 'league', league }
      : currentOrg
        ? { kind: 'org', organization: currentOrg }
        : { kind: 'global' },
  [league?.pk, currentOrg?.pk],
);
```

The `showMmr` gate already permits org scope, so the field appears with the existing `mmrLabel="Org MMR"` treatment. We do *not* relax `showMmr` itself — keeping it gated preserves the global-edit semantics for non-tournament call sites (e.g., user profile page).

**Plan-time verification:** confirm the tournament view populates `useOrgStore.currentOrg` *before* `hasErrors` renders. If not (race on first paint), `currentOrg` will be `null` and the scope falls back to `'global'` — i.e., the original bug. The fix is to either await org load before rendering `hasErrors`, or to read `tournament.organization_pk` and trigger a `getOrganization(orgPk)` call when `currentOrg` is missing/mismatched.

### 3. Signup data not propagating to user (#196a)

When users submit an event signup form they declare positions, MMR, and Steam friend ID. These fields land on `PlayerDotaProfile` (per-org, linked via `OrgUser`), but the equivalent **User-level** fields (`User.positions` FK to `PositionsModel`, `User.steam_account_id`) stay empty. The tournament-side "incomplete profile" panel reads from User-level fields, so it keeps flagging the same data the user already filled in at signup.

**Fix — writethrough rules (PlayerDotaProfile → User):**

| Source on `PlayerDotaProfile` | Target | Rule |
|---|---|---|
| `pos_1`…`pos_5` | `User.positions` (the linked `PositionsModel`) | last-write-wins on signup save |
| `steam_account_id` (from signup form) | `User.steam_account_id` | first-write-wins (only if currently null/blank) |
| `mmr` | `OrgUser.mmr` | **untouched** at signup; routes through existing `MmrApprovalModal` / `approve_signup(mmr_override=...)` |

Rationale: positions express intent and self-correct as the user resubmits. Steam ID is identity-bearing and globally `unique=True` on `CustomUser` — a typo overwriting a verified value is worse than failing to update. MMR is staff-vetted and owned by the parallel MMR-range plan.

**Atomicity:** signup save and user writethrough share one `transaction.atomic`. A user-update failure (e.g., a colliding `steam_account_id` from another account) rolls the signup back too. This keeps invariants clean: the user never sees their signup recorded with the User-side fields silently ignored.

**Cache invalidation:** the writethrough mutates `User`, `OrgUser` (when MMR is later approved), and the linked `PositionsModel`. Inside the `transaction.atomic`, end with `invalidate_after_commit(user, org_user, tournament)` so the tournament-view "incomplete profile" panel reflects the writethrough on the next render rather than after the 1-hour TTL. Without this, the fix appears broken to users.

### 4. Discord guild nickname not seeded for new site users (#196b)

When `AddUser` creates a brand-new `User` from a Discord member, `User.nickname` is left blank. Setting it from the guild nick provides a familiar identifier the user already recognizes from Discord.

**Fix:** at the user-creation call site only, set `User.nickname = member.nick or member.global_name or member.username`. Never touches existing site users on subsequent links — this is one-time seeding, not a sync.

**Cache invalidation:** `app.customuser` is in the cacheops `CACHEOPS` map, so `.save()` on a freshly created user auto-invalidates per cacheops conventions. No extra `invalidate_after_commit` needed for this path.

### 5. Discord embed user list capped at 20 (#194)

`backend/events/discord/embeds.py` truncates signup lists at 20 users (`_user_list` default; inline `[:20]` slices at lines 122 and 237). Larger events lose visibility.

**Fix:** raise the cap to 40. Discord enforces a 1024-character per-field limit; 40 long display names can exceed it. So: build the line set, measure, and if it would exceed 1024 chars, split into two inline fields (`Signed Up`, `Signed Up (cont.)`). The split logic lives in a shared helper used by `build_announcement_embeds`, `build_announcement_v2`, and any other consumer of `_user_list_quoted`. "Declined" / "Tentative" / "Waitlisted" lists keep the same logic — split when over 1024 chars.

### 6. DM fallback for signup messages + ephemeral lifetime (#192, #191)

Signup-flow responses are currently ephemeral with `delete_after=60`. Users on mobile or away from the app miss them, and even when seen, the 60-second auto-dismiss is too aggressive.

**Fix — new helper:** `backend/discordbot/signup_responses.py`

```python
async def respond_to_signup_user(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    event=None,  # for logging context
) -> ResponseChannel:  # DM | EPHEMERAL
    """Try DM → fall back to ephemeral with <@user_id> prefix on Forbidden(50007)."""
```

**Behavior — must respect Discord's interaction lifecycle:**

```python
if not interaction.response.is_done():
    await interaction.response.defer(ephemeral=True)  # extends 3s window to 15min

try:
    dm = await interaction.user.create_dm()
    await dm.send(content=content, embed=embed, view=view)
    await interaction.delete_original_response()  # silent ack — no visible ephemeral
    channel = ResponseChannel.DM
except discord.Forbidden as e:
    if e.code == 50007:  # "Cannot send messages to this user"
        await interaction.followup.send(
            content=f"<@{interaction.user.id}> {content or ''}".strip(),
            embed=embed, view=view, ephemeral=True,
        )
        channel = ResponseChannel.EPHEMERAL
    else:
        log.error("signup_response_failed", system="events", subsystem="discord",
                  user_id=interaction.user.id,
                  event_id=getattr(event, "pk", None),
                  error=str(e))
        raise

log.info("signup_response_sent", system="events", subsystem="discord",
         channel=channel.value,
         fallback_to_ephemeral=(channel == ResponseChannel.EPHEMERAL),
         user_id=interaction.user.id,
         event_id=getattr(event, "pk", None))
return channel
```

Three correctness points the simpler version misses:

1. **Defer first.** Discord interactions must be acknowledged within 3 seconds, but `create_dm` + `send` can exceed that under load. `interaction.response.defer(ephemeral=True)` extends the window to 15 minutes; the deferral isn't visible to the user once we delete the original response.
2. **Silent-ack on DM success.** After a successful DM send, the deferred ephemeral placeholder must be deleted via `delete_original_response()`, otherwise the user sees an empty "thinking" state on the originating button.
3. **Logging taxonomy.** `system="events", subsystem="discord"` matches the project's existing event-Discord logging table. Event names are `signup_response_sent` (info, every call) and `signup_response_failed` (error, non-50007 Forbidden). Required fields per the logging skill: `system`, `subsystem`, `user_id`, `event_id`, plus `channel` / `fallback_to_ephemeral` for this helper, `error` on failure.

**On other `discord.Forbidden`:** log + re-raise. Don't swallow real permission errors (e.g., bot lacks Send Messages in the channel).

**Callsite refactor:** ~20 ephemeral responses in `backend/discordbot/components.py` belong to signup flows (signup confirmations, MMR/medal/position prompts and their results). Each becomes one call to `respond_to_signup_user`. Non-signup ephemerals (admin errors, validation) keep their shape but lose `delete_after=60` per #191B.

**View persistence:** discord.py persistent views work in DMs as long as the bot owns the custom IDs. Project uses bounded-timeout views, so no migration.

### 7. Post-roll-call "Start Tournament" creates nothing (#200)

`backend/events/views.py:608` `start_tournament` action transitions `Event` state and calls `finalize_event_tournament(event)`. Both no-op silently when `event.tournament is None`. Result: button "succeeds" but no tournament is created, no users are added.

**Fix — make `start_tournament` idempotent and self-healing:**

1. If `event.tournament is None`, call `create_tournament_for_event(event)` first.
2. Iterate `EventSignup`s in `APPROVED` or `CONFIRMED` status; `tournament.users.add(signup.user)` for each. Django's M2M `add()` is a no-op for already-added users, so this is safe to re-run.
3. Then `finalize_event_tournament(event)` → state transition.

Extract steps 1+2 into a new `services.ensure_tournament_with_signups(event)` so the view stays thin and the logic is unit-testable.

**Cache invalidation:** Django M2M `add()` does *not* trigger cacheops auto-invalidation (called out in the testing skill as a flake source). After the `tournament.users.add(...)` loop and the state transition, end with `invalidate_after_commit(tournament, event)` inside the same transaction. Without this, the tournament UI shows zero users until the 1-hour cacheops TTL expires.

## Non-goals

- DB schema changes, data migrations.
- API contract changes (request/response shapes).
- Touching the in-flight MMR-range plan; #188 stays on that track.
- Reworking ephemeral lifetime for non-signup flows beyond removing `delete_after=60`.
- Periodic prompts to refresh stale signup data — signup remains the only authoritative resubmission path.
- Generalizing `respond_to_signup_user` to non-signup interactions in this PR.

## File map

**Backend — `events/`**

- `services.py` — add `ensure_tournament_with_signups(event)`; extend signup save (or signup serializer's `create` / `update`) with positions+steam_id writethrough inside the existing `transaction.atomic`.
- `views.py` — `start_tournament` calls `ensure_tournament_with_signups` before `finalize_event_tournament`.
- `discord/embeds.py` — `_user_list`/`_user_list_quoted` raise default cap to 40; new helper splits into multiple fields when >1024 chars; inline `[:20]` blocks at 122 and 237 use the shared helper.

**Backend — `discordbot/`**

- `signup_responses.py` (new) — `respond_to_signup_user`, `ResponseChannel` enum, structured logging.
- `components.py` — refactor ~20 signup-flow callsites to use the helper; strip `delete_after=60` from remaining non-signup ephemerals.
- `bot.py` — same pattern audit; replace any signup-flow ephemeral with the helper. (Confirmed sites: 421, 455, 463, 466 from initial grep — verify scope at implementation time.)

**Backend — Discord-member → User creation site (#196b)**

- Locate the path that creates a new `User` from a Discord member (likely `app/views/admin_team.py` or a discord serializer); seed `nickname` from `member.nick / global_name / username`. Implementation task should `grep -rn "User.objects.create" backend/` against discord-add code paths to confirm location before edits.

**Frontend**

- `app/components/tournament/captains/UpdateCaptainButton.tsx:61` — typo fix.
- `app/pages/tournament/hasErrors.tsx` — add `'org'` branch in `editScope` derivation.
- `app/components/user/userCard/editModal.tsx` — confirm no change needed (the `'org'` scope already passes the `showMmr` gate); add a comment explaining the gate's intent if not already present.

## Test strategy

**Test data origin.** Reuse the existing **Events Test Org** fixture (org pk=7, league pk=7) populated by `backend/tests/populate/`. Login fixtures: `loginEventAdmin()` (pk=1080, org-admin in org 7) for staff actions; `loginEventPlayer()` (pk=1081) for signup actions. Adding new top-level orgs is unnecessary — the seven issues all fit within Events Test Org's domain.

**Backend invocation pattern.** All backend tests run via Docker per project convention (avoids the local-pytest Redis-hang issue):

```bash
just test::run 'python manage.py test events.tests.test_signup_writethrough -v 2'
```

The CLAUDE.md and testing skill both call this out as the recommended path; do not run `pytest` locally for these.

**Backend tests**

| File | Coverage |
|---|---|
| `events/tests/test_signup_writethrough.py` (new) | last-write-wins positions; first-write-wins steam_id (no overwrite when set); MMR not touched on save; one transaction (rollback test); `invalidate_after_commit` fires on success |
| `events/tests/test_start_tournament_idempotent.py` (new) | `event.tournament=None` → tournament created; APPROVED+CONFIRMED users added; second call no-ops; mixed-status signups (REJECTED/CANCELLED excluded); **cacheops invalidation asserted after M2M add** (call to GET tournament returns fresh user count, not stale empty) |
| `events/tests/test_embeds_user_list.py` (extend existing) | 40-user cap; auto-split at 1024 chars; counts in field names match split; 0/1/exactly-40 boundary cases |
| `discordbot/tests/test_signup_responses.py` (new) | interaction deferred before DM attempt; DM happy path → `delete_original_response` called; `Forbidden(50007)` → ephemeral followup with `<@user_id>` prefix; other `Forbidden` re-raised + `signup_response_failed` log emitted; `signup_response_sent` log emitted on every success path with correct `system`/`subsystem`/`channel` fields; ResponseChannel return value |
| `events/tests/test_add_user_discord_nick.py` (new) | guild nick → `User.nickname` on create; fallback chain (`nick`→`global_name`→`username`); existing user not overwritten |

**Frontend tests.** Frontend test runner verification deferred to plan-time (`cat frontend/package.json | grep -E '"(test|vitest|jest)"'` resolves it in one line). Assuming Vitest:

- `editModal.test.tsx` — extend: org-scope shows MMR even with no league.
- `hasErrors.test.tsx` (new or extend) — `useOrgStore.currentOrg` set + no league → editScope kind === `'org'`.
- `UpdateCaptainButton.test.tsx` — assertion on the non-staff button text.

**Playwright E2E.** Mostly skipped, with one targeted exception: extend an existing event-admin Playwright spec to assert `[data-testid="mmr-input"]` is visible in the edit-user modal opened from a tournament whose org is set but league is absent. The MMR-range plan already wires `data-testid="mmr-input"` so the testid exists. Use `data-testid` selectors per the testing skill's mandatory selector policy. No new spec file — extend an existing one to keep feature isolation.

**TDD discipline** — per `superpowers:test-driven-development`, each new test file lands as failing tests first; implementation in the next commit.

## Architectural decisions

### DM-fallback as a wrapper helper (not inline try/except)

~20 callsites is enough that duplicating the try/except is more code than the abstraction. A helper also centralizes the structured log line so future metrics ("DM-success rate") attach in one place. The helper is small (≤30 lines) and lives in its own file — the abstraction overhead is negligible.

### Signup writethrough split (positions/steam-id immediate, MMR via approval)

Positions and steam ID are low-risk: positions are aspirational and re-declared each signup; steam ID is gated by first-write-wins. MMR is high-risk (drives bracket seeding, draft order) and already has a staff-approval flow we shouldn't bypass.

### `start_tournament` self-healing (not a separate "create tournament" endpoint)

The bug surfaces a class of legacy events where `event.tournament` is `None`. A separate endpoint forces staff to know they need to call it. Self-healing inside `start_tournament` lets the existing button "just work" for those events without UI changes.

### Embed split into two fields (vs. truncation)

Up to 40 names is the user-stated requirement. Truncating to a smaller cap to fit one field fails the requirement; pushing to a second field uses Discord's available real estate and never silently drops names.

## Rollout

- Single PR, commits grouped per issue.
- No migrations, no settings changes, no Discord re-onboarding required.
- Existing tournaments unaffected unless they hit the `start_tournament` self-heal path (which is a strict improvement for them).
- DM fallback rollout has a small risk: users with DMs disabled now see ephemeral messages that they previously saw the same way. Net change for them: zero, plus a `<@user_id>` notification ping.

## Open questions

None at design time. Implementation-time questions (e.g., exact location of the discord-add-user code path for #196b) resolved during plan execution.
