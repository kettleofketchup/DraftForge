from django.contrib import admin
from django.test import RequestFactory, TestCase

from app.models import CustomUser, GameType, Organization
from org.admin import OrgUserAdmin, OrgUserGameMmrInline
from org.models import OrgUser, OrgUserGameMmr

ADD_URL = "/admin/org/orgusergamemmr/add/"


def change_url(pk: int) -> str:
    return f"/admin/org/orgusergamemmr/{pk}/change/"


class OrgUserGameMmrAdminTest(TestCase):
    def setUp(self) -> None:
        self.superuser = CustomUser.objects.create_superuser(
            username="mmr_admin", password="x", email="mmr@example.com"
        )
        self.client.force_login(self.superuser)
        self.org = Organization.objects.create(name="Admin MMR Org")
        player = CustomUser.objects.create(username="mmr_player")
        self.org_user = OrgUser.objects.create(user=player, organization=self.org)
        self.dota = OrgUserGameMmr.objects.create(
            org_user=self.org_user, game_type=GameType.DOTA2, mmr=4000
        )
        OrgUserGameMmr.objects.create(
            org_user=self.org_user, game_type=GameType.DEADLOCK, mmr=2500
        )

    def test_add_view_forbidden(self) -> None:
        self.assertEqual(self.client.get(ADD_URL).status_code, 403)

    def test_change_post_forbidden_and_row_unchanged(self) -> None:
        response = self.client.post(
            change_url(self.dota.pk),
            {
                "org_user": self.org_user.pk,
                "game_type": GameType.DOTA2,
                "mmr": 1,
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.dota.refresh_from_db()
        self.assertEqual(self.dota.mmr, 4000)

    def test_inline_is_read_only(self) -> None:
        request = RequestFactory().get("/")
        request.user = self.superuser
        inline = OrgUserGameMmrInline(OrgUser, admin.site)
        self.assertFalse(inline.has_add_permission(request, self.org_user))
        self.assertFalse(inline.has_change_permission(request, self.org_user))
        self.assertFalse(inline.has_delete_permission(request, self.org_user))
        self.assertIn(OrgUserGameMmrInline, OrgUserAdmin.inlines)

    def test_orguser_change_view_renders_inline_without_controls(self) -> None:
        response = self.client.get(f"/admin/org/orguser/{self.org_user.pk}/change/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("game_mmrs", content)
        self.assertNotIn("game_mmrs-0-DELETE", content)
        self.assertNotIn("add-row", content)

    def test_changelist_mmrs_column(self) -> None:
        model_admin = OrgUserAdmin(OrgUser, admin.site)
        self.assertNotIn("mmr", model_admin.list_display)
        request = RequestFactory().get("/")
        request.user = self.superuser
        org_user = model_admin.get_queryset(request).get(pk=self.org_user.pk)
        self.assertEqual(model_admin.mmrs(org_user), "D2 4000 · DL 2500")

    def test_changelist_renders(self) -> None:
        response = self.client.get("/admin/org/orguser/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("D2 4000 · DL 2500", response.content.decode())
