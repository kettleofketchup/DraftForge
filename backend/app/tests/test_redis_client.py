from django.test import SimpleTestCase

from app.redis_client import get_redis_client, set_client_for_tests

UNUSED_DB = 15


class RedisClientTimeoutTests(SimpleTestCase):
    def tearDown(self) -> None:
        set_client_for_tests(None, db=UNUSED_DB)

    def test_client_times_out_instead_of_blocking(self) -> None:
        set_client_for_tests(None, db=UNUSED_DB)
        kwargs = get_redis_client(UNUSED_DB).connection_pool.connection_kwargs
        self.assertEqual(kwargs["socket_timeout"], 2)
        self.assertEqual(kwargs["socket_connect_timeout"], 2)
