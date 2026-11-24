from django.test import SimpleTestCase
from django.urls import resolve


class UserURLHomesTests(SimpleTestCase):
    def test_user_routes_resolve_to_user_app(self) -> None:
        routes = {
            "/api/users/search/": "search_users",
            "/api/users/bulk/": "bulk_users",
            "/api/users/steam-account-id/1/": "steam_account_id_lookup",
            "/api/users/1/": "users-detail",
            "/api/current_user": None,
            "/api/profile_update": "profile_update",
            "/api/avatars/refresh/": "refresh-avatars",
            "/api/internal/users/avatar-check/": None,
            "/api/internal/users/1/avatar/": None,
            "/api/users/1/ssr/": "user_ssr",
            "/api/user/register": None,
        }
        for path, name in routes.items():
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.url_name, name)
                self.assertTrue(match.func.__module__.startswith("user."), match.func)
