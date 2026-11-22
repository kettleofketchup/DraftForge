"""django-linear-migrations is active in dev/test and every max_migration.txt is current."""

from django.apps import apps
from django.core.checks import Tags, run_checks
from django.test import SimpleTestCase


class MaxMigrationFilesTest(SimpleTestCase):
    def test_linear_migrations_installed(self) -> None:
        # settings.py skips the app when the package is missing (release image);
        # the dev/test image must have it or the check below never runs.
        self.assertTrue(apps.is_installed("django_linear_migrations"))

    def test_max_migration_files_match_latest_migrations(self) -> None:
        errors = [e for e in run_checks(tags=[Tags.models]) if e.id.startswith("dlm.")]
        self.assertEqual(errors, [], "\n".join(str(e) for e in errors))
