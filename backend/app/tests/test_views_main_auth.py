from django.test import TestCase
from django.urls import NoReverseMatch, reverse


class AjaxAuthRemovedTest(TestCase):
    def test_route_is_not_reversible(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("ajax-auth", kwargs={"backend": "discord"})

    def test_route_returns_404(self) -> None:
        response = self.client.get("/ajax-auth/discord/")

        self.assertEqual(response.status_code, 404)
