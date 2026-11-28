import ipaddress
import json
import socket
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from ssl import create_default_context
from urllib.parse import urlsplit

from urllib3._collections import HTTPHeaderDict
from urllib3.connection import HTTPSConnection
from urllib3.response import HTTPResponse


class SafeHttpError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_EMBEDDED_V4 = tuple(
    ipaddress.ip_network(prefix)
    for prefix in (
        "::/96",
        "::ffff:0:0/96",
        "2002::/16",
        "2001::/32",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
    )
)
_DNS_WORKER = """
import json, socket, sys
host = json.loads(sys.stdin.read(4096))
answers = socket.getaddrinfo(host, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
if not 0 < len(answers) <= 64:
    sys.exit(1)
print(json.dumps([answer[4][0] for answer in answers]))
"""


def remaining(deadline: float) -> float:
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise SafeHttpError("deadline_exceeded")
    return seconds


def public_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
        if (
            not address.is_global
            or address.is_reserved
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or (address.version == 6 and any(address in net for net in _EMBEDDED_V4))
        ):
            raise ValueError
        return str(address)
    except ValueError:
        raise SafeHttpError("unsafe_address") from None


def _resolve(host: str, deadline: float) -> tuple[str, ...]:
    remaining(deadline)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return (str(address),)
    # libc DNS is not cancellable in a thread. Isolate it so a timeout reaps it.
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", _DNS_WORKER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd="/",
    )
    try:
        output, _ = child.communicate(
            json.dumps(host).encode(), timeout=remaining(deadline)
        )
        if child.returncode != 0 or len(output) > 8192:
            raise SafeHttpError("dns_failed")
        values = json.loads(output)
        if (
            not isinstance(values, list)
            or not 0 < len(values) <= 64
            or any(type(item) is not str for item in values)
        ):
            raise SafeHttpError("dns_failed")
        remaining(deadline)
        return tuple(values)
    except subprocess.TimeoutExpired:
        raise SafeHttpError("deadline_exceeded") from None
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()


def public_answers(host: str, deadline: float) -> frozenset[str]:
    answers = _resolve(host, deadline)
    if not 0 < len(answers) <= 64:
        raise SafeHttpError("dns_failed")
    return frozenset(public_address(answer) for answer in answers)


class _PinnedConnection(HTTPSConnection):
    def __init__(self, host: str, deadline: float) -> None:
        super().__init__(
            host,
            port=443,
            timeout=remaining(deadline),
            ssl_context=create_default_context(),
            cert_reqs="CERT_REQUIRED",
            assert_hostname=host,
            server_hostname=host,
        )
        self.set_debuglevel(0)
        self.deadline = deadline
        self.watch_socket: socket.socket | None = None
        self.watchdog: threading.Timer | None = None

    def _expire(self) -> None:
        if self.watch_socket is not None:
            try:
                self.watch_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _new_conn(self) -> socket.socket:
        addresses = public_answers(self.host, self.deadline)
        address = sorted(addresses)[0]
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(remaining(self.deadline))
            sock.connect((address, 443))
            if str(ipaddress.ip_address(sock.getpeername()[0])) not in addresses:
                raise SafeHttpError("peer_mismatch")
            # A duplicate retains the TCP endpoint when TLS takes ownership of sock.
            self.watch_socket = sock.dup()
            self.watchdog = threading.Timer(remaining(self.deadline), self._expire)
            self.watchdog.daemon = True
            self.watchdog.start()
            return sock
        except BaseException:
            sock.close()
            raise

    def getresponse(self) -> HTTPResponse:
        # urllib3's header-parse warning logs the rendered URL and remote headers.
        response = HTTPConnection.getresponse(self)
        try:
            return HTTPResponse(
                body=response,
                headers=HTTPHeaderDict(response.getheaders()),
                status=response.status,
                preload_content=False,
                decode_content=False,
                original_response=response,
                enforce_content_length=True,
            )
        except BaseException:
            response.close()
            raise

    def finish(self) -> None:
        if self.watchdog is not None:
            self.watchdog.cancel()
            self.watchdog.join()
            self.watchdog = None
        if self.watch_socket is not None:
            self.watch_socket.close()
            self.watch_socket = None
        super().close()


class PinnedHTTPSAdapter:
    """One verified socket, no pool, redirects, environment, retries or cookies."""

    def __init__(self, url: str, deadline: float) -> None:
        host = urlsplit(url).hostname
        if host is None:
            raise SafeHttpError("invalid_url")
        self.connection = _PinnedConnection(host, deadline)
        self.deadline = deadline

    def send(
        self, method: str, target: str, body: bytes | None, headers: dict[str, str]
    ) -> HTTPResponse:
        remaining(self.deadline)
        self.connection.request(
            method,
            target,
            body=body,
            headers=headers,
            preload_content=False,
            decode_content=False,
        )
        remaining(self.deadline)
        return self.connection.getresponse()

    def close(self) -> None:
        self.connection.finish()
