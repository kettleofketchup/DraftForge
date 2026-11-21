from cacheops.conf import model_profile
from django.conf import settings
from django.test import SimpleTestCase

from org.models import Organization, OrgLog


class OrganizationModelConfigTests(SimpleTestCase):
    def test_tables_and_labels(self) -> None:
        for model, table in (
            (Organization, "app_organization"),
            (OrgLog, "app_orglog"),
        ):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    (model._meta.app_label, model._meta.db_table), ("org", table)
                )
        for field, table in (
            ("admins", "app_organization_admins"),
            ("staff", "app_organization_staff"),
            ("promoters", "app_organization_promoters"),
        ):
            with self.subTest(field=field):
                through = Organization._meta.get_field(field).remote_field.through
                self.assertEqual(through._meta.db_table, table)

    def test_cacheops_profile(self) -> None:
        if not getattr(settings, "CACHEOPS", None):
            self.skipTest("CACHEOPS is empty (DISABLE_CACHE)")
        self.assertIsNotNone(model_profile(Organization))
        self.assertIsNone(model_profile(OrgLog))
