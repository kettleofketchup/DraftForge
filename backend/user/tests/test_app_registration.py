import json
import os
import subprocess
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase
from django.urls import URLResolver, get_resolver, resolve

from config.installed_apps import MODEL_APPS


class UserAppRegistrationTests(SimpleTestCase):
    def test_app_is_installed(self):
        assert apps.is_installed("user")

    def test_app_config_name(self):
        config = apps.get_app_config("user")
        assert config.name == "user"

    def test_placeholder_url_resolves(self):
        match = resolve("/api/users/me/profile/")
        assert match.url_name == "me-profile"

    def test_web_user_registration_keeps_original_position(self) -> None:
        installed = list(settings.INSTALLED_APPS)
        self.assertEqual(installed.count("user.apps.UserConfig"), 1)
        self.assertEqual(MODEL_APPS.count("user.apps.UserConfig"), 1)
        index = installed.index("user.apps.UserConfig")
        self.assertEqual(
            installed[index - 1 : index + 2],
            ["bracket.apps.BracketConfig", "user.apps.UserConfig", "cacheops"],
        )
        self.assertEqual(
            [entry for entry in installed if entry in MODEL_APPS],
            [entry for entry in MODEL_APPS if entry != "user.apps.UserConfig"]
            + ["user.apps.UserConfig"],
        )

    def test_admin_resolver_order_matches_task1_baseline(self) -> None:
        admin = next(
            route
            for route in get_resolver().url_patterns
            if isinstance(route, URLResolver) and route.namespace == "admin"
        )
        model_routes = [
            str(route.pattern).strip("/").replace("/", "_")
            for route in admin.url_patterns
            if isinstance(route, URLResolver)
        ]
        self.assertEqual(
            model_routes,
            [
                "auth_group",
                "draft_herodraft",
                "draft_herodraftevent",
                "draft_herodraftchatmessage",
                "app_customuser",
                "tournament_teamlog",
                "events_eventrepeater",
                "events_event",
                "events_eventteam",
                "events_signupledgerentry",
                "events_eventsignup",
                "events_readycheck",
                "events_readycheckentry",
                "events_eventvoicepresence",
                "discordbot_eventtemplate",
                "discordbot_scheduledevent",
                "discordbot_rsvp",
                "discordbot_discordmessagelog",
                "discordbot_discordevent",
                "discordbot_discordeventmsgsignup",
                "discordbot_discordeventmsgannouncement",
                "discordbot_discordeventlog",
                "discordbot_discordtournamentlog",
                "discordbot_discordeventdm",
                "discordbot_draftactivitychannel",
                "discordbot_draftactivityinstance",
                "discordbot_discorddm",
                "org_orguser",
                "org_orgusergamemmr",
                "org_mmrchangerequest",
                "org_orgfeature",
                "org_orgsettings",
                "org_orgapitoken",
                "org_orgapitokenusage",
                "org_orgapilimits",
                "league_leagueuser",
                "lobby_gamelobby",
                "lobby_gamelobbyevent",
                "opsnotices_opsnotice",
                "social_django_usersocialauth",
                "social_django_nonce",
                "social_django_association",
                "user_baseuserprofile",
                "user_dotauserprofile",
                "user_deadlockuserprofile",
            ],
        )
        app_list = next(
            route
            for route in admin.url_patterns
            if getattr(route, "name", None) == "app_list"
        )
        self.assertEqual(
            str(app_list.pattern),
            r"^(?P<app_label>auth|draft|app|tournament|events|discordbot|org|league|lobby|opsnotices|social_django|user)/$",
        )

    def test_celery_still_installs_user_once(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import django, json; django.setup(); "
                "from django.apps import apps; from django.conf import settings; "
                "print(json.dumps([apps.get_app_config('user').name, "
                "settings.INSTALLED_APPS.count('user.apps.UserConfig')]))",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings_celery"},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        self.assertEqual(
            json.loads(result.stdout.strip().splitlines()[-1]), ["user", 1]
        )
