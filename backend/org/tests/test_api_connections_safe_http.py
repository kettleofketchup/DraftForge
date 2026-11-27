import gzip
import json
import logging
import os
import socket
import ssl
import subprocess
import threading
import time
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace, TracebackType
from unittest.mock import patch

from django.test import SimpleTestCase
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from org.api_connections import safe_http, tls_adapter
from org.api_connections.safe_http import SafeHttpError, canonical_url, request_json
from org.api_connections.types import SafeHttpRequest
from org.tests.fixtures.api_connections.tls_server import tls_endpoint

FIXTURES = Path(__file__).parent / "fixtures" / "api_connections"
PUBLIC = "93.184.216.34"
URL = "https://sync.example/ratings"


class ConnectedSocket:
    def __init__(self, sock: socket.socket, peer: str, dials: list[object]) -> None:
        self.sock = sock
        self.peer = peer
        self.dials = dials

    def connect(self, address: object) -> None:
        self.dials.append(address)

    def getpeername(self) -> tuple[str, int]:
        return self.peer, 443

    def __getattr__(self, name: str) -> object:
        return getattr(self.sock, name)


class TlsFixture:
    def __init__(
        self,
        response: bytes = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}",
        *,
        peer: str = PUBLIC,
        stall: bool = False,
        observe_eof: bool = False,
        stall_handshake: bool = False,
    ) -> None:
        self.client, self.server = socket.socketpair()
        self.response = response
        self.peer = peer
        self.stall = stall
        self.observe_eof = observe_eof
        self.stall_handshake = stall_handshake
        self.eof = threading.Event()
        self.dials: list[object] = []
        self.names: list[str | None] = []
        self.request = b""
        self.errors: list[Exception] = []
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(FIXTURES / "server.crt", FIXTURES / "server.key")
        self.context.set_servername_callback(self.on_name)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.release = threading.Event()

    def on_name(
        self, sock: ssl.SSLSocket, name: str | None, ctx: ssl.SSLContext
    ) -> None:
        self.names.append(name)

    def serve(self) -> None:
        if self.stall_handshake:
            self.release.wait(3)
            return
        try:
            with self.context.wrap_socket(self.server, server_side=True) as sock:
                sock.settimeout(3)
                while b"\r\n\r\n" not in self.request:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    self.request += chunk
                sock.sendall(self.response)
                if self.observe_eof and not sock.recv(1):
                    self.eof.set()
                if self.stall:
                    self.release.wait(3)
        except (OSError, ssl.SSLError) as exc:
            self.errors.append(exc)

    def __enter__(self) -> "TlsFixture":
        self.thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release.set()
        self.client.close()
        self.server.close()
        self.thread.join(4)

    def socket(self, *args: object, **kwargs: object) -> ConnectedSocket:
        return ConnectedSocket(self.client, self.peer, self.dials)

    def client_context(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=str(FIXTURES / "server.crt"))


