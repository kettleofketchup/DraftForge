from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from config.installed_apps import MODEL_APPS
from joke.models import Joke


class JokeRegistrationTest(SimpleTestCase):
    def test_web_only_registration(self) -> None:
        installed = list(settings.INSTALLED_APPS)
        self.assertEqual(installed.count("joke.apps.JokeConfig"), 1)
        index = installed.index("joke.apps.JokeConfig")
        self.assertEqual(installed[index - 1], "corsheaders")
        self.assertEqual(
            [entry for entry in MODEL_APPS if entry.split(".")[0] == "joke"], []
        )

    def test_model_label(self) -> None:
        self.assertEqual(Joke._meta.label, "joke.Joke")

    def test_url_names_reverse_to_public_paths(self) -> None:
        self.assertEqual(reverse("get-tangoes"), "/api/jokes/tangoes/")
        self.assertEqual(reverse("buy-tango"), "/api/jokes/tangoes/buy/")
