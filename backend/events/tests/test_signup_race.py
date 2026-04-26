import threading
from datetime import timedelta

from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization, PositionsModel
from events.constants import EventState
from events.models import Event
from events.services import staff_add_signup


class StaffAddSignupRaceTest(TransactionTestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(username="race_admin", password="x")
        self.admin.positions = PositionsModel.objects.create()
        self.admin.save()
        self.user = CustomUser.objects.create_user(username="race_user", password="x")
        self.user.positions = PositionsModel.objects.create()
        self.user.save()
        self.org = Organization.objects.create(name="Race Org", owner=self.admin)
        self.event = Event.objects.create(
            organization=self.org,
            name="Race Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.ROLL_CALL,
            created_by=self.admin,
            tournament_name="T",
            max_players=10,
        )

    def test_concurrent_staff_add_for_same_user_only_one_succeeds(self):
        results = {"success": 0, "errors": 0}
        lock = threading.Lock()
        barrier = threading.Barrier(2)  # force actual contention on the unique constraint

        def worker():
            try:
                # Both threads block here until both have arrived, so the inserts
                # race on the unique_event_user_signup constraint.
                barrier.wait(timeout=5)
                staff_add_signup(self.event, self.user)
                with lock:
                    results["success"] += 1
            except Exception:
                with lock:
                    results["errors"] += 1
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["success"] == 1, results
        assert results["errors"] == 1, results
