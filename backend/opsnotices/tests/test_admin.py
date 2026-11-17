from django.urls import reverse

from app.models import CustomUser
from events.tests.base import EventTestCase
from opsnotices.models import OpsNotice


class OpsNoticeAdminTests(EventTestCase):
    def test_changelist_and_change_render(self) -> None:
        superuser = CustomUser.objects.create_superuser(
            username="ops_admin", password="testpass"
        )
        notice = OpsNotice.objects.create(
            organization=self.org,
            event=self.event,
            event_key=self.event.id,
            event_name=self.event.name,
            key="test.thing",
            category="log",
            severity="info",
        )
        self.client.force_login(superuser)

        changelist = self.client.get(reverse("admin:opsnotices_opsnotice_changelist"))
        change = self.client.get(
            reverse("admin:opsnotices_opsnotice_change", args=[notice.pk])
        )

        self.assertEqual(changelist.status_code, 200)
        self.assertEqual(change.status_code, 200)
