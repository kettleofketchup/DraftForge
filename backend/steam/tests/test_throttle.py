import time
from unittest.mock import MagicMock, patch

from django.test import TestCase

from steam.utils.retry import throttle_request


class ThrottleRequestTest(TestCase):
    def test_throttle_enforces_minimum_delay(self):
        """Verify throttle decorator enforces 0.5s minimum delay."""
        call_times = []

        @throttle_request(min_delay=0.5)
        def mock_request():
            call_times.append(time.time())
            return "ok"

        # Make 3 rapid calls
        for _ in range(3):
            mock_request()

        # Verify delays between calls
        for i in range(1, len(call_times)):
            elapsed = call_times[i] - call_times[i - 1]
            self.assertGreaterEqual(elapsed, 0.49)  # Allow small timing variance

    def test_throttle_no_delay_when_time_elapsed(self):
        """Verify throttle doesn't add unnecessary delay when enough time has passed."""
        # Reset the global state by patching
        with patch("steam.utils.retry._last_request_time", 0.0):
            call_times = []

            @throttle_request(min_delay=0.1)
            def mock_request():
                call_times.append(time.time())
                return "ok"

            # First call should not delay
            start = time.time()
            mock_request()
            first_call_duration = time.time() - start

            # First call shouldn't have significant delay
            self.assertLess(first_call_duration, 0.15)

    def test_throttle_preserves_function_return_value(self):
        """Verify throttle decorator preserves the function's return value."""

        @throttle_request(min_delay=0.01)
        def mock_request():
            return {"result": "success"}

        result = mock_request()
        self.assertEqual(result, {"result": "success"})

    def test_throttle_preserves_function_arguments(self):
        """Verify throttle decorator passes arguments correctly."""

        @throttle_request(min_delay=0.01)
        def mock_request(a, b, c=None):
            return (a, b, c)

        result = mock_request(1, 2, c=3)
        self.assertEqual(result, (1, 2, 3))
