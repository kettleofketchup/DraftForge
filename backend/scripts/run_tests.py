"""Run the full test suite and capture results."""

import os
import sys

os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings"
os.environ["DISABLE_CACHE"] = "true"

import django

django.setup()

from django.test.runner import DiscoverRunner

runner = DiscoverRunner(verbosity=2)
failures = runner.run_tests(["events.tests", "discordbot.tests", "org.tests"])
sys.exit(failures)
