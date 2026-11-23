"""A TransactionTestCase flush must take this run's cacheops entries with it.

The flush deletes rows with raw SQL, so cacheops never invalidates what it cached
for them. Primary keys come back (reset_sequences, or a migration test rebuilding
a table), and a later test then reads a deleted row from the cache.
"""

from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser
from events.models import Event
from org.models import Organization
from tournament.models import Tournament
from tournament.serializers.users import tournament_organization
from user.tests.test_cacheops_integration import _redis_reachable


class FlushDropsRunCacheTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        if not _redis_reachable():
            self.skipTest("Cacheops Redis not reachable")

    def test_a_caches_the_source_event_organization(self) -> None:
        owner = CustomUser.objects.create_user(username="flush_cache_owner")
        org = Organization.objects.create(name="Flushed Org", owner=owner)
        tournament = Tournament.objects.create(
            name="Flushed Cup", date_played=timezone.now()
        )
        Event.objects.create(
            organization=org,
            name="Flushed Event",
            scheduled_at=timezone.now(),
            created_by=owner,
            tournament=tournament,
        )
        self.assertEqual(tournament_organization(tournament), org)

    def test_b_reused_pk_reads_the_database(self) -> None:
        tournament = Tournament.objects.create(
            name="Reused Cup", date_played=timezone.now()
        )
        self.assertEqual(tournament.pk, 1)
        self.assertIsNone(tournament_organization(tournament))
