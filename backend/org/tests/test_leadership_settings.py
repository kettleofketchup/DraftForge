from structlog.testing import capture_logs

from org.leadership.kinds import DEFAULT_POINTS
from org.leadership.settings import (
    get_leadership_settings,
    leadership_points,
    update_leadership_settings,
)
from org.models import ContributionPointValue, OrgLog
from org.models_leadership import OrgLeadershipSettings
from org.tests.leadership_base import LeadershipTestCase


class LeadershipSettingsServiceTest(LeadershipTestCase):
    def test_defaults_without_a_row(self) -> None:
        row = get_leadership_settings(self.org)
        self.assertIsNone(row.pk)
        self.assertEqual(row.review_window_hours, 72)
        self.assertEqual(row.rating_min_reviewers, 2)
        self.assertEqual(get_leadership_settings(self.org.pk).pk, None)
        self.assertEqual(OrgLeadershipSettings.objects.count(), 0)

    def test_create_flag_creates_row(self) -> None:
        row = get_leadership_settings(self.org, create=True)
        self.assertIsNotNone(row.pk)
        self.assertEqual(OrgLeadershipSettings.objects.count(), 1)

    def test_update_creates_row_and_logs_once(self) -> None:
        update_leadership_settings(
            self.org, actor=self.admin, changes={"review_window_hours": 24}
        )
        row = OrgLeadershipSettings.objects.get(organization=self.org)
        self.assertEqual(row.review_window_hours, 24)
        self.assertEqual(row.updated_by, self.admin)
        stamp = row.updated_at
        update_leadership_settings(
            self.org, actor=self.admin, changes={"review_window_hours": 24}
        )
        logs = OrgLog.objects.filter(action="update_leadership_settings")
        self.assertEqual(logs.count(), 1)
        self.assertEqual(
            logs.get().details,
            {"changed_fields": ["review_window_hours"], "points": {}},
        )
        row.refresh_from_db()
        self.assertEqual(row.updated_at, stamp)

    def test_update_invalidates_cached_read(self) -> None:
        get_leadership_settings(self.org, create=True)
        self.assertEqual(get_leadership_settings(self.org).review_window_hours, 72)
        with self.captureOnCommitCallbacks(execute=True):
            update_leadership_settings(
                self.org, actor=self.admin, changes={"review_window_hours": 12}
            )
        self.assertEqual(get_leadership_settings(self.org).review_window_hours, 12)

    def test_logs_on_commit(self) -> None:
        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                update_leadership_settings(
                    self.org, actor=self.admin, changes={"leaderboard_public": True}
                )
        events = [e for e in logs if e["event"] == "leadership_settings_updated"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["system"], "org")
        self.assertEqual(events[0]["subsystem"], "leadership")
        self.assertEqual(events[0]["changed_fields"], ["leaderboard_public"])

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            update_leadership_settings(self.org, actor=self.admin, changes={"bogus": 1})

    def test_out_of_range_rejected(self) -> None:
        for changes in (
            {"rating_min_reviewers": 1},
            {"review_window_hours": 0},
            {"prior_rating": 5.5},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                update_leadership_settings(self.org, actor=self.admin, changes=changes)
        self.assertFalse(
            OrgLog.objects.filter(action="update_leadership_settings").exists()
        )

    def test_defaults_include_release_gate(self) -> None:
        row = get_leadership_settings(self.org)
        self.assertIs(row.require_staff_release, False)
        self.assertIsNone(row.auto_release_after_hours)

    def test_validate_accepts_null_hours(self) -> None:
        update_leadership_settings(
            self.org, actor=self.admin, changes={"auto_release_after_hours": None}
        )

    def test_validate_accepts_valid_release_values(self) -> None:
        for hours in (1, 720):
            with self.subTest(hours=hours):
                update_leadership_settings(
                    self.org,
                    actor=self.admin,
                    changes={
                        "require_staff_release": True,
                        "auto_release_after_hours": hours,
                    },
                )
                row = OrgLeadershipSettings.objects.nocache().get(organization=self.org)
                self.assertIs(row.require_staff_release, True)
                self.assertEqual(row.auto_release_after_hours, hours)

    def test_validate_rejects_out_of_range_hours(self) -> None:
        for hours in (0, 721):
            with (
                self.subTest(hours=hours),
                self.assertRaisesRegex(ValueError, "between 1 and 720"),
            ):
                update_leadership_settings(
                    self.org,
                    actor=self.admin,
                    changes={"auto_release_after_hours": hours},
                )

    def test_validate_rejects_null_on_non_nullable(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be null"):
            update_leadership_settings(
                self.org, actor=self.admin, changes={"review_window_hours": None}
            )

    def test_validate_rejects_non_bool_gate(self) -> None:
        for changes in ({"require_staff_release": 1}, {"leaderboard_public": "yes"}):
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "must be true or false"),
            ):
                update_leadership_settings(self.org, actor=self.admin, changes=changes)

    def test_max_age_below_half_life_rejected(self) -> None:
        with self.assertRaises(ValueError):
            update_leadership_settings(
                self.org,
                actor=self.admin,
                changes={"max_age_days": 100, "half_life_days": 180},
            )

    def test_point_overrides(self) -> None:
        ContributionPointValue.objects.create(
            organization=self.org, kind="placement_1", points=12
        )
        update_leadership_settings(
            self.org,
            actor=self.admin,
            changes={},
            points={"captained": 7, "placement_1": None},
        )
        self.assertEqual(
            dict(
                ContributionPointValue.objects.filter(
                    organization=self.org
                ).values_list("kind", "points")
            ),
            {"captained": 7},
        )
        self.assertEqual(
            OrgLog.objects.get(action="update_leadership_settings").details,
            {
                "changed_fields": [],
                "points": {
                    "captained": {"old": None, "new": 7},
                    "placement_1": {"old": 12, "new": None},
                },
            },
        )
        self.assertEqual(
            leadership_points(self.org),
            {**DEFAULT_POINTS, "captained": 7},
        )

    def test_unchanged_points_write_nothing(self) -> None:
        update_leadership_settings(
            self.org, actor=self.admin, changes={}, points={"captained": 7}
        )
        update_leadership_settings(
            self.org,
            actor=self.admin,
            changes={},
            points={"captained": 7, "placement_2": None},
        )
        self.assertEqual(
            OrgLog.objects.filter(action="update_leadership_settings").count(), 1
        )

    def test_invalid_points_rejected(self) -> None:
        self.assertNotIn("captain_rating", DEFAULT_POINTS)
        for points in ({"captain_rating": 3}, {"captained": -1}, {"captained": 1001}):
            with self.subTest(points=points), self.assertRaises(ValueError):
                update_leadership_settings(
                    self.org, actor=self.admin, changes={}, points=points
                )
        self.assertFalse(
            ContributionPointValue.objects.filter(organization=self.org).exists()
        )

    def test_leadership_points_defaults(self) -> None:
        self.assertEqual(leadership_points(self.org), DEFAULT_POINTS)
