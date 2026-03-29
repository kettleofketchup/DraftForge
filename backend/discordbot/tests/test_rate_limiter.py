from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings


class DiscordRateLimiterTest(TestCase):
    @override_settings(DISCORD_RATE_LIMIT=40, DISCORD_RATE_LIMIT_BURST=40)
    @patch("discordbot.utils.redis_client")
    def test_acquire_token_succeeds(self, mock_redis):
        mock_redis.eval.return_value = 1
        from discordbot.utils import _acquire_rate_limit_token

        self.assertTrue(_acquire_rate_limit_token())

    @override_settings(DISCORD_RATE_LIMIT=40, DISCORD_RATE_LIMIT_BURST=40)
    @patch("discordbot.utils.redis_client")
    def test_acquire_token_blocks_when_empty(self, mock_redis):
        mock_redis.eval.side_effect = [0, 1]
        from discordbot.utils import _acquire_rate_limit_token

        self.assertTrue(_acquire_rate_limit_token(max_wait=2.0))
        self.assertEqual(mock_redis.eval.call_count, 2)

    @override_settings(DISCORD_RATE_LIMIT=40, DISCORD_RATE_LIMIT_BURST=40)
    @patch("discordbot.utils.redis_client")
    def test_acquire_token_timeout(self, mock_redis):
        mock_redis.eval.return_value = 0
        from discordbot.utils import _acquire_rate_limit_token

        with self.assertRaises(RuntimeError):
            _acquire_rate_limit_token(max_wait=0.1)


class RateLimitedRequestTest(TestCase):
    @patch("discordbot.utils._acquire_rate_limit_token")
    @patch("discordbot.utils.requests.request")
    def test_retries_on_429(self, mock_request, mock_acquire):
        mock_acquire.return_value = True
        resp_429 = MagicMock(status_code=429)
        resp_429.json.return_value = {"retry_after": 0.01}
        resp_ok = MagicMock(status_code=200)
        resp_ok.json.return_value = {"id": "123"}
        mock_request.side_effect = [resp_429, resp_ok]
        from discordbot.utils import _rate_limited_request

        result = _rate_limited_request("POST", "https://example.com", json={})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)
