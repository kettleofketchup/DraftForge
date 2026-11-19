"""Shared raw Redis clients, one per database, for the web and worker processes."""

import redis
from django.conf import settings

_clients: dict[int, redis.Redis] = {}


def get_redis_client(db: int = 2) -> redis.Redis:
    """Get or create the client for ``db`` on ``settings.REDIS_HOST``."""
    client = _clients.get(db)
    if client is None:
        client = redis.Redis(
            host=getattr(settings, "REDIS_HOST", "localhost"),
            port=6379,
            db=db,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        _clients[db] = client
    return client


def set_client_for_tests(client: object | None, db: int = 2) -> None:
    """Install a stand-in client for ``db``; None drops it so the next call reconnects."""
    if client is None:
        _clients.pop(db, None)
    else:
        _clients[db] = client  # type: ignore[assignment]
