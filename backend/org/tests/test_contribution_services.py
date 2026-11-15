from datetime import UTC, date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization, OrgLog
from events.models import Event
from org.contributions.kinds import DEFAULT_POINTS, ContributionKind
from org.contributions.points import points_for
from org.contributions.services import (
    POINT_VALUE_MAX,
    RescoreResult,
    award_entry,
    create_manual_award,
    delete_manual_award,
    delete_user_entries,
    set_point_value,
    update_manual_award,
)
from org.models import ContributionEntry, ContributionPointValue, OrgUser


class ContributionServicesTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(username="svc_admin", password="x")
        self.member = CustomUser.objects.create_user(
            username="svc_member", password="x"
        )
        self.org = Organization.objects.create(
            name="Svc Org", owner=self.admin, timezone="America/New_York"
        )
        self.other_org = Organization.objects.create(
            name="Svc Other Org", owner=self.admin
        )
        self.league = League.objects.create(
            name="Svc League", organization=self.org, steam_league_id=99771
        )
        self.other_league = League.objects.create(
            name="Svc Other League",
            organization=self.other_org,
            steam_league_id=99772,
        )
        self.event = self._event(self.org, self.league, "Svc Event")
        self.foreign_event = self._event(
            self.other_org, self.other_league, "Foreign Event"
        )

    def _event(self, org: Organization, league: League, name: str) -> Event:
        return Event.objects.create(
            organization=org,
            name=name,
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            tournament_league=league,
        )

    def _manual(self, **overrides: object) -> ContributionEntry:
        fields: dict[str, object] = {
            "org": self.org,
            "user": self.member,
            "points": 7,
            "reason": "Ran the stream",
            "on_date": date(2026, 11, 1),
            "actor": self.admin,
        }
        fields.update(overrides)
        OrgUser.objects.get_or_create(user=fields["user"], organization=fields["org"])
        return create_manual_award(**fields)  # type: ignore[arg-type]

    def _auto(
        self, kind: str, occurred_at: datetime, event: Event | None = None
    ) -> ContributionEntry:
        return award_entry(
            org=self.org,
            user=self.member,
            kind=kind,
            occurred_at=occurred_at,
            event=event,
        )

    # award_entry

    def test_award_entry_defaults_points_and_creates_org_user(self) -> None:
        self.assertFalse(OrgUser.objects.filter(user=self.member).exists())
        entry = self._auto(
            ContributionKind.EVENT_HOST, timezone.now(), event=self.event
        )
        self.assertEqual(entry.points, DEFAULT_POINTS["event_host"])
        self.assertEqual(entry.org_user.user, self.member)
        self.assertEqual(entry.org_user.organization, self.org)
        self.assertEqual(entry.event_name, "Svc Event")
        self.assertIsNone(entry.awarded_by)

    def test_award_entry_uses_org_override(self) -> None:
        ContributionPointValue.objects.create(
            organization=self.org, kind=ContributionKind.PROMO_MESSAGE, points=4
        )
        entry = self._auto(ContributionKind.PROMO_MESSAGE, timezone.now())
        self.assertEqual(entry.points, 4)

    def test_award_entry_rejects_foreign_event(self) -> None:
        with self.assertRaises(ValueError):
            self._auto(
                ContributionKind.EVENT_HOST, timezone.now(), event=self.foreign_event
            )

    # create_manual_award

    def test_manual_award_requires_reason(self) -> None:
        for reason in ("", "   "):
            with self.assertRaises(ValueError):
                self._manual(reason=reason)
        self.assertFalse(ContributionEntry.objects.exists())

    def test_manual_award_reason_stripped(self) -> None:
        entry = self._manual(reason="  Helped out  ")
        self.assertEqual(entry.reason, "Helped out")

    def test_manual_award_rejects_long_reason(self) -> None:
        with self.assertRaises(ValueError):
            self._manual(reason="x" * 501)

    def test_manual_award_rejects_out_of_range_points(self) -> None:
        for points in (0, -5, 1001, True):
            with self.assertRaises(ValueError, msg=f"points={points!r}"):
                self._manual(points=points)
        self.assertFalse(ContributionEntry.objects.exists())

    def test_manual_award_accepts_range_bounds(self) -> None:
        self.assertEqual(self._manual(points=1).points, 1)
        self.assertEqual(self._manual(points=1000).points, 1000)

    def test_manual_award_dated_nov1_ny_is_local_noon(self) -> None:
        entry = self._manual(on_date=date(2026, 11, 1))
        self.assertEqual(entry.occurred_at, datetime(2026, 11, 1, 17, 0, tzinfo=UTC))
        self.assertEqual(entry.kind, ContributionKind.MANUAL)
        self.assertEqual(entry.awarded_by, self.admin)
        self.assertEqual(entry.organization, self.org)

    def test_manual_award_bad_timezone_falls_back_to_utc(self) -> None:
        Organization.objects.filter(pk=self.org.pk).update(timezone="Mars/Base")
        self.org.refresh_from_db()
        entry = self._manual(on_date=date(2026, 11, 1))
        self.assertEqual(entry.occurred_at, datetime(2026, 11, 1, 12, 0, tzinfo=UTC))

    def test_manual_award_with_own_event(self) -> None:
        entry = self._manual(event=self.event)
        self.assertEqual(entry.event, self.event)
        self.assertEqual(entry.event_name, "Svc Event")

    def test_manual_award_rejects_foreign_event(self) -> None:
        with self.assertRaises(ValueError):
            self._manual(event=self.foreign_event)
        self.assertFalse(ContributionEntry.objects.exists())

    def test_manual_award_rejects_non_member(self) -> None:
        outsider = CustomUser.objects.create_user(username="svc_outsider", password="x")
        with self.assertRaises(ValueError):
            create_manual_award(
                org=self.org,
                user=outsider,
                points=5,
                reason="Not a member",
                on_date=date(2026, 11, 1),
                actor=self.admin,
            )
        self.assertFalse(OrgUser.objects.filter(user=outsider).exists())
        self.assertFalse(ContributionEntry.objects.exists())
        self.assertFalse(OrgLog.objects.filter(action="award_points").exists())

    def test_manual_award_rejects_member_of_other_org(self) -> None:
        OrgUser.objects.create(user=self.member, organization=self.other_org)
        with self.assertRaises(ValueError):
            create_manual_award(
                org=self.org,
                user=self.member,
                points=5,
                reason="Wrong org",
                on_date=date(2026, 11, 1),
                actor=self.admin,
            )
        self.assertFalse(
            OrgUser.objects.filter(user=self.member, organization=self.org).exists()
        )
        self.assertFalse(ContributionEntry.objects.exists())

    def test_manual_award_to_role_holders_without_org_user_creates_row(self) -> None:
        holders: dict[str, CustomUser] = {
            role: CustomUser.objects.create_user(username=f"svc_{role}", password="x")
            for role in ("co_admin", "staffer", "promoter")
        }
        self.org.admins.add(holders["co_admin"])
        self.org.staff.add(holders["staffer"])
        self.org.promoters.add(holders["promoter"])
        for role, user in [*holders.items(), ("owner", self.admin)]:
            with self.subTest(role=role):
                self.assertFalse(
                    OrgUser.objects.filter(user=user, organization=self.org).exists()
                )
                entry = create_manual_award(
                    org=self.org,
                    user=user,
                    points=5,
                    reason="Helped out",
                    on_date=date(2026, 11, 1),
                    actor=self.admin,
                )
                self.assertEqual(entry.org_user.user, user)
                self.assertEqual(entry.org_user.organization, self.org)

    def test_manual_award_rejects_role_holder_of_other_org(self) -> None:
        other_admin = CustomUser.objects.create_user(
            username="svc_other_admin", password="x"
        )
        self.other_org.admins.add(other_admin)
        with self.assertRaises(ValueError):
            create_manual_award(
                org=self.org,
                user=other_admin,
                points=5,
                reason="Wrong org",
                on_date=date(2026, 11, 1),
                actor=self.admin,
            )
        self.assertFalse(OrgUser.objects.filter(user=other_admin).exists())
        self.assertFalse(ContributionEntry.objects.exists())

    def test_manual_award_writes_org_log(self) -> None:
        entry = self._manual(points=12, reason="Casted finals")
        log = OrgLog.objects.get(organization=self.org, action="award_points")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_user, self.member)
        self.assertEqual(log.details["pk"], entry.pk)
        self.assertEqual(log.details["points"], 12)
        self.assertEqual(log.details["reason"], "Casted finals")

    # update_manual_award

    def test_update_manual_award_changes_fields_and_logs(self) -> None:
        entry = self._manual(points=7, reason="Old")
        updated = update_manual_award(
            entry,
            actor=self.admin,
            points=9,
            reason=" New ",
            on_date=date(2026, 10, 31),
            event=self.event,
        )
        updated.refresh_from_db()
        self.assertEqual(updated.points, 9)
        self.assertEqual(updated.reason, "New")
        self.assertEqual(updated.occurred_at, datetime(2026, 10, 31, 16, 0, tzinfo=UTC))
        self.assertEqual(updated.event, self.event)
        self.assertEqual(updated.event_name, "Svc Event")
        log = OrgLog.objects.get(organization=self.org, action="edit_award")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_user, self.member)
        self.assertEqual(log.details["pk"], entry.pk)
        self.assertEqual(log.details["old"]["points"], 7)
        self.assertEqual(log.details["new"]["points"], 9)
        self.assertEqual(log.details["old"]["reason"], "Old")
        self.assertEqual(log.details["new"]["reason"], "New")

    def test_update_manual_award_partial_keeps_other_fields(self) -> None:
        entry = self._manual(points=7, reason="Keep", event=self.event)
        update_manual_award(entry, actor=self.admin, points=8)
        entry.refresh_from_db()
        self.assertEqual(entry.points, 8)
        self.assertEqual(entry.reason, "Keep")
        self.assertEqual(entry.event, self.event)
        self.assertEqual(entry.occurred_at, datetime(2026, 11, 1, 17, 0, tzinfo=UTC))

    def test_update_manual_award_can_clear_event(self) -> None:
        entry = self._manual(event=self.event)
        update_manual_award(entry, actor=self.admin, event=None)
        entry.refresh_from_db()
        self.assertIsNone(entry.event)
        self.assertEqual(entry.event_name, "")

    def test_update_manual_award_rejects_out_of_range_points(self) -> None:
        entry = self._manual(points=7)
        for points in (0, -5, 1001, True):
            with self.assertRaises(ValueError, msg=f"points={points!r}"):
                update_manual_award(entry, actor=self.admin, points=points)
        entry.refresh_from_db()
        self.assertEqual(entry.points, 7)

    def test_update_manual_award_noop_skips_save_and_log(self) -> None:
        entry = self._manual(points=7, reason="Same", event=self.event)
        before = ContributionEntry.objects.get(pk=entry.pk).updated_at
        update_manual_award(entry, actor=self.admin)
        update_manual_award(
            entry, actor=self.admin, points=7, reason="Same", event=self.event
        )
        self.assertFalse(OrgLog.objects.filter(action="edit_award").exists())
        self.assertEqual(ContributionEntry.objects.get(pk=entry.pk).updated_at, before)

    def test_update_manual_award_rejects_blank_reason(self) -> None:
        entry = self._manual()
        with self.assertRaises(ValueError):
            update_manual_award(entry, actor=self.admin, reason="  ")

    def test_update_manual_award_rejects_foreign_event(self) -> None:
        entry = self._manual()
        with self.assertRaises(ValueError):
            update_manual_award(entry, actor=self.admin, event=self.foreign_event)

    def test_edit_and_delete_reject_non_manual(self) -> None:
        entry = self._auto(
            ContributionKind.EVENT_HOST, timezone.now(), event=self.event
        )
        with self.assertRaises(ValueError):
            update_manual_award(entry, actor=self.admin, points=3)
        with self.assertRaises(ValueError):
            delete_manual_award(entry, actor=self.admin)
        self.assertTrue(ContributionEntry.objects.filter(pk=entry.pk).exists())
        self.assertFalse(
            OrgLog.objects.filter(action__in=["edit_award", "delete_award"]).exists()
        )

    # delete_manual_award

    def test_delete_manual_award_logs(self) -> None:
        entry = self._manual(points=6, reason="Oops")
        pk = entry.pk
        delete_manual_award(entry, actor=self.admin)
        self.assertFalse(ContributionEntry.objects.filter(pk=pk).exists())
        log = OrgLog.objects.get(organization=self.org, action="delete_award")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.target_user, self.member)
        self.assertEqual(log.details["pk"], pk)
        self.assertEqual(log.details["points"], 6)
        self.assertEqual(log.details["reason"], "Oops")

    def test_edit_and_delete_after_concurrent_delete_raise_does_not_exist(
        self,
    ) -> None:
        entry = self._manual(points=6)
        stale = ContributionEntry.objects.get(pk=entry.pk)
        delete_manual_award(entry, actor=self.admin)
        with self.assertRaises(ContributionEntry.DoesNotExist):
            update_manual_award(stale, actor=self.admin, points=3)
        with self.assertRaises(ContributionEntry.DoesNotExist):
            delete_manual_award(stale, actor=self.admin)
        self.assertEqual(OrgLog.objects.filter(action="delete_award").count(), 1)
        self.assertFalse(OrgLog.objects.filter(action="edit_award").exists())

    # set_point_value

    def test_set_point_value_future_only_leaves_old_entries(self) -> None:
        old = self._auto(ContributionKind.EVENT_HOST, timezone.now(), event=self.event)
        result = set_point_value(
            self.org, ContributionKind.EVENT_HOST, 20, actor=self.admin
        )
        self.assertEqual(result, RescoreResult(old=10, new=20, changed=0))
        old.refresh_from_db()
        self.assertEqual(old.points, 10)
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 20)
        self.assertFalse(OrgLog.objects.filter(action="rescore").exists())
        log = OrgLog.objects.get(organization=self.org, action="set_point_value")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.details, {"kind": "event_host", "old": 10, "new": 20})

    def test_set_point_value_updates_existing_override(self) -> None:
        set_point_value(self.org, ContributionKind.EVENT_HOST, 20, actor=self.admin)
        result = set_point_value(
            self.org, ContributionKind.EVENT_HOST, 30, actor=self.admin
        )
        self.assertEqual(result.old, 20)
        self.assertEqual(result.new, 30)
        row = ContributionPointValue.objects.get(
            organization=self.org, kind=ContributionKind.EVENT_HOST
        )
        self.assertEqual(row.points, 30)
        self.assertEqual(row.updated_by, self.admin)

    def test_apply_to_past_updates_only_that_kind(self) -> None:
        now = timezone.now()
        host = self._auto(ContributionKind.EVENT_HOST, now, event=self.event)
        promo_a = self._auto(ContributionKind.PROMO_MESSAGE, now)
        promo_b = self._auto(ContributionKind.PROMO_MESSAGE, now)
        manual = self._manual(points=1)
        other_org_promo = award_entry(
            org=self.other_org,
            user=self.member,
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=now,
        )

        result = set_point_value(
            self.org,
            ContributionKind.PROMO_MESSAGE,
            3,
            actor=self.admin,
            apply_to_past=True,
        )

        self.assertEqual(result, RescoreResult(old=1, new=3, changed=2))
        for entry, expected in (
            (promo_a, 3),
            (promo_b, 3),
            (host, 10),
            (manual, 1),
            (other_org_promo, 1),
        ):
            entry.refresh_from_db()
            self.assertEqual(entry.points, expected, entry.kind)
        log = OrgLog.objects.get(organization=self.org, action="rescore")
        self.assertEqual(
            log.details,
            {"kind": "promo_message", "old": 1, "new": 3, "since": None, "changed": 2},
        )

    def test_apply_to_past_bumps_updated_at(self) -> None:
        entry = self._auto(ContributionKind.PROMO_MESSAGE, timezone.now())
        stale = timezone.now() - timedelta(days=3)
        ContributionEntry.objects.filter(pk=entry.pk).update(updated_at=stale)
        set_point_value(
            self.org,
            ContributionKind.PROMO_MESSAGE,
            4,
            actor=self.admin,
            apply_to_past=True,
        )
        entry.refresh_from_db()
        self.assertGreater(entry.updated_at, stale)

    def test_set_point_value_rejects_since_without_apply_to_past(self) -> None:
        with self.assertRaises(ValueError):
            set_point_value(
                self.org,
                ContributionKind.EVENT_HOST,
                20,
                actor=self.admin,
                since=date(2026, 11, 1),
            )
        self.assertFalse(ContributionPointValue.objects.exists())
        self.assertFalse(OrgLog.objects.filter(action="set_point_value").exists())

    def test_apply_to_past_since_is_local_day_start(self) -> None:
        # NY local day start of 2026-11-01 is 2026-11-01T04:00Z.
        before = self._auto(
            ContributionKind.EVENT_HELPER,
            datetime(2026, 11, 1, 3, 59, tzinfo=UTC),
        )
        at = self._auto(
            ContributionKind.EVENT_HELPER,
            datetime(2026, 11, 1, 4, 0, tzinfo=UTC),
        )
        after = self._auto(
            ContributionKind.EVENT_HELPER,
            datetime(2026, 11, 5, 0, 0, tzinfo=UTC),
        )

        result = set_point_value(
            self.org,
            ContributionKind.EVENT_HELPER,
            8,
            actor=self.admin,
            apply_to_past=True,
            since=date(2026, 11, 1),
        )

        self.assertEqual(result.changed, 2)
        before.refresh_from_db()
        at.refresh_from_db()
        after.refresh_from_db()
        self.assertEqual(before.points, 5)
        self.assertEqual(at.points, 8)
        self.assertEqual(after.points, 8)
        log = OrgLog.objects.get(organization=self.org, action="rescore")
        self.assertEqual(log.details["since"], "2026-11-01")
        self.assertEqual(log.details["changed"], 2)

    def test_reset_deletes_row_and_uses_default(self) -> None:
        set_point_value(self.org, ContributionKind.EVENT_HOST, 20, actor=self.admin)
        result = set_point_value(
            self.org, ContributionKind.EVENT_HOST, None, actor=self.admin
        )
        self.assertEqual(result, RescoreResult(old=20, new=10, changed=0))
        self.assertFalse(
            ContributionPointValue.objects.filter(
                organization=self.org, kind=ContributionKind.EVENT_HOST
            ).exists()
        )
        self.assertEqual(points_for(self.org, ContributionKind.EVENT_HOST), 10)

    def test_reset_with_apply_to_past_uses_default(self) -> None:
        entry = self._auto(
            ContributionKind.EVENT_HOST, timezone.now(), event=self.event
        )
        set_point_value(self.org, ContributionKind.EVENT_HOST, 20, actor=self.admin)
        set_point_value(
            self.org,
            ContributionKind.EVENT_HOST,
            None,
            actor=self.admin,
            apply_to_past=True,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.points, 10)

    def test_set_point_value_rejects_manual_kind(self) -> None:
        with self.assertRaises(ValueError):
            set_point_value(self.org, ContributionKind.MANUAL, 5, actor=self.admin)
        self.assertFalse(ContributionPointValue.objects.exists())

    def test_set_point_value_rejects_negative_points(self) -> None:
        with self.assertRaises(ValueError):
            set_point_value(self.org, ContributionKind.EVENT_HOST, -1, actor=self.admin)
        self.assertFalse(ContributionPointValue.objects.exists())
        self.assertFalse(OrgLog.objects.filter(action="set_point_value").exists())

    def test_set_point_value_rejects_above_max(self) -> None:
        self._auto(ContributionKind.PROMO_MESSAGE, timezone.now())
        for points in (POINT_VALUE_MAX + 1, 10**30):
            with self.subTest(points=points), self.assertRaises(ValueError):
                set_point_value(
                    self.org,
                    ContributionKind.PROMO_MESSAGE,
                    points,
                    actor=self.admin,
                    apply_to_past=True,
                )
        self.assertFalse(ContributionPointValue.objects.exists())
        self.assertFalse(
            OrgLog.objects.filter(action__in=["set_point_value", "rescore"]).exists()
        )
        self.assertEqual(
            ContributionEntry.objects.get().points,
            DEFAULT_POINTS[ContributionKind.PROMO_MESSAGE],
        )

    def test_set_point_value_accepts_max(self) -> None:
        result = set_point_value(
            self.org, ContributionKind.EVENT_HOST, POINT_VALUE_MAX, actor=self.admin
        )
        self.assertEqual(result.new, POINT_VALUE_MAX)

    # delete_user_entries

    def test_delete_user_entries_across_orgs(self) -> None:
        keeper = CustomUser.objects.create_user(username="svc_keeper", password="x")
        now = timezone.now()
        self._manual()
        self._auto(ContributionKind.PROMO_MESSAGE, now)
        award_entry(
            org=self.other_org,
            user=self.member,
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=now,
        )
        kept = award_entry(
            org=self.org,
            user=keeper,
            kind=ContributionKind.PROMO_MESSAGE,
            occurred_at=now,
        )

        deleted = delete_user_entries(self.member, actor=self.admin)

        self.assertEqual(deleted, 3)
        self.assertFalse(
            ContributionEntry.objects.filter(org_user__user=self.member).exists()
        )
        self.assertTrue(ContributionEntry.objects.filter(pk=kept.pk).exists())
        logs = OrgLog.objects.filter(action="delete_user_contributions")
        self.assertEqual(
            {log.organization_id: log.details["count"] for log in logs},
            {self.org.pk: 2, self.other_org.pk: 1},
        )
        for log in logs:
            self.assertEqual(log.actor, self.admin)
            self.assertEqual(log.target_user, self.member)

    def test_delete_user_entries_without_entries(self) -> None:
        self.assertEqual(delete_user_entries(self.member, actor=self.admin), 0)
        self.assertFalse(
            OrgLog.objects.filter(action="delete_user_contributions").exists()
        )
