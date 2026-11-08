"""populate_all must not reach the network when no credentials are configured.

Environments that seed test data behind default-deny egress (CI sandboxes,
throwaway preview deployments) have no Discord or Steam credentials. A single
outbound connect there never completes, so seeding hangs. This test refuses
every connect to a public address while populate_all runs and fails if any
happened. Loopback and private addresses stay open, because the test stack's
Redis runs on a container network.
"""

import ipaddress
import socket
import traceback
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings


def _is_internal(address):
    if not isinstance(address, tuple):
        return True  # AF_UNIX
    try:
        return not ipaddress.ip_address(address[0]).is_global
    except ValueError:
        return address[0] == "localhost"


# The test runner forces DEBUG=False; the populate helpers refuse to create
# test-login users unless the settings describe a test environment.
@override_settings(
    DEBUG=True,
    DISCORD_BOT_TOKEN=None,
    SOCIAL_AUTH_DISCORD_KEY=None,
    SOCIAL_AUTH_DISCORD_SECRET=None,
)
class PopulateAllOfflineTest(TransactionTestCase):
    def test_populate_all_makes_no_outbound_connection(self):
        import tests.populate.utils as populate_utils
        from tests.populate import populate_all

        attempts = []
        real_connect = socket.socket.connect

        def guarded_connect(sock, address):
            if _is_internal(address):
                return real_connect(sock, address)
            attempts.append((address, "".join(traceback.format_stack(limit=15))))
            raise OSError(f"outbound connection blocked by test: {address!r}")

        # The avatar map is memoised per process; reset it so this run decides
        # for itself whether to call Discord.
        with (
            patch.object(populate_utils, "_discord_avatar_cache", None),
            patch.object(socket.socket, "connect", guarded_connect),
        ):
            populate_all(force=True)

        self.assertEqual(
            attempts,
            [],
            "populate_all attempted outbound connections:\n"
            + "\n".join(f"{addr!r}\n{stack}" for addr, stack in attempts),
        )