class SafeHttpTests(SimpleTestCase):
    def assert_code(
        self, request: SafeHttpRequest, code: str, **kwargs: object
    ) -> None:
        with self.assertRaises(SafeHttpError) as caught:
            request_json(request, deadline=time.monotonic() + 2, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_canonical_idna_ip_and_url_policy(self) -> None:
        self.assertEqual(
            canonical_url("https://BÜCHER.example:443/a"),
            "https://xn--bcher-kva.example/a",
        )
        self.assertEqual(
            canonical_url("https://[2606:4700:4700::1111]/"),
            "https://[2606:4700:4700::1111]/",
        )
        for url in (
            "http://example.com/",
            "https://example.com:444/",
            "https://user:pass@example.com/",
            "https://example.com/#fragment",
            "https://example.com/#",
            "https://example.com/?key=x",
            "https://example.com\\@evil.com/",
            "https://example.com./",
            "https://example.com:/",
            "https://example.com/\n",
            "https://[fe80::1%25eth0]/",
            "https://127.1/",
            "https://2130706433/",
            "https://0x7f000001/",
            "https://example.com/%0d%0aX:yes",
        ):
            with self.subTest(url=url), self.assertRaises(SafeHttpError):
                canonical_url(url)

    def test_any_unsafe_answer_rejects_all(self) -> None:
        for address in (
            "0.0.0.0",
            "10.0.0.1",
            "127.0.0.1",
            "169.254.169.254",
            "172.16.0.1",
            "192.168.1.1",
            "100.100.100.200",
            "192.0.2.1",
            "224.0.0.1",
            "240.0.0.1",
            "::",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
            "2001:db8::1",
            "::ffff:93.184.216.34",
            "::93.184.216.34",
            "2002:5db8:d822::1",
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",
            "64:ff9b::a9fe:a9fe",
            "64:ff9b:1::1",
        ):
            with (
                self.subTest(address=address),
                patch.object(tls_adapter, "_resolve", return_value=(PUBLIC, address)),
                patch.object(
                    tls_adapter.socket,
                    "socket",
                    side_effect=AssertionError("unsafe dial"),
                ),
            ):
                self.assert_code(SafeHttpRequest(url=URL), "unsafe_address")

    def call_fixture(
        self,
        server: TlsFixture,
        request: SafeHttpRequest | None = None,
        **kwargs: object,
    ) -> object:
        with (
            patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
            patch.object(tls_adapter.socket, "socket", side_effect=server.socket),
            patch.object(
                tls_adapter, "create_default_context", side_effect=server.client_context
            ),
        ):
            return request_json(
                request or SafeHttpRequest(url=URL),
                deadline=time.monotonic() + 2,
                **kwargs,
            )

    def test_idempotency_header_and_non_json_bodies(self) -> None:
        key = "0f8c2b6e-1d2a-4c3b-9e5f-7a6b5c4d3e2f"
        with TlsFixture() as server:
            self.call_fixture(server, SafeHttpRequest(url=URL, idempotency_key=key))
        self.assertIn(f"Idempotency-Key: {key}".encode(), server.request)
        with self.assertRaises(ValueError):
            SafeHttpRequest(url=URL, idempotency_key="bad\r\nX-Injected: 1")
        with TlsFixture(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nnope") as server:
            with self.assertRaises(SafeHttpError) as caught:
                self.call_fixture(server)
        self.assertEqual(caught.exception.code, "invalid_json")
        with TlsFixture(
            b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 4\r\n\r\nnope"
        ) as server:
            response = self.call_fixture(server)
        self.assertEqual(response.status, 502)
        self.assertIsNone(response.data)

    def test_rebinding_never_redials_hostname(self) -> None:
        with (
            TlsFixture() as server,
            patch.object(
                socket, "getaddrinfo", side_effect=AssertionError("hostname redial")
            ),
        ):
            result = self.call_fixture(server)
            self.assertEqual(result.data, {})
            self.assertEqual(server.dials, [(PUBLIC, 443)])

    def test_real_tcp_socket_retains_numeric_dial_and_original_tls_name(self) -> None:
        with tls_endpoint(FIXTURES, PUBLIC) as server:
            sockets = SimpleNamespace(
                AF_INET=socket.AF_INET,
                AF_INET6=socket.AF_INET6,
                SOCK_STREAM=socket.SOCK_STREAM,
                SHUT_RDWR=socket.SHUT_RDWR,
                socket=lambda family, kind: server.new_socket(family),
            )
            context = ssl.create_default_context(cafile=str(FIXTURES / "server.crt"))
            with (
                patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
                patch.object(tls_adapter, "socket", sockets),
                patch.object(
                    tls_adapter, "create_default_context", return_value=context
                ),
            ):
                response = request_json(
                    SafeHttpRequest(url=URL), deadline=time.monotonic() + 2
                )
            self.assertEqual(response.data, {"ok": True})
            self.assertEqual(server.targets, [(PUBLIC, 443)])
            self.assertEqual(server.sni, ["sync.example"])
            self.assertIn(b"Host: sync.example\r\n", server.received)

    def test_untrusted_certificate_is_refused(self) -> None:
        with TlsFixture() as server:
            with (
                patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
                patch.object(tls_adapter.socket, "socket", side_effect=server.socket),
            ):
                self.assert_code(SafeHttpRequest(url=URL), "tls_failed")

    def test_connected_peer_must_match_validated_set(self) -> None:
        with TlsFixture(peer="127.0.0.1") as server:
            with self.assertRaises(SafeHttpError) as caught:
                self.call_fixture(server)
            self.assertEqual(caught.exception.code, "peer_mismatch")
            self.assertEqual(server.names, [])

    def test_tls_sni_host_and_certificate_use_original_hostname(self) -> None:
        with TlsFixture() as server:
            self.call_fixture(server)
            self.assertEqual(server.names, ["sync.example"])
            self.assertIn(b"Host: sync.example\r\n", server.request)
        with TlsFixture() as server:
            with self.assertRaises(SafeHttpError) as caught:
                self.call_fixture(server, SafeHttpRequest(url="https://wrong.example/"))
            self.assertEqual(caught.exception.code, "tls_failed")

    def test_redirect_proxy_cookie_netrc_forbidden(self) -> None:
        response = b"HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/\r\nSet-Cookie: session=secret\r\nContent-Length: 0\r\n\r\n"
        with (
            TlsFixture(response) as server,
            patch.dict(
                os.environ,
                {"HTTPS_PROXY": "http://127.0.0.1:1", "NETRC": "/nonexistent"},
            ),
        ):
            with self.assertRaises(SafeHttpError) as caught:
                self.call_fixture(server)
            self.assertEqual(caught.exception.code, "redirect_forbidden")
            self.assertEqual(len(server.dials), 1)
            self.assertNotIn(b"Cookie:", server.request)
            self.assertNotIn(b"Authorization:", server.request)

    def test_close_delimited_redirect_releases_socket_with_retained_exception(
        self,
    ) -> None:
        for response, code in (
            (
                b"HTTP/1.1 302 Found\r\nConnection: close\r\nLocation: /elsewhere\r\n\r\n",
                "redirect_forbidden",
            ),
            (
                b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 2, 3\r\n\r\n{}",
                "network_failed",
            ),
        ):
            retained: list[SafeHttpError] = []
            with (
                self.subTest(code=code),
                TlsFixture(response, observe_eof=True) as server,
            ):
                try:
                    self.call_fixture(server)
                except SafeHttpError as exc:
                    retained.append(exc)
                self.assertEqual(retained[0].code, code)
                self.assertIsNotNone(retained[0].__traceback__)
                self.assertTrue(
                    server.eof.wait(0.5), "response socket retained by traceback"
                )

    def test_parser_seam_handles_chunking_and_truncation(self) -> None:
        cases = (
            (b"Transfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n", True),
            (b"Transfer-Encoding: chunked\r\n\r\nZ\r\n{}\r\n", False),
            (b"Content-Length: 3\r\n\r\n{}", False),
            (b"Content-Length: 2, 3\r\n\r\n{}", False),
        )
        for body, success in cases:
            with (
                self.subTest(body=body),
                TlsFixture(b"HTTP/1.1 200 OK\r\n" + body) as server,
            ):
                if success:
                    self.assertEqual(self.call_fixture(server).data, {})
                else:
                    with self.assertRaises(SafeHttpError):
                        self.call_fixture(server)

    def test_close_delimited_and_partial_headers_share_deadline(self) -> None:
        for response in (
            b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n{",
            b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 20\r\n\r\n{",
            b"HTTP/1.1 200 OK\r\nX-Incomplete:",
        ):
            start = time.monotonic()
            with (
                self.subTest(response=response),
                TlsFixture(response, stall=True) as server,
            ):
                with (
                    patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
                    patch.object(
                        tls_adapter.socket, "socket", side_effect=server.socket
                    ),
                    patch.object(
                        tls_adapter,
                        "create_default_context",
                        side_effect=server.client_context,
                    ),
                ):
                    with self.assertRaises(SafeHttpError) as caught:
                        request_json(SafeHttpRequest(url=URL), deadline=start + 0.2)
                self.assertEqual(caught.exception.code, "deadline_exceeded")
            self.assertLess(time.monotonic() - start, 1)

    def test_slow_tls_handshake_uses_absolute_deadline(self) -> None:
        start = time.monotonic()
        with TlsFixture(stall_handshake=True) as server:
            with (
                patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
                patch.object(tls_adapter.socket, "socket", side_effect=server.socket),
                patch.object(
                    tls_adapter,
                    "create_default_context",
                    side_effect=server.client_context,
                ),
            ):
                with self.assertRaises(SafeHttpError) as caught:
                    request_json(SafeHttpRequest(url=URL), deadline=start + 0.2)
            self.assertEqual(caught.exception.code, "deadline_exceeded")
        self.assertLess(time.monotonic() - start, 1)

    def test_decompression_bomb_stops_at_cap(self) -> None:
        compressed = gzip.compress(b'"' + b"a" * 2000000 + b'"')
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: "
            + str(len(compressed)).encode()
            + b"\r\n\r\n"
            + compressed
        )
        with TlsFixture(response) as server:
            with self.assertRaises(SafeHttpError) as caught:
                self.call_fixture(server, max_bytes=1024)
            self.assertEqual(caught.exception.code, "response_too_large")

    def test_dns_and_slow_stream_share_absolute_deadline(self) -> None:
        # A blocked resolver process must be killed and reaped, not abandoned in a thread.
        child = subprocess.Popen(
            ["/bin/cat"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )
        with patch.object(tls_adapter.subprocess, "Popen", return_value=child):
            with patch.object(
                child,
                "communicate",
                side_effect=[subprocess.TimeoutExpired("dns", 0.01), (b"", b"")],
            ):
                with self.assertRaises(SafeHttpError) as caught:
                    tls_adapter._resolve("sync.example", time.monotonic() + 0.01)
        child.wait(timeout=2)
        self.assertEqual(caught.exception.code, "deadline_exceeded")
        self.assertIsNotNone(child.returncode)
        start = time.monotonic()
        with TlsFixture(
            b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\n{", stall=True
        ) as server:
            with (
                patch.object(tls_adapter, "_resolve", return_value=(PUBLIC,)),
                patch.object(tls_adapter.socket, "socket", side_effect=server.socket),
                patch.object(
                    tls_adapter,
                    "create_default_context",
                    side_effect=server.client_context,
                ),
            ):
                with self.assertRaises(SafeHttpError) as caught:
                    request_json(SafeHttpRequest(url=URL), deadline=start + 0.2)
            self.assertEqual(caught.exception.code, "deadline_exceeded")
        self.assertLess(time.monotonic() - start, 1)

    def test_dns_timeout_reaps_actual_resolver_process(self) -> None:
        children: list[subprocess.Popen[bytes]] = []
        popen = subprocess.Popen

        def record_child(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        start = time.monotonic()
        with (
            patch.object(tls_adapter, "_DNS_WORKER", "import signal; signal.pause()"),
            patch.object(tls_adapter.subprocess, "Popen", side_effect=record_child),
        ):
            with self.assertRaises(SafeHttpError) as caught:
                tls_adapter._resolve("sync.example", start + 0.1)
        self.assertEqual(caught.exception.code, "deadline_exceeded")
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertLess(time.monotonic() - start, 1)

    def test_credentials_cannot_cross_origins(self) -> None:
        for origin in (None, "https://other.example:443"):
            request = SafeHttpRequest(
                url=URL,
                auth="bearer",
                credential="super-secret",
                credential_origin=origin,
            )
            with patch.object(
                tls_adapter, "_resolve", side_effect=AssertionError("must not dial")
            ):
                self.assert_code(request, "invalid_credential")

    def test_exception_with_secret_url_never_stringified(self) -> None:
        class SecretError(Exception):
            def __str__(self) -> str:
                raise AssertionError("secret exception stringified")

        with patch.object(
            tls_adapter, "_resolve", side_effect=SecretError("secret-url")
        ):
            self.assert_code(SafeHttpRequest(url=URL), "network_failed")

    def test_malformed_response_headers_never_log_rendered_query(self) -> None:
        response = b"HTTP/1.1 200 OK\r\nmalformed header\r\nContent-Length: 2\r\n\r\n{}"
        request = SafeHttpRequest(
            url=URL,
            auth="api_key_field",
            credential="super-secret",
            credential_origin="https://sync.example:443",
            credential_field={"location": "query", "key": "key"},
        )
        captured = StringIO()
        handler = logging.StreamHandler(captured)
        logger = logging.getLogger("urllib3.connection")
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            with TlsFixture(response) as server:
                self.call_fixture(server, request)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertNotIn("super-secret", captured.getvalue())

    def test_process_debug_http_setting_never_prints_credentials(self) -> None:
        request = SafeHttpRequest(
            url=URL,
            auth="bearer",
            credential="super-secret",
            credential_origin="https://sync.example:443",
        )
        output = StringIO()
        with (
            TlsFixture() as server,
            patch.object(tls_adapter.HTTPConnection, "debuglevel", 1),
            redirect_stdout(output),
        ):
            self.call_fixture(server, request)
        self.assertNotIn("super-secret", output.getvalue())

    def test_query_auth_does_not_enter_exported_telemetry_or_repr(self) -> None:
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        request = SafeHttpRequest(
            url=URL,
            auth="api_key_field",
            credential="super-secret",
            credential_origin="https://sync.example:443",
            credential_field={"location": "query", "key": "key"},
            query={"page": 1},
        )
        self.assertNotIn("super-secret", repr(request))
        with (
            TlsFixture() as server,
            patch.object(safe_http, "tracer", provider.get_tracer("test")),
        ):
            self.call_fixture(server, request)
            self.assertIn(b"?page=1&key=super-secret ", server.request)
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        serialized = json.dumps([span.to_json() for span in spans])
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("?page", serialized)
        provider.shutdown()
