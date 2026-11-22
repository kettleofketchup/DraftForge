from org.leadership.kinds import DEFAULT_POINTS
from org.leadership.services import (
    TraitInUse,
    delete_trait,
    update_settings,
    upsert_traits,
)
from org.leadership.store import effective_traits, get_leadership_settings
from org.models import ContributionPointValue, Organization, OrgLog
from org.models_leadership import CaptainTrait, OrgLeadershipSettings
from org.tests.leadership_base import LeadershipTestCase


class LeadershipSettingsServiceTest(LeadershipTestCase):
    def test_defaults_without_a_row(self) -> None:
        row = get_leadership_settings(self.org)
        self.assertIsNone(row.pk)
        self.assertEqual(row.review_window_hours, 72)
        self.assertEqual(row.rating_min_reviewers, 2)
        self.assertEqual(OrgLeadershipSettings.objects.count(), 0)

    def test_update_creates_row_and_logs_once(self) -> None:
        update_settings(self.org, actor=self.admin, changes={"review_window_hours": 24})
        self.assertEqual(
            OrgLeadershipSettings.objects.get(
                organization=self.org
            ).review_window_hours,
            24,
        )
        update_settings(self.org, actor=self.admin, changes={"review_window_hours": 24})
        self.assertEqual(
            OrgLog.objects.filter(action="update_leadership_settings").count(), 1
        )

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            update_settings(self.org, actor=self.admin, changes={"bogus": 1})

    def test_max_age_below_half_life_rejected(self) -> None:
        with self.assertRaises(ValueError):
            update_settings(
                self.org,
                actor=self.admin,
                changes={"max_age_days": 100, "half_life_days": 180},
            )

    def test_point_overrides(self) -> None:
        update_settings(self.org, actor=self.admin, changes={}, points={"captained": 7})
        self.assertEqual(
            ContributionPointValue.objects.get(
                organization=self.org, kind="captained"
            ).points,
            7,
        )
        update_settings(
            self.org, actor=self.admin, changes={}, points={"captained": None}
        )
        self.assertFalse(
            ContributionPointValue.objects.filter(organization=self.org).exists()
        )
        self.assertNotIn("captain_rating", DEFAULT_POINTS)
        with self.assertRaises(ValueError):
            update_settings(
                self.org, actor=self.admin, changes={}, points={"captain_rating": 3}
            )


class CaptainTraitServiceTest(LeadershipTestCase):
    def test_effective_traits_are_unsaved_defaults(self) -> None:
        traits = effective_traits(self.org)
        self.assertEqual(
            [t.key for t in traits],
            ["communication", "drafting", "composure", "sportsmanship"],
        )
        self.assertTrue(all(t.pk is None for t in traits))

    def test_upsert_materialises_renames_and_adds(self) -> None:
        upsert_traits(
            self.org,
            actor=self.admin,
            items=[
                {"key": "drafting", "label": "Draft calls"},
                {"key": "shotcalling", "label": "Shotcalling", "order": 9},
            ],
        )
        rows = {
            t.key: t.label for t in CaptainTrait.objects.filter(organization=self.org)
        }
        self.assertEqual(rows["drafting"], "Draft calls")
        self.assertEqual(rows["shotcalling"], "Shotcalling")
        self.assertEqual(len(rows), 5)

    def test_active_limits(self) -> None:
        with self.assertRaises(ValueError):
            upsert_traits(
                self.org,
                actor=self.admin,
                items=[{"key": f"extra{i}", "label": f"E{i}"} for i in range(5)],
            )
        with self.assertRaises(ValueError):
            upsert_traits(
                self.org,
                actor=self.admin,
                items=[
                    {"key": t.key, "active": False} for t in effective_traits(self.org)
                ],
            )

    def test_delete_scored_trait_refused_unscored_deleted(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        with self.assertRaises(TraitInUse):
            delete_trait(self.org, actor=self.admin, key="drafting")
        upsert_traits(
            self.org, actor=self.admin, items=[{"key": "spare", "label": "Spare"}]
        )
        delete_trait(self.org, actor=self.admin, key="spare")
        self.assertFalse(CaptainTrait.objects.filter(key="spare").exists())

    def test_cross_org_key_not_found(self) -> None:
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        upsert_traits(
            other, actor=self.admin, items=[{"key": "only_there", "label": "X"}]
        )
        with self.assertRaises(CaptainTrait.DoesNotExist):
            delete_trait(self.org, actor=self.admin, key="only_there")
