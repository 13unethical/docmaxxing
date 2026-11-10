"""Fetch a user-supplied URL without letting it reach internal hosts (SSRF guard).

Every hop is checked before any connection: http/https only, no userinfo, a normalized DNS
name or canonical IP literal, an allowed port, and every address the name resolves to must be
public (no loopback, private, link-local, CGNAT, metadata, multicast, reserved or IPv4-mapped
ranges). The connection then goes to the validated IP itself, while TLS still verifies the
certificate and SNI against the original hostname, so a second DNS answer (rebinding) is never
used. Redirects are followed manually with the same checks per hop, and only harmless headers
survive a redirect. Time, body size and decompressed size are bounded.

``_resolve`` and ``_transport`` are the only places that touch DNS and sockets.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import zlib
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
CONNECT_TIMEOUT_S = 5.0
READ_TIMEOUT_S = 10.0
TOTAL_TIMEOUT_S = 20.0
_CHUNK = 16 * 1024
_MAX_URL_LEN = 2048

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SAFE_REDIRECT_HEADERS = frozenset({"user-agent", "accept", "accept-language"})

_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home.arpa",
    ".corp",
)
_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*\.?$")
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_FORBIDDEN_URL_CHARS = re.compile(r"[\s\\\x00-\x1f\x7f]")


class UnsafeUrlError(ValueError):
    """The URL or one of its redirects points somewhere the server must not connect to."""

    def __init__(self, message: str = "This address cannot be used. Enter a public web page URL.") -> None:
        super().__init__(message)


class FetchError(requests.RequestException):
    """The public page could not be retrieved (network, status, size, type or time limit)."""

    def __init__(self, message: str = "Could not retrieve this page.") -> None:
        super().__init__(message)


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    path: str
    url: str

    @property
    def host_header(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.scheme == "https" else 80
        return host if self.port == default else f"{host}:{self.port}"


def is_forbidden_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    try:
        ip = ipaddress.ip_address(value if not isinstance(value, str) else value.split("%", 1)[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo):
        return True
    if any(ip.version == net.version and ip in net for net in _BLOCKED_NETWORKS):
        return True
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _normalize_host(raw: str | None) -> str:
    host = (raw or "").strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if not host:
        raise UnsafeUrlError()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if is_forbidden_ip(literal):
            raise UnsafeUrlError()
        return str(literal)
    if _NUMERIC_HOST.match(host) or ":" in host:
        raise UnsafeUrlError()
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise UnsafeUrlError() from None
    if _NUMERIC_HOST.match(ascii_host):
        raise UnsafeUrlError()
    labels = ascii_host.split(".")
    if len(labels) < 2 or len(ascii_host) > 253 or not all(_LABEL.match(label) for label in labels):
        raise UnsafeUrlError()
    if ascii_host == "localhost" or ascii_host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise UnsafeUrlError()
    return ascii_host


def parse_target(url: str) -> _Target:
    """Static checks of one URL (no DNS)."""
    if not isinstance(url, str) or not url or len(url) > _MAX_URL_LEN or _FORBIDDEN_URL_CHARS.search(url):
        raise UnsafeUrlError()
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UnsafeUrlError() from None
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only http:// and https:// URLs are supported.")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise UnsafeUrlError()
    host = _normalize_host(parts.hostname)
    if port is None:
        port = 443 if scheme == "https" else 80
    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError()
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    shown_host = f"[{host}]" if ":" in host else host
    netloc = shown_host if port == (443 if scheme == "https" else 80) else f"{shown_host}:{port}"
    return _Target(scheme=scheme, host=host, port=port, path=path, url=urlunsplit((scheme, netloc, parts.path or "/", parts.query, "")))


def _resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def resolve_public_ip(target: _Target) -> str:
    """One validated address for the target; any forbidden answer rejects the whole name."""
    try:
        literal = ipaddress.ip_address(target.host)
    except ValueError:
        literal = None
    if literal is not None:
        if is_forbidden_ip(literal):
            raise UnsafeUrlError()
        return str(literal)
    try:
        addresses = _resolve(target.host, target.port)
    except (OSError, UnicodeError):
        raise FetchError() from None
    if not addresses:
        raise FetchError()
    for address in addresses:
        if is_forbidden_ip(address):
            raise UnsafeUrlError()
    return addresses[0].split("%", 1)[0]


def _transport(*, target: _Target, ip: str, headers: dict[str, str], timeout: Any) -> Any:
    """Open ``target`` on the already validated ``ip``; TLS verifies ``target.host``."""
    import certifi
    import urllib3

    if target.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            ip,
            port=target.port,
            timeout=timeout,
            retries=False,
            maxsize=1,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
            server_hostname=target.host,
            assert_hostname=target.host,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port=target.port, timeout=timeout, retries=False, maxsize=1)
    try:
        response = pool.urlopen(
            "GET",
            target.path,
            headers=headers,
            redirect=False,
            retries=False,
            preload_content=False,
            decode_content=False,
            assert_same_host=False,
        )
    except BaseException:
        pool.close()
        raise
    response.safe_fetch_pool = pool
    return response


def _header(response: Any, name: str) -> str:
    headers = getattr(response, "headers", None) or {}
    value = headers.get(name)
    if value is None and hasattr(headers, "items"):
        lowered = name.lower()
        for key, item in headers.items():
            if str(key).lower() == lowered:
                value = item
                break
    return str(value or "").strip()


def _close(response: Any) -> None:
    for owner, name in ((response, "close"), (getattr(response, "safe_fetch_pool", None), "close")):
        method = getattr(owner, name, None) if owner is not None else None
        if callable(method):
            try:
                method()
            except Exception:  # noqa: BLE001
                pass


def _decoder(encoding: str) -> Any:
    encoding = encoding.lower()
    if encoding in ("", "identity"):
        return None
    if encoding in ("gzip", "x-gzip"):
        return zlib.decompressobj(16 + zlib.MAX_WBITS)
    if encoding == "deflate":
        return zlib.decompressobj()
    raise FetchError()


def _read_body(response: Any, *, max_bytes: int, deadline: float) -> bytes:
    declared = _header(response, "Content-Length")
    if declared.isdigit() and int(declared) > max_bytes:
        raise FetchError()
    decoder = _decoder(_header(response, "Content-Encoding"))
    out = bytearray()
    raw_total = 0
    try:
        while True:
            if time.monotonic() > deadline:
                raise FetchError()
            chunk = response.read(_CHUNK, decode_content=False)
            if not chunk:
                break
            raw_total += len(chunk)
            if raw_total > max_bytes:
                raise FetchError()
            if decoder is None:
                out += chunk
            else:
                out += decoder.decompress(chunk, max_bytes + 1 - len(out))
                if decoder.unconsumed_tail:
                    raise FetchError()
            if len(out) > max_bytes:
                raise FetchError()
        if decoder is not None:
            out += decoder.flush()
            if len(out) > max_bytes:
                raise FetchError()
    except FetchError:
        raise
    except zlib.error:
        raise FetchError() from None
    except Exception:  # noqa: BLE001
        raise FetchError() from None
    return bytes(out)


def _content_type_allowed(content_type: str, allowed: Iterable[str] | None) -> bool:
    if allowed is None:
        return True
    for option in allowed:
        option = option.lower()
        if option.endswith("/") and content_type.startswith(option):
            return True
        if content_type == option:
            return True
    return False


def fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    allowed_content_types: Iterable[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    connect_timeout: float = CONNECT_TIMEOUT_S,
    read_timeout: float = READ_TIMEOUT_S,
    total_timeout: float = TOTAL_TIMEOUT_S,
) -> FetchResult:
    """GET a public URL. Raises ``UnsafeUrlError`` (destination refused) or ``FetchError``."""
    import urllib3

    allowed = tuple(allowed_content_types) if allowed_content_types is not None else None
    request_headers = {str(k): str(v) for k, v in (headers or {}).items()}
    request_headers["Accept-Encoding"] = "gzip, deflate"
    deadline = time.monotonic() + total_timeout
    timeout = urllib3.Timeout(connect=connect_timeout, read=read_timeout)
    current = url
    for hop in range(max_redirects + 1):
        target = parse_target(current)
        ip = resolve_public_ip(target)
        if time.monotonic() > deadline:
            raise FetchError()
        hop_headers = dict(request_headers)
        if hop:
            hop_headers = {
                k: v for k, v in hop_headers.items() if k.lower() in _SAFE_REDIRECT_HEADERS or k == "Accept-Encoding"
            }
        hop_headers["Host"] = target.host_header
        try:
            response = _transport(target=target, ip=ip, headers=hop_headers, timeout=timeout)
        except (UnsafeUrlError, FetchError):
            raise
        except Exception:  # noqa: BLE001
            raise FetchError() from None
        try:
            status = int(getattr(response, "status", 0) or 0)
            if status in _REDIRECT_STATUSES:
                location = _header(response, "Location")
                if not location:
                    raise FetchError()
                current = urljoin(target.url, location)
                continue
            if not 200 <= status < 300:
                raise FetchError()
            content_type = _header(response, "Content-Type").split(";", 1)[0].strip().lower()
            if not _content_type_allowed(content_type, allowed):
                raise FetchError()
            body = _read_body(response, max_bytes=max_bytes, deadline=deadline)
            return FetchResult(
                url=target.url,
                status=status,
                content_type=content_type,
                content=body,
                headers={str(k).lower(): str(v) for k, v in (getattr(response, "headers", None) or {}).items()},
            )
        finally:
            _close(response)
    raise FetchError()
