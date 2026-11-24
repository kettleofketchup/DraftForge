from typing import Any

from django.db.models import JSONField, Value
from structlog.testing import capture_logs

from app.models import CustomUser
from events.constants import SignupAction, SignupStatus
from events.history import HISTORY_EXTRA_KEYS, reduce_history_snapshot
from events.ledger import (
    ActorRole,
    SignupActor,
    SignupMeans,
    event_snapshot,
    record_signup_change,
    snapshot,
    user_snapshot,
)
from events.merge import merge_user_signups
from events.models import EventSignup, SignupLedgerEntry
from events.schemas import SignupSnapshot
from events.serializers import SignupLedgerEntrySerializer
from events.tests.base import EventTestCase

TOP_KEYS = {
    "id",
    "occurred_at",
    "action",
    "subject",
    "actor",
    "means",
    "on_behalf",
    "reason",
    "before",
    "after",
    "rules_overridden",
    "caused_by",
}
SUBJECT_KEYS = {
    "user_id",
    "username",
    "nickname",
    "discordNickname",
    "guildNickname",
    "avatarUrl",
    "discord_id",
}
ACTOR_KEYS = {
    "user_id",
    "username",
    "nickname",
    "discordNickname",
    "guildNickname",
    "avatarUrl",
    "role",
}
SNAPSHOT_KEYS = set(SignupSnapshot.model_fields)


def _staff_actor(user: CustomUser) -> SignupActor:
    return SignupActor(user=user, role=ActorRole.STAFF, means=SignupMeans.WEB)


