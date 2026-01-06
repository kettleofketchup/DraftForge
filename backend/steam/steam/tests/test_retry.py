from unittest.mock import MagicMock

from django.test import TestCase

from steam.utils.retry import retry_with_backoff


class RetryUtilityTest(TestCase):
    def test_success_on_first_try(self):
        func = MagicMock(return_value="success")
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertTrue(success)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 1)

    def test_success_after_retry(self):
        func = MagicMock(side_effect=[Exception("fail"), Exception("fail"), "success"])
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertTrue(success)
        self.assertEqual(result, "success")
        self.assertEqual(func.call_count, 3)

    def test_failure_after_max_retries(self):
        func = MagicMock(side_effect=Exception("always fails"))
        success, result = retry_with_backoff(func, max_retries=3, base_delay=0.01)
        self.assertFalse(success)
        self.assertIsInstance(result, Exception)
        self.assertEqual(func.call_count, 3)
