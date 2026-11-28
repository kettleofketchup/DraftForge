from django.test import SimpleTestCase
from django.urls import resolve, reverse


class JokeRoutesTest(SimpleTestCase):
    def test_moved_paths_resolve_to_joke_views(self) -> None:
        for path, url_name in (
            ("/api/jokes/tangoes/", "get-tangoes"),
            ("/api/jokes/tangoes/buy/", "buy-tango"),
        ):
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(match.func.__module__, "joke.views")
                self.assertEqual(match.url_name, url_name)
                self.assertEqual(reverse(url_name), path)
