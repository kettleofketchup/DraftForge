from org.leadership.traits import (
    TraitInUse,
    delete_trait,
    effective_traits,
    materialize_traits,
    upsert_traits,
)
from org.models import Organization, OrgLog
from org.models_leadership import CaptainTrait
from org.tests.leadership_base import LeadershipTestCase

DEFAULT_KEYS = ["communication", "drafting", "composure", "sportsmanship"]


class CaptainTraitServiceTest(LeadershipTestCase):
    def test_effective_traits_are_unsaved_defaults(self) -> None:
        traits = effective_traits(self.org.pk)
        self.assertEqual([t.key for t in traits], DEFAULT_KEYS)
        self.assertEqual([t.order for t in traits], [0, 1, 2, 3])
        self.assertTrue(all(t.pk is None for t in traits))
        self.assertFalse(CaptainTrait.objects.exists())

    def test_effective_traits_active_only(self) -> None:
        upsert_traits(
            self.org,
            actor=self.admin,
            items=[{"key": "composure", "active": False}],
        )
        self.assertEqual(
            [t.key for t in effective_traits(self.org.pk, active_only=True)],
            ["communication", "drafting", "sportsmanship"],
        )
        self.assertEqual(len(effective_traits(self.org.pk)), 4)

    def test_materialize_is_idempotent(self) -> None:
        first = materialize_traits(self.org.pk)
        second = materialize_traits(self.org.pk)
        self.assertEqual([t.key for t in first], DEFAULT_KEYS)
        self.assertEqual([t.pk for t in first], [t.pk for t in second])
        self.assertEqual(CaptainTrait.objects.filter(organization=self.org).count(), 4)

    def test_upsert_materialises_renames_and_adds(self) -> None:
        traits = upsert_traits(
            self.org,
            actor=self.admin,
            items=[
                {"key": "drafting", "label": "Draft calls"},
                {"key": "shotcalling", "label": "Shotcalling", "order": 9},
            ],
        )
        rows = {t.key: t.label for t in traits}
        self.assertEqual(rows["drafting"], "Draft calls")
        self.assertEqual(rows["shotcalling"], "Shotcalling")
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            OrgLog.objects.get(action="update_captain_traits").details,
            {"created": ["shotcalling"], "updated": ["drafting"]},
        )

    def test_upsert_without_changes_logs_nothing(self) -> None:
        upsert_traits(
            self.org,
            actor=self.admin,
            items=[{"key": "drafting", "label": "Drafting"}],
        )
        self.assertFalse(OrgLog.objects.filter(action="update_captain_traits").exists())

    def test_invalid_items_rejected(self) -> None:
        for items in (
            [{"key": "Bad Key", "label": "Bad"}],
            [{"key": "nolabel"}],
        ):
            with self.subTest(items=items), self.assertRaises(ValueError):
                upsert_traits(self.org, actor=self.admin, items=items)

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
                items=[{"key": key, "active": False} for key in DEFAULT_KEYS],
            )
        self.assertFalse(
            CaptainTrait.objects.filter(organization=self.org, key="extra0").exists()
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
        self.assertEqual(
            OrgLog.objects.filter(action="update_captain_traits")
            .order_by("pk")
            .last()
            .details,
            {"deleted": ["spare"]},
        )

    def test_cross_org_key_not_found(self) -> None:
        other = Organization.objects.create(name="Other Org", owner=self.admin)
        upsert_traits(
            other, actor=self.admin, items=[{"key": "only_there", "label": "X"}]
        )
        with self.assertRaises(CaptainTrait.DoesNotExist):
            delete_trait(self.org, actor=self.admin, key="only_there")
