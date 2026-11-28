import ipaddress
import json
import math
import re
import ssl
import time
import zlib
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import quote, unquote, urlencode, urlsplit

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from urllib3.exceptions import SSLError
from urllib3.response import HTTPResponse
from urllib3.util.ssl_match_hostname import CertificateError

from org.api_connections.crypto import CredentialError, canonical_origin
from org.api_connections.limits import (
    CONFIG_BYTES,
    CREDENTIAL_BYTES,
    PAGE_BYTES,
    REQUEST_SECONDS,
)
from org.api_connections.tls_adapter import (
    PinnedHTTPSAdapter,
    SafeHttpError,
    public_address,
    public_answers,
    remaining,
)
from org.api_connections.types import (
    SafeHttpRawResponse,
    SafeHttpRequest,
    SafeHttpResponse,
)

tracer = trace.get_tracer(__name__)


def canonical_url(url: str) -> str:
    try:
        origin = canonical_origin(url)
        parts = urlsplit(url)
        host = urlsplit(origin).hostname
        if (
            len(url) > 2048
            or parts.port not in (None, 443)
            or "?" in url
            or "#" in url
            or host is None
            or host.endswith(".")
            or any(ord(char) <= 32 or ord(char) == 127 for char in unquote(parts.path))
        ):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or re.fullmatch(
                r"[0-9]+|0x[0-9a-f]+", host.rsplit(".", 1)[-1]
            ):
                raise ValueError
        else:
            public_address(host)
        authority = f"[{host}]" if ":" in host else host
        return f"https://{authority}{quote(parts.path or '/', safe='/%:@!$&\'()*+,;=-._~')}"
    except (CredentialError, ValueError, UnicodeError):
        raise SafeHttpError("invalid_url") from None


def public_origin(url: str) -> str:
    """Canonical origin of ``url`` once every DNS answer is public; no request is sent."""
    host = urlsplit(canonical_url(url)).hostname
    if not host:
        raise SafeHttpError("invalid_url")
    public_answers(host, time.monotonic() + REQUEST_SECONDS)
    return canonical_origin(url)


