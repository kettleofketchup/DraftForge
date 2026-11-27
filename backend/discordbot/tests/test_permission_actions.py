import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.test import SimpleTestCase
from pydantic import ValidationError

from discordbot.permissions.actions import (
    EVENT_ACTIONS,
    PUBLIC_PREVIEW_ACTIONS,
    REGISTRY,
    profile_for,
)
from discordbot.permissions.evaluate import ResolvedCheck, SnapshotBundle, evaluate
from discordbot.permissions.flags import BIT
from discordbot.permissions.flags import PermissionFlag as F
from discordbot.permissions.schemas import (
    ActionKind as A,
)
from discordbot.permissions.schemas import (
    ChannelSnap,
    Destination,
    GuildSnap,
    MemberSnap,
    Observation,
    Overwrite,
    PermissionChecksApi,
    PermissionChecksRequest,
    PermissionChecksResponse,
    RoleSnap,
    ThreadMeta,
)

GUILD = "223456789012345678"
CHANNEL = "123456789012345678"
PARENT = "323456789012345678"
BOT = "423456789012345678"
ROLE = "523456789012345678"
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def bits(*flags: F) -> int:
    return sum(BIT[flag] for flag in flags)


def bundle(permissions: int, *, timeout: datetime | None = None) -> SnapshotBundle:
    return SnapshotBundle(
        guild=GuildSnap(
            GUILD,
            "623456789012345678",
            {
                GUILD: RoleSnap(GUILD, permissions, False, False),
                ROLE: RoleSnap(ROLE, 0, False, False),
            },
        ),
        member=MemberSnap(BOT, (), timeout),
        observation=Observation(NOW, NOW + timedelta(seconds=60)),
        error=None,
        retry_after=None,
    )


def check(action: A = A.ANNOUNCEMENT, *, channel_type: int = 0) -> ResolvedCheck:
    channel = ChannelSnap(
        CHANNEL, GUILD, channel_type, "event-updates", None, (), 0, None, False
    )
    return ResolvedCheck(
        key="announcement",
        action=action,
        destination=Destination(
            kind="channel",
            channel_id=CHANNEL,
            name="event-updates",
            channel_type=channel_type,
            source="configured",
        ),
        channel=channel,
        parent=None,
        role_ids=(),
        include_rsvp=False,
        reference_present=True,
        message_owned=True,
        event_creator_is_bot=True,
        reason_override=None,
    )


