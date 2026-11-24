"""DELETE on /api/users/ only deletes through destroy and its cleanup."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.models import CustomUser


class UserDeleteRouteTests(TestCase):
    def setUp(self) -> None:
        self.staff = CustomUser.objects.create_user(
            username="del_staff", password="x", is_staff=True, is_superuser=True
        )
        self.victim = CustomUser.objects.create_user(
            username="del_victim", password="x"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    @patch("user.views_account.standing.on_user_deleted")
    @patch("user.views_account.release_earning_sends")
    def test_detail_delete_runs_destroy_cleanup(
        self, release: MagicMock, on_deleted: MagicMock
    ) -> None:
        released: list[int] = []
        release.side_effect = lambda user: released.append(user.pk)
        victim_pk = self.victim.pk

        response = self.client.delete(f"/api/users/{victim_pk}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(CustomUser.objects.filter(pk=victim_pk).exists())
        self.assertEqual(released, [victim_pk])
        on_deleted.assert_called_once()
        self.assertEqual(on_deleted.call_args.kwargs["actor"], self.staff)

    def test_list_delete_is_not_allowed(self) -> None:
        response = self.client.delete("/api/users/")

        self.assertEqual(response.status_code, 405)
        self.assertTrue(CustomUser.objects.filter(pk=self.victim.pk).exists())