def _render(
    request: SafeHttpRequest, url: str
) -> tuple[str, bytes | None, dict[str, str]]:
    query = dict(request.query)
    body = dict(request.body) if request.body is not None else None
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }
    if request.idempotency_key is not None:
        headers["Idempotency-Key"] = request.idempotency_key
    if request.auth != "none":
        if (
            request.credential is None
            or not 0 < len(request.credential.encode()) <= CREDENTIAL_BYTES
            or request.credential_origin != canonical_origin(url)
            or any(ord(char) < 32 or ord(char) == 127 for char in request.credential)
        ):
            raise SafeHttpError("invalid_credential")
        if request.auth == "bearer":
            headers["Authorization"] = f"Bearer {request.credential}"
        elif request.auth == "api_key_header":
            headers["X-API-Key"] = request.credential
        elif request.credential_field is not None:
            field = request.credential_field
            if field.location == "query":
                query[field.key] = request.credential
            elif body is not None:
                body[field.key] = request.credential
            else:
                raise SafeHttpError("invalid_request")
        else:
            raise SafeHttpError("invalid_request")
    elif request.credential is not None or request.credential_field is not None:
        raise SafeHttpError("invalid_request")
    if request.method == "GET" and body is not None:
        raise SafeHttpError("invalid_request")
    encoded_body = None
    if body is not None and request.body_encoding == "canonical":
        encoded_body = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    elif body is not None:
        encoded_body = json.dumps(body, allow_nan=False, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    for value in query.values():
        values = value if isinstance(value, list) else [value]
        if any(
            type(item) not in (str, int, float, bool, type(None)) for item in values
        ):
            raise SafeHttpError("invalid_request")
    suffix = urlencode(query, doseq=True)
    target = urlsplit(url).path + (f"?{suffix}" if suffix else "")
    if (
        len(target.encode()) + len(encoded_body or b"")
        > CONFIG_BYTES + CREDENTIAL_BYTES
    ):
        raise SafeHttpError("request_too_large")
    return target, encoded_body, headers


def _read_body(response: HTTPResponse, deadline: float, cap: int) -> bytes:
    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
    if encoding not in ("identity", "gzip", "deflate"):
        raise SafeHttpError("unsupported_encoding")
    decoder = (
        None
        if encoding == "identity"
        else zlib.decompressobj(31 if encoding == "gzip" else 15)
    )
    result = bytearray()
    wire_bytes = 0
    while True:
        remaining(deadline)
        chunk = response.read1(8192, decode_content=False)
        remaining(deadline)
        if not chunk:
            break
        wire_bytes += len(chunk)
        if wire_bytes > PAGE_BYTES:
            raise SafeHttpError("response_too_large")
        decoded = decoder.decompress(chunk, cap - len(result) + 1) if decoder else chunk
        result.extend(decoded)
        if len(result) > cap:
            raise SafeHttpError("response_too_large")
        if decoder and decoder.unused_data:
            raise SafeHttpError("invalid_compression")
    if decoder and not decoder.eof:
        raise SafeHttpError("invalid_compression")
    remaining(deadline)
    return bytes(result)


def _read_json(response: HTTPResponse, deadline: float, cap: int) -> SafeHttpResponse:
    if 300 <= response.status < 400:
        raise SafeHttpError("redirect_forbidden")
    result = _read_body(response, deadline, cap)
    try:
        data = json.loads(result) if result else None
    except ValueError:
        if 200 <= response.status < 300:
            raise SafeHttpError("invalid_json") from None
        data = None
    remaining(deadline)
    return SafeHttpResponse(
        status=response.status, data=data, bytes_received=len(result)
    )


def _read_raw(response: HTTPResponse, deadline: float, cap: int) -> SafeHttpRawResponse:
    body = _read_body(response, deadline, cap)
    retry_after = response.headers.get("Retry-After")
    return SafeHttpRawResponse(
        status=response.status,
        body=body,
        retry_after=retry_after[:64] if retry_after is not None else None,
    )


def request_json(
    request: SafeHttpRequest, *, deadline: float, max_bytes: int = PAGE_BYTES
) -> SafeHttpResponse:
    return _send(request, deadline, max_bytes, _read_json)


def request_bytes(
    request: SafeHttpRequest, *, deadline: float, max_bytes: int = PAGE_BYTES
) -> SafeHttpRawResponse:
    """Like ``request_json`` but returns the undecoded body; 3xx is not followed."""
    return _send(request, deadline, max_bytes, _read_raw)


def _send[T: (SafeHttpResponse, SafeHttpRawResponse)](
    request: SafeHttpRequest,
    deadline: float,
    max_bytes: int,
    reader: Callable[[HTTPResponse, float, int], T],
) -> T:
    adapter: PinnedHTTPSAdapter | None = None
    response: HTTPResponse | None = None
    if (
        type(max_bytes) is not int
        or not 0 < max_bytes <= PAGE_BYTES
        or not math.isfinite(deadline)
    ):
        raise SafeHttpError("invalid_request")
    deadline = min(deadline, time.monotonic() + REQUEST_SECONDS)
    # Suppress library URL/exception capture; this span contains fixed metadata only.
    with (
        suppress_instrumentation(),
        tracer.start_as_current_span(
            "org.api_connections.http",
            record_exception=False,
            set_status_on_exception=False,
        ) as span,
    ):
        try:
            url = canonical_url(request.url)
            target, body, headers = _render(request, url)
            adapter = PinnedHTTPSAdapter(url, deadline)
            response = adapter.send(request.method, target, body, headers)
            result = reader(response, deadline, max_bytes)
            span.set_attribute("http.response.status_code", result.status)
            return result
        except SafeHttpError as exc:
            span.set_attribute("error.type", exc.code)
            raise
        except (ssl.SSLError, SSLError, CertificateError):
            code = "deadline_exceeded" if time.monotonic() >= deadline else "tls_failed"
            span.set_attribute("error.type", code)
            raise SafeHttpError(code) from None
        except Exception:
            code = (
                "deadline_exceeded"
                if time.monotonic() >= deadline
                else "network_failed"
            )
            span.set_attribute("error.type", code)
            raise SafeHttpError(code) from None
        finally:
            if response is not None:
                with suppress(Exception):
                    response.close()
            if adapter is not None:
                with suppress(Exception):
                    adapter.close()