class ActionPermissionTests(SimpleTestCase):
    def test_missing_embed_links_reports_only_that_flag(self) -> None:
        result = evaluate(
            check(),
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.READ_MESSAGE_HISTORY)),
            NOW,
        )
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.missing, ["EMBED_LINKS"])
        self.assertEqual(
            result.granted, ["VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY"]
        )
        self.assertEqual(result.effective_permissions, "68608")

    def test_start_mention_plain_reply_needs_no_embed(self) -> None:
        result = evaluate(
            check(A.START_MENTION),
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.READ_MESSAGE_HISTORY)),
            NOW,
        )
        self.assertEqual(result.status, "verified")
        self.assertNotIn("EMBED_LINKS", result.required_all)

    def test_forum_signup_needs_no_create_public_threads(self) -> None:
        result = evaluate(
            check(A.SIGNUP_CREATE, channel_type=15),
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)),
            NOW,
        )
        self.assertEqual(result.status, "verified")
        self.assertNotIn("CREATE_PUBLIC_THREADS", result.required_all)

    def test_text_and_announcement_signup_use_embed_permissions(self) -> None:
        required = (F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)
        for channel_type in (0, 5):
            for missing in (None, *required):
                with self.subTest(channel_type=channel_type, missing=missing):
                    result = evaluate(
                        check(A.SIGNUP_CREATE, channel_type=channel_type),
                        bundle(bits(*(flag for flag in required if flag != missing))),
                        NOW,
                    )
                    self.assertEqual(result.required_all, list(required))
                    self.assertEqual(
                        result.status,
                        "verified" if missing is None else "missing_permissions",
                    )
                    self.assertEqual(
                        result.missing,
                        []
                        if missing is None
                        else list(required[required.index(missing) :]),
                    )

    def test_forum_requires_tag_blocks(self) -> None:
        descriptor = check(A.SIGNUP_CREATE, channel_type=15)
        descriptor = replace(
            descriptor,
            channel=replace(descriptor.channel, available_tags_required=True),
        )
        result = evaluate(descriptor, bundle(bits(F.ADMINISTRATOR)), NOW)
        self.assertEqual(result.status, "unsupported")
        self.assertEqual([b.code for b in result.blockers], ["forum_requires_tag"])

    def test_message_action_at_forum_is_unsupported_channel_type(self) -> None:
        for action in (
            A.SIGNUP_FALLBACK,
            A.ANNOUNCEMENT,
            A.ATTENDANCE_REMINDER,
            A.PROFILE_REMINDER,
            A.NEW_EVENT_NOTICE,
            A.TEMPLATE_POST,
            A.ADMIN_CHANNEL_POST,
        ):
            with self.subTest(action=action):
                result = evaluate(
                    check(action, channel_type=15), bundle(bits(F.ADMINISTRATOR)), NOW
                )
                self.assertEqual(
                    (result.status, result.reason),
                    ("unsupported", "unsupported_channel_type"),
                )

    def test_template_rsvp_needs_history_and_reactions(self) -> None:
        descriptor = replace(check(A.TEMPLATE_POST), include_rsvp=True)
        result = evaluate(
            descriptor,
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)),
            NOW,
        )
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.missing, ["READ_MESSAGE_HISTORY", "ADD_REACTIONS"])
        self.assertEqual(
            evaluate(
                check(A.TEMPLATE_POST),
                bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)),
                NOW,
            ).status,
            "verified",
        )

    def test_non_mentionable_role_requires_mention_everyone(self) -> None:
        for action, channel_type in ((A.ANNOUNCEMENT, 0), (A.SIGNUP_CREATE, 15)):
            descriptor = replace(
                check(action, channel_type=channel_type), role_ids=(ROLE,)
            )
            result = evaluate(
                descriptor,
                bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)),
                NOW,
            )
            self.assertEqual(result.missing, ["MENTION_EVERYONE"])
            self.assertEqual(result.status, "missing_permissions")
            self.assertEqual(
                [b.code for b in result.blockers], ["role_not_mentionable"]
            )
            self.assertEqual(
                evaluate(descriptor, bundle(bits(F.ADMINISTRATOR)), NOW).status,
                "verified",
            )

    def test_mentionable_role_needs_nothing_extra(self) -> None:
        snapshot = bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS))
        snapshot.guild.roles[ROLE] = RoleSnap(ROLE, 0, True, False)
        result = evaluate(replace(check(), role_ids=(ROLE,)), snapshot, NOW)
        self.assertEqual(result.status, "verified")
        self.assertNotIn("MENTION_EVERYONE", result.required_all)

    def test_deleted_role_is_blocker(self) -> None:
        result = evaluate(
            replace(check(), role_ids=("723456789012345678",)),
            bundle(bits(F.ADMINISTRATOR)),
            NOW,
        )
        self.assertEqual(result.status, "unknown")
        self.assertEqual([b.code for b in result.blockers], ["role_missing"])

    def test_fallback_has_no_role_requirement(self) -> None:
        descriptor = replace(check(A.SIGNUP_FALLBACK), role_ids=("723456789012345678",))
        result = evaluate(
            descriptor,
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)),
            NOW,
        )
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.blockers, [])

    def test_create_events_alone_creates(self) -> None:
        result = evaluate(
            check(A.SCHEDULED_EVENT_CREATE), bundle(bits(F.CREATE_EVENTS)), NOW
        )
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.required_all, ["CREATE_EVENTS"])
        self.assertEqual(result.destination.kind, "guild")

    def test_manage_events_alone_does_not_create(self) -> None:
        result = evaluate(
            check(A.SCHEDULED_EVENT_CREATE), bundle(bits(F.MANAGE_EVENTS)), NOW
        )
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.missing, ["CREATE_EVENTS"])

    def test_own_event_update_accepts_either(self) -> None:
        for action in (A.SCHEDULED_EVENT_UPDATE, A.SCHEDULED_EVENT_DELETE):
            for permission in (F.CREATE_EVENTS, F.MANAGE_EVENTS):
                with self.subTest(action=action, permission=permission):
                    result = evaluate(check(action), bundle(bits(permission)), NOW)
                    self.assertEqual(result.status, "verified")
                    self.assertEqual(
                        result.required_any, [["CREATE_EVENTS", "MANAGE_EVENTS"]]
                    )
                    self.assertEqual(result.missing, [])

    def test_other_creator_update_needs_manage_events(self) -> None:
        descriptor = replace(
            check(A.SCHEDULED_EVENT_UPDATE), event_creator_is_bot=False
        )
        result = evaluate(descriptor, bundle(bits(F.CREATE_EVENTS)), NOW)
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.missing, ["MANAGE_EVENTS"])
        self.assertEqual(
            evaluate(descriptor, bundle(bits(F.MANAGE_EVENTS)), NOW).status, "verified"
        )

    def test_unknown_creator_cannot_use_create_alternative(self) -> None:
        for action in (A.SCHEDULED_EVENT_UPDATE, A.SCHEDULED_EVENT_DELETE):
            descriptor = replace(check(action), event_creator_is_bot=None)
            result = evaluate(descriptor, bundle(bits(F.CREATE_EVENTS)), NOW)
            self.assertEqual(result.status, "unknown")
            self.assertEqual(result.required_all, ["MANAGE_EVENTS"])
            self.assertEqual(
                evaluate(descriptor, bundle(bits(F.MANAGE_EVENTS)), NOW).status,
                "verified",
            )

    def test_missing_event_reference_pending(self) -> None:
        for reference in (None, False):
            for action in (A.SCHEDULED_EVENT_UPDATE, A.SCHEDULED_EVENT_DELETE):
                result = evaluate(
                    replace(check(action), reference_present=reference),
                    bundle(bits(F.ADMINISTRATOR)),
                    NOW,
                )
                self.assertEqual(result.status, "unconfigured")
                self.assertEqual(
                    [b.code for b in result.blockers], ["missing_reference"]
                )

    def test_timeout_blocks_scheduled_event_create(self) -> None:
        until = NOW + timedelta(seconds=20)
        result = evaluate(
            check(A.SCHEDULED_EVENT_CREATE),
            bundle(bits(F.CREATE_EVENTS), timeout=until),
            NOW,
        )
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.blockers[0].code, "communication_timeout")
        self.assertEqual(result.blockers[0].missing, ["CREATE_EVENTS"])
        self.assertIn("CREATE_EVENTS", result.base_granted)
        self.assertNotIn("CREATE_EVENTS", result.granted)
        self.assertLessEqual(result.expires_at, until)

    def test_timeout_blocks_update_alternatives(self) -> None:
        for action in (A.SCHEDULED_EVENT_UPDATE, A.SCHEDULED_EVENT_DELETE):
            for flag in (F.CREATE_EVENTS, F.MANAGE_EVENTS):
                result = evaluate(
                    check(action),
                    bundle(bits(flag), timeout=NOW + timedelta(seconds=20)),
                    NOW,
                )
                self.assertEqual(result.status, "missing_permissions")
                self.assertEqual(
                    result.required_any, [["CREATE_EVENTS", "MANAGE_EVENTS"]]
                )
                self.assertEqual(result.missing, [])
                self.assertEqual(
                    result.blockers[0].missing, ["CREATE_EVENTS", "MANAGE_EVENTS"]
                )

    def test_timeout_blocks_send_even_with_overwrite_allow(self) -> None:
        descriptor = check()
        descriptor = replace(
            descriptor,
            channel=replace(
                descriptor.channel,
                overwrites=(
                    Overwrite(BOT, 1, bits(F.SEND_MESSAGES, F.EMBED_LINKS), 0),
                ),
            ),
        )
        result = evaluate(
            descriptor,
            bundle(bits(F.VIEW_CHANNEL), timeout=NOW + timedelta(seconds=20)),
            NOW,
        )
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(result.missing, ["SEND_MESSAGES", "EMBED_LINKS"])
        self.assertEqual(result.blockers[0].code, "communication_timeout")

    def test_mark_interested_unsupported(self) -> None:
        result = evaluate(check(A.MARK_INTERESTED), bundle(bits(F.ADMINISTRATOR)), NOW)
        self.assertEqual(
            (result.status, result.reason), ("unsupported", "unsupported_endpoint")
        )

    def test_dm_not_applicable_never_verified(self) -> None:
        for action in (A.SIGNUP_REMINDER_DM, A.TOURNAMENT_DM):
            result = evaluate(check(action), bundle(bits(F.ADMINISTRATOR)), NOW)
            self.assertEqual(result.status, "not_applicable")
            self.assertEqual(
                (result.destination.kind, result.destination.source),
                ("dm", "recipient"),
            )

    def test_pending_signup_post(self) -> None:
        result = evaluate(
            replace(check(A.START_MENTION), reference_present=False),
            bundle(bits(F.ADMINISTRATOR)),
            NOW,
        )
        self.assertEqual(
            (result.status, result.reason), ("unconfigured", "pending_signup_post")
        )
        self.assertEqual(
            result.required_all,
            ["VIEW_CHANNEL", "SEND_MESSAGES", "READ_MESSAGE_HISTORY"],
        )

    def test_incomplete_snapshot_is_unknown_not_missing(self) -> None:
        snapshot = bundle(bits(F.ADMINISTRATOR))
        snapshot.guild.roles.pop(GUILD)
        result = evaluate(check(), snapshot, NOW)
        self.assertEqual(
            (result.status, result.reason), ("unknown", "malformed_snapshot")
        )
        self.assertIsNone(result.granted)
        self.assertIsNone(result.effective_permissions)
        self.assertEqual(
            result.required_all, ["VIEW_CHANNEL", "SEND_MESSAGES", "EMBED_LINKS"]
        )

    def test_expired_observation_is_unknown(self) -> None:
        snapshot = replace(
            bundle(bits(F.ADMINISTRATOR)),
            observation=Observation(NOW - timedelta(minutes=2), NOW),
        )
        result = evaluate(check(), snapshot, NOW)
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.granted)

    def test_failures_keep_requirements_without_effective_grants(self) -> None:
        for reason in (
            "forbidden_read",
            "resource_unavailable",
            "rate_limited",
            "network_error",
            "credential_unavailable",
        ):
            snapshot = replace(
                bundle(bits(F.ADMINISTRATOR)), error=reason, retry_after=10
            )
            result = evaluate(check(), snapshot, NOW)
            self.assertEqual((result.status, result.reason), ("unknown", reason))
            self.assertEqual(result.retry_after_seconds, 10)
            self.assertIsNone(result.granted)
            self.assertIn("EMBED_LINKS", result.required_all)

    def test_unconfigured_destinations_never_verify(self) -> None:
        no_guild = replace(bundle(0), guild=None)
        result = evaluate(check(), no_guild, NOW)
        self.assertEqual(
            (result.status, result.reason), ("unconfigured", "no_server_configured")
        )
        result = evaluate(
            replace(check(), channel=None, destination=Destination(kind="none")),
            bundle(bits(F.ADMINISTRATOR)),
            NOW,
        )
        self.assertEqual(
            (result.status, result.reason), ("unconfigured", "no_channel_configured")
        )

    def test_administrator_does_not_bypass_unsupported_or_blockers(self) -> None:
        descriptor = replace(check(A.SIGNUP_EDIT), message_owned=None)
        result = evaluate(descriptor, bundle(bits(F.ADMINISTRATOR)), NOW)
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.required_all, ["VIEW_CHANNEL"])
        self.assertNotIn("MANAGE_MESSAGES", result.required_all)
        self.assertNotEqual(
            evaluate(
                replace(descriptor, message_owned=False),
                bundle(bits(F.ADMINISTRATOR)),
                NOW,
            ).status,
            "verified",
        )

    def thread_check(
        self,
        action: A,
        *,
        private: bool = False,
        member: bool | None = True,
        archived: bool = False,
        locked: bool = False,
    ) -> ResolvedCheck:
        descriptor = check(action)
        parent = replace(descriptor.channel, id=PARENT)
        thread = replace(
            descriptor.channel,
            type=12 if private else 11,
            parent_id=PARENT,
            thread_meta=ThreadMeta(archived, locked, private, member),
        )
        return replace(
            descriptor,
            channel=thread,
            parent=parent,
            destination=Destination(
                kind="thread",
                channel_id=CHANNEL,
                parent_id=PARENT,
                channel_type=thread.type,
                source="posted",
            ),
        )

    def test_private_thread_access_cases(self) -> None:
        for action in (A.START_MENTION, A.SIGNUP_EDIT, A.ANNOUNCEMENT_EDIT):
            for member in (True, False, None):
                for grants in (
                    bits(
                        F.VIEW_CHANNEL,
                        F.SEND_MESSAGES_IN_THREADS,
                        F.READ_MESSAGE_HISTORY,
                    ),
                    bits(F.ADMINISTRATOR),
                ):
                    with self.subTest(action=action, member=member, grants=grants):
                        result = evaluate(
                            self.thread_check(action, private=True, member=member),
                            bundle(grants),
                            NOW,
                        )
                        self.assertEqual(
                            result.status, "verified" if member else "unknown"
                        )
                        self.assertEqual(
                            [b.code for b in result.blockers],
                            [] if member else ["private_thread_access"],
                        )

    def test_thread_lifecycle_cases(self) -> None:
        for action in (A.START_MENTION, A.SIGNUP_EDIT, A.ANNOUNCEMENT_EDIT):
            for archived, locked in (
                (False, False),
                (True, False),
                (False, True),
                (True, True),
            ):
                for grants in (
                    bits(
                        F.VIEW_CHANNEL,
                        F.SEND_MESSAGES_IN_THREADS,
                        F.READ_MESSAGE_HISTORY,
                    ),
                    bits(F.ADMINISTRATOR),
                ):
                    with self.subTest(
                        action=action, archived=archived, locked=locked, grants=grants
                    ):
                        result = evaluate(
                            self.thread_check(action, archived=archived, locked=locked),
                            bundle(grants),
                            NOW,
                        )
                        self.assertEqual(
                            result.status,
                            "unknown" if archived or locked else "verified",
                        )
                        self.assertEqual(
                            [b.code for b in result.blockers],
                            (["thread_archived"] if archived else [])
                            + (["thread_locked"] if locked else []),
                        )

    def test_thread_send_does_not_use_parent_send(self) -> None:
        descriptor = self.thread_check(A.START_MENTION)
        result = evaluate(
            descriptor,
            bundle(bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.READ_MESSAGE_HISTORY)),
            NOW,
        )
        self.assertEqual(result.missing, ["SEND_MESSAGES_IN_THREADS"])
        self.assertEqual(result.status, "missing_permissions")
        self.assertEqual(
            evaluate(
                replace(
                    descriptor, channel=replace(descriptor.channel, thread_meta=None)
                ),
                bundle(bits(F.ADMINISTRATOR)),
                NOW,
            ).status,
            "unknown",
        )

    def test_bitfield_above_js_safe_range_round_trips_as_string(self) -> None:
        value = 1 << 60 | bits(F.VIEW_CHANNEL, F.SEND_MESSAGES, F.EMBED_LINKS)
        result = evaluate(check(), bundle(value), NOW)
        self.assertEqual(result.effective_permissions, str(value))
        self.assertEqual(result.raw_permissions, str(value))
        parsed = PermissionChecksResponse.model_validate_json(
            PermissionChecksResponse(guild_id=GUILD, checks=[result]).model_dump_json()
        )
        self.assertEqual(parsed.checks[0].effective_permissions, str(value))

    def test_registry_and_public_action_sets(self) -> None:
        self.assertEqual(set(REGISTRY), set(A))
        self.assertNotIn(A.ADMIN_CHANNEL_POST, PUBLIC_PREVIEW_ACTIONS)
        self.assertNotIn(A.SIGNUP_EDIT, PUBLIC_PREVIEW_ACTIONS)
        self.assertNotIn(A.ANNOUNCEMENT_EDIT, PUBLIC_PREVIEW_ACTIONS)
        self.assertEqual(
            EVENT_ACTIONS, frozenset(A) - {A.ADMIN_CHANNEL_POST, A.TEMPLATE_POST}
        )
        profile = profile_for(
            A.START_MENTION, in_thread=True, include_rsvp=False, own_event=None
        )
        self.assertEqual(
            profile.required_all,
            (F.VIEW_CHANNEL, F.SEND_MESSAGES_IN_THREADS, F.READ_MESSAGE_HISTORY),
        )

    def test_fixture_matches_contract(self) -> None:
        fixture = Path(__file__).with_name("permission_checks_fixture.json")
        response = PermissionChecksResponse.model_validate(
            json.loads(fixture.read_text())
        )
        self.assertEqual(
            {r.status for r in response.checks},
            {"verified", "missing_permissions", "unsupported", "not_applicable"},
        )
        self.assertEqual(
            response.model_dump(mode="json"), json.loads(fixture.read_text())
        )

    def test_request_rejects_duplicate_keys_and_oversize(self) -> None:
        valid = {"key": "announcement", "action": "announcement", "channel_id": CHANNEL}
        invalid = [
            {"checks": [valid, valid]},
            {"checks": [{**valid, "key": f"check-{i}"} for i in range(21)]},
            {"checks": [{**valid, "role_ids": [ROLE] * 26}]},
            {"checks": [{**valid, "channel_id": int(CHANNEL)}]},
            {"checks": [{**valid, "role_ids": [int(ROLE)]}]},
            {"checks": [{**valid, "action": "arbitrary"}]},
            {"checks": [{**valid, "message_owned": True}]},
            {"checks": [{**valid, "key": "INVALID"}]},
            {"checks": [valid], "guild_id": GUILD},
            {"checks": []},
        ]
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValidationError):
                PermissionChecksRequest.model_validate(body)
        parsed = PermissionChecksRequest.model_validate({"checks": [valid]})
        self.assertEqual(parsed.checks[0].role_ids, [])

    def test_serialized_response_defaults_are_required_in_schema(self) -> None:
        schema = PermissionChecksApi.model_json_schema(mode="serialization")
        result = schema["$defs"]["PermissionCheckResult"]
        self.assertEqual(set(result["required"]), set(result["properties"]))
