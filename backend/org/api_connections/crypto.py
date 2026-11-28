import base64
import binascii
import ipaddress
import json
import re
import secrets
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

from org.api_connections.limits import CREDENTIAL_BYTES


class CredentialError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical_origin(url: str) -> str:
    try:
        if (
            not isinstance(url, str)
            or any(ord(c) <= 32 or ord(c) == 127 for c in url)
            or "\\" in url
        ):
            raise ValueError
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
        ):
            raise ValueError
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if "%" in host:
            raise ValueError
        if ":" in host:
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        elif (
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                for label in host.split(".")
            )
            or len(host) > 253
        ):
            raise ValueError
        port = parts.port if parts.port is not None else 443
        if not 1 <= port <= 65535 or parts.netloc.endswith(":"):
            raise ValueError
        return f"https://{host}:{port}"
    except (ValueError, UnicodeError):
        raise CredentialError("invalid_origin") from None


def credential_key_ring() -> list[tuple[str, bytes]]:
    try:
        raw = json.loads(settings.ORG_API_CREDENTIAL_KEYS)
        if not isinstance(raw, list) or not raw:
            raise ValueError
        keys: list[tuple[str, bytes]] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, dict) or set(entry) != {"id", "key"}:
                raise ValueError
            key_id, encoded = entry["id"], entry["key"]
            if (
                not isinstance(key_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key_id)
                or key_id in seen
                or not isinstance(encoded, str)
            ):
                raise ValueError
            key = base64.b64decode(encoded, validate=True)
            if len(key) != 32:
                raise ValueError
            seen.add(key_id)
            keys.append((key_id, key))
        return keys
    except (AttributeError, TypeError, ValueError, binascii.Error):
        raise CredentialError("credential_keys_unavailable") from None


def _binding(*, org_id: int, connection_id: int, origin: str) -> dict[str, object]:
    if (
        type(org_id) is not int
        or type(connection_id) is not int
        or org_id < 1
        or connection_id < 1
    ):
        raise CredentialError("credential_binding_invalid")
    return {
        "org_id": org_id,
        "connection_id": connection_id,
        "origin": canonical_origin(origin),
        "credential_type": "outbound",
    }


def _json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def seal_credential(
    secret: str, *, org_id: int, connection_id: int, origin: str
) -> str:
    try:
        if (
            not isinstance(secret, str)
            or not secret
            or len(secret.encode()) > CREDENTIAL_BYTES
            or any(ord(c) < 32 or ord(c) == 127 for c in secret)
        ):
            raise ValueError
    except (ValueError, UnicodeError):
        raise CredentialError("credential_invalid") from None
    key_id, key = credential_key_ring()[0]
    binding = _binding(org_id=org_id, connection_id=connection_id, origin=origin)
    nonce = secrets.token_bytes(12)
    aad = _json({"v": 1, "kid": key_id, **binding})
    encrypted = AESGCM(key).encrypt(nonce, _json({**binding, "secret": secret}), aad)
    return _json(
        {
            "v": 1,
            "kid": key_id,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(encrypted).decode(),
        }
    ).decode()


def open_credential(
    envelope: str, *, org_id: int, connection_id: int, origin: str
) -> str:
    keys = dict(credential_key_ring())
    binding = _binding(org_id=org_id, connection_id=connection_id, origin=origin)
    try:
        if not isinstance(envelope, str) or len(envelope) > 32 * 1024:
            raise ValueError
        raw = json.loads(envelope)
        if (
            not isinstance(raw, dict)
            or set(raw) != {"v", "kid", "nonce", "ciphertext"}
            or type(raw["v"]) is not int
            or raw["v"] != 1
            or not isinstance(raw["kid"], str)
        ):
            raise ValueError
        if raw["kid"] not in keys:
            raise CredentialError("credential_key_unavailable")
        nonce = base64.b64decode(raw["nonce"], validate=True)
        encrypted = base64.b64decode(raw["ciphertext"], validate=True)
        if len(nonce) != 12:
            raise ValueError
        aad = _json({"v": 1, "kid": raw["kid"], **binding})
        payload = json.loads(AESGCM(keys[raw["kid"]]).decrypt(nonce, encrypted, aad))
        if (
            not isinstance(payload, dict)
            or set(payload) != {*binding, "secret"}
            or any(payload[k] != v for k, v in binding.items())
            or not isinstance(payload["secret"], str)
            or not payload["secret"]
        ):
            raise ValueError
        return payload["secret"]
    except CredentialError:
        raise
    except (ValueError, TypeError, KeyError, InvalidTag, binascii.Error, UnicodeError):
        raise CredentialError("credential_invalid") from None
