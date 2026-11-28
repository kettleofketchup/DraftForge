import os
import socket
import ssl
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class RedirectedSocket(socket.socket):
    def __init__(self, family: int, endpoint: "TlsEndpoint") -> None:
        super().__init__(family, socket.SOCK_STREAM)
        self.endpoint = endpoint

    def connect(self, address: tuple[str, int]) -> None:
        self.endpoint.targets.append(address)
        super().connect(self.endpoint.address)

    def getpeername(self) -> tuple[str, int]:
        return (self.endpoint.public_ip, 443)

    def dup(self) -> socket.socket:
        return socket.socket(
            self.family, self.type, self.proto, fileno=os.dup(self.fileno())
        )


class TlsEndpoint:
    def __init__(self, directory: Path, public_ip: str) -> None:
        self.public_ip = public_ip
        self.sni: list[str | None] = []
        self.received = b""
        self.targets: list[tuple[str, int]] = []
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(directory / "server.crt", directory / "server.key")
        self.context.set_servername_callback(self.record_sni)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(5)
        self.address = self.listener.getsockname()
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def record_sni(
        self, sock: ssl.SSLSocket, name: str | None, context: ssl.SSLContext
    ) -> None:
        self.sni.append(name)

    def new_socket(self, family: int) -> RedirectedSocket:
        return RedirectedSocket(family, self)

    def serve(self) -> None:
        try:
            client, _ = self.listener.accept()
            with client:
                with self.context.wrap_socket(client, server_side=True) as secured:
                    secured.settimeout(5)
                    while b"\r\n\r\n" not in self.received:
                        chunk = secured.recv(4096)
                        if not chunk:
                            return
                        self.received += chunk
                    secured.sendall(
                        b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 11\r\n\r\n{"ok":true}'
                    )
        except (OSError, ssl.SSLError):
            return


@contextmanager
def tls_endpoint(directory: Path, public_ip: str) -> Iterator[TlsEndpoint]:
    endpoint = TlsEndpoint(directory, public_ip)
    endpoint.thread.start()
    try:
        yield endpoint
    finally:
        endpoint.listener.close()
        endpoint.thread.join(timeout=6)
        if endpoint.thread.is_alive():
            raise AssertionError("TLS fixture failed to stop")