class SignupLedgerEntrySerializerTest(EventTestCase):
    def _serialize(
        self, entry: SignupLedgerEntry, nicks: dict[int, str | None] | None = None
    ) -> dict[str, Any]:
        context = {"_history_guild_nicknames": nicks} if nicks is not None else {}
        return dict(SignupLedgerEntrySerializer(entry, context=context).data)

    def _raw_entry(self, **fields: Any) -> SignupLedgerEntry:
        entry = SignupLedgerEntry.objects.create(
            event=self.event,
            organization_id=self.event.organization_id,
            event_snapshot=event_snapshot(self.event),
            subject_user=self.user,
            subject_snapshot=user_snapshot(self.user),
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.APPROVED,
            **fields,
        )
        entry.refresh_from_db()
        return entry

    def _signup_entry(self, **kwargs: Any) -> SignupLedgerEntry:
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        return record_signup_change(
            event=self.event,
            subject=self.user,
            signup=signup,
            before=kwargs.pop("before", None),
            after=snapshot(signup, extra={"staff_power": True}),
            **kwargs,
        )

    def test_shape_keys(self) -> None:
        signup = EventSignup.objects.create(event=self.event, user=self.user)
        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=_staff_actor(self.admin),
            action=SignupAction.STAFF_ADDED,
            signup=signup,
            before=snapshot(signup),
            after=snapshot(signup, extra={"mmr_override": 4000}),
            reason="late add",
        )
        data = self._serialize(entry)
        self.assertEqual(set(data), TOP_KEYS)
        self.assertEqual(set(data["subject"]), SUBJECT_KEYS)
        self.assertEqual(set(data["actor"]), ACTOR_KEYS)
        for side in ("before", "after"):
            self.assertLessEqual(set(data[side]), SNAPSHOT_KEYS)
            self.assertLessEqual(set(data[side]["extra"]), HISTORY_EXTRA_KEYS)
        self.assertEqual(data["id"], entry.pk)
        self.assertEqual(data["action"], SignupAction.STAFF_ADDED)
        self.assertEqual(data["means"], SignupMeans.WEB)
        self.assertEqual(data["reason"], "late add")
        self.assertEqual(data["rules_overridden"], [])
        self.assertIsNone(data["caused_by"])
        self.assertIsInstance(data["occurred_at"], str)

    def test_live_values(self) -> None:
        self.user.discordId = "100000000000009003"
        self.user.avatar = "abc123"
        self.user.discordNickname = "cara"
        self.user.save()
        self.user.refresh_from_db()
        entry = self._signup_entry(
            actor=_staff_actor(self.admin), action=SignupAction.STAFF_ADDED
        )
        entry = SignupLedgerEntry.objects.select_related(
            "subject_user__base_profile", "actor_user__base_profile"
        ).get(pk=entry.pk)
        data = self._serialize(
            entry, {self.user.pk: "GuildCara", self.admin.pk: "GuildAdmin"}
        )
        subject = data["subject"]
        self.assertEqual(subject["user_id"], self.user.pk)
        self.assertEqual(subject["username"], self.user.username)
        self.assertEqual(subject["nickname"], "EventUser")
        self.assertEqual(subject["discordNickname"], "cara")
        self.assertEqual(subject["guildNickname"], "GuildCara")
        self.assertEqual(
            subject["avatarUrl"],
            "https://cdn.discordapp.com/avatars/100000000000009003/abc123.png",
        )
        self.assertEqual(subject["avatarUrl"], self.user.avatarUrl)
        self.assertEqual(subject["discord_id"], "100000000000009003")
        self.assertEqual(data["actor"]["user_id"], self.admin.pk)
        self.assertEqual(data["actor"]["guildNickname"], "GuildAdmin")
        self.assertEqual(data["after"]["extra"], {"staff_power": True})

    def test_system_actor_all_null(self) -> None:
        entry = self._signup_entry(
            actor=SignupActor.system(), action=SignupAction.PROMOTED
        )
        actor = self._serialize(entry)["actor"]
        self.assertEqual(actor["role"], ActorRole.SYSTEM)
        self.assertTrue(all(v is None for k, v in actor.items() if k != "role"))

    def test_staff_on_behalf(self) -> None:
        entry = self._signup_entry(
            actor=_staff_actor(self.admin), action=SignupAction.STAFF_ADDED
        )
        data = self._serialize(entry)
        self.assertEqual(data["actor"]["role"], "staff")
        self.assertIs(data["on_behalf"], True)

    def test_deleted_subject_falls_back_to_snapshot(self) -> None:
        gone = self.make_user()
        gone.discordId = "100000000000009004"
        gone.nickname = "Gone"
        gone.save()
        entry = record_signup_change(
            event=self.event,
            subject=gone,
            actor=SignupActor.system(),
            action=SignupAction.WITHDREW,
        )
        gone_pk, gone_username = gone.pk, gone.username
        gone.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.subject_user_id)
        subject = self._serialize(entry, {gone_pk: "ignored"})["subject"]
        self.assertEqual(
            subject,
            {
                "user_id": gone_pk,
                "username": gone_username,
                "nickname": "Gone",
                "discordNickname": None,
                "guildNickname": None,
                "avatarUrl": None,
                "discord_id": "100000000000009004",
            },
        )

    def test_null_subject_snapshot(self) -> None:
        entry = SignupLedgerEntry.objects.create(
            event=self.event,
            organization_id=self.event.organization_id,
            event_snapshot=event_snapshot(self.event),
            subject_user=None,
            subject_snapshot=Value(None, JSONField()),
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.WITHDREW,
        )
        entry.refresh_from_db()
        self.assertIsNone(entry.subject_snapshot)
        data = self._serialize(entry)
        self.assertEqual(set(data["subject"]), SUBJECT_KEYS)
        self.assertTrue(all(v is None for v in data["subject"].values()))

    def test_extra_allow_list(self) -> None:
        stored = {
            "status": SignupStatus.APPROVED,
            "commitment": "confirmed",
            "rsvp_class": "player",
            "extra": {"secret": "x", "mmr_override": 3},
            "junk": 1,
        }
        entry = self._raw_entry(after=stored)
        after = self._serialize(entry)["after"]
        self.assertEqual(after["extra"], {"mmr_override": 3})
        self.assertNotIn("junk", after)
        self.assertEqual(after["status"], SignupStatus.APPROVED)

    def test_merge_duplicate_keeps_before_extra(self) -> None:
        drop = self.make_user()
        EventSignup.objects.create(
            event=self.event, user=self.user, status=SignupStatus.APPROVED
        )
        dup = EventSignup.objects.create(
            event=self.event, user=drop, status=SignupStatus.CANCELLED
        )
        dup_pk = dup.pk
        merge_user_signups(drop, self.user, actor=_staff_actor(self.admin))
        entry = SignupLedgerEntry.objects.get(
            event=self.event, action=SignupAction.ACCOUNT_MERGED
        )
        data = self._serialize(entry)
        self.assertEqual(
            data["before"]["extra"],
            {
                "from_user_id": drop.pk,
                "discarded_duplicate": True,
                "discarded_signup_id": dup_pk,
            },
        )
        self.assertEqual(data["after"]["extra"], {})

    def test_malformed_snapshot_is_null_and_logged(self) -> None:
        entry = self._raw_entry(before={"status": 5})
        with capture_logs() as logs:
            data = self._serialize(entry)
        self.assertIsNone(data["before"])
        [log_entry] = [
            e for e in logs if e["event"] == "signup_history_snapshot_invalid"
        ]
        self.assertEqual(log_entry["log_level"], "warning")
        self.assertEqual(log_entry["system"], "events")
        self.assertEqual(log_entry["subsystem"], "ledger")
        self.assertEqual(log_entry["entry_id"], entry.pk)

    def test_malformed_rules_overridden_is_empty_and_logged(self) -> None:
        for raw in ({"rule": "x"}, "max_players", [1, "x"], [{"a": 1}]):
            with self.subTest(raw=raw):
                entry = self._raw_entry(rules_overridden=raw)
                with capture_logs() as logs:
                    data = self._serialize(entry)
                self.assertEqual(data["rules_overridden"], [])
                [log_entry] = [
                    e for e in logs if e["event"] == "signup_history_rules_invalid"
                ]
                self.assertEqual(log_entry["log_level"], "warning")
                self.assertEqual(log_entry["system"], "events")
                self.assertEqual(log_entry["subsystem"], "ledger")
                self.assertEqual(log_entry["entry_id"], entry.pk)

    def test_rules_overridden_strings_pass_through(self) -> None:
        entry = self._raw_entry(rules_overridden=["max_players", "min_mmr"])
        with capture_logs() as logs:
            data = self._serialize(entry)
        self.assertEqual(data["rules_overridden"], ["max_players", "min_mmr"])
        self.assertEqual(logs, [])


class ReduceHistorySnapshotTest(EventTestCase):
    def test_none_passthrough(self) -> None:
        self.assertIsNone(reduce_history_snapshot(None, entry_id=1))

    def test_non_dict_is_null(self) -> None:
        with capture_logs() as logs:
            self.assertIsNone(reduce_history_snapshot("x", entry_id=7))
            self.assertIsNone(reduce_history_snapshot([1], entry_id=7))
        self.assertEqual(
            [e["event"] for e in logs], ["signup_history_snapshot_invalid"] * 2
        )
