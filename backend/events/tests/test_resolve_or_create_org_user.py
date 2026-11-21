from django.test import TestCase

import events.services
from app.models import CustomUser
from events.services import resolve_or_create_org_user
from org.membership import resolve_or_create_org_user as membership_fn
from org.models import Organization, OrgUser


class ResolveOrCreateOrgUserTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create(username="u1")
        self.org = Organization.objects.create(name="Org 1")

    def test_creates_when_missing(self):
        org_user = resolve_or_create_org_user(self.user, self.org)
        self.assertIsInstance(org_user, OrgUser)
        self.assertEqual(org_user.user, self.user)
        self.assertEqual(org_user.organization, self.org)

    def test_reuses_existing(self):
        existing = OrgUser.objects.create(user=self.user, organization=self.org)
        org_user = resolve_or_create_org_user(self.user, self.org)
        self.assertEqual(org_user.pk, existing.pk)

    def test_idempotent(self):
        a = resolve_or_create_org_user(self.user, self.org)
        b = resolve_or_create_org_user(self.user, self.org)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(
            OrgUser.objects.filter(user=self.user, organization=self.org).count(),
            1,
        )

    def test_is_the_membership_function(self) -> None:
        self.assertIs(events.services.resolve_or_create_org_user, membership_fn)
