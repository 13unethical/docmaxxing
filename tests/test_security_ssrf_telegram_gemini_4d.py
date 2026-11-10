"""Patch 4D: SSRF in URL fetching, Telegram support-reply integrity, secrets in logs/diagnostics.

Remediation plan items: F-05 (anonymous ``POST /api/reference`` fetched any URL, redirects
followed), F-06 (Telegram replies routed by chat-agnostic message ids and a ``User ID:`` text
footer, no sender / chat / update checks), F-12 (webhook secret accepted in ``?secret=``),
F-09 (Gemini key in the ``?key=`` query, echoed by ``repr(exc)`` into logs and diagnostics) and
the Telegram bot token in tracebacks.

Nothing leaves the machine: DNS is a fake resolver, HTTP is a fake transport or a local server
reached through a pinned 127.0.0.1, socket traps record any connection attempt, and Telegram /
Gemini calls are mocked. Concurrent workers are forked processes on one SQLite database.
"""

from __future__ import annotations

import gzip
import http.server
import json
import logging
import socket
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from services import safe_fetch
from services.economy import db as economy_db
from services.secret_redaction import describe_exception, install_log_redaction, redact
from tests.test_security_account_protection_4c import _run_workers
from tests.test_security_paid_pipelines import _client, _signed_in, _user, economy  # noqa: F401

PUBLIC_IP = "93.184.216.34"
PUBLIC_IP_2 = "151.101.1.69"
TG_BOT_ID = 123456
TG_TOKEN = f"{TG_BOT_ID}:TGSENTINELtoken_abcdefghijklmnopqrstuvwxyz0123"
TG_WEBHOOK_SECRET = "whsecSENTINEL_0123456789abcdef"
GROUP_CHAT = -1001234567890
ADMIN_ID = 4242
SECOND_ADMIN_ID = 5151
GEMINI_KEY = "AIzaSySENTINELgeminiKey_0123456789abcdefXYZ"
ODD_GEMINI_KEY = "gmk~live~SENTINEL~odd-format-9f8e7d6c5b4a"

_ENV_KNOBS = (
    "TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN", "CHAT_ID", "TELEGRAM_CHAT_ID", "TELEGRAM_ADMIN_USER_IDS",
    "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_POLLING", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_MODEL",
    "GEMINI_TIMEOUT_S", "REFERENCE_LOOKUPS_PER_MINUTE", "REFERENCE_LOOKUPS_PER_HOUR",
    "CONTACT_LIMIT_PER_IP_HOUR", "CONTACT_LIMIT_PER_IP_DAY", "TRUSTED_PROXIES", "INTERNAL_TOOLS_ENABLED",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_KNOBS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def raw_logging():
    """Default log records: module code must sanitize on its own, without the global filter."""
    previous = logging.getLogRecordFactory()
    logging.setLogRecordFactory(logging.LogRecord)
    yield
    logging.setLogRecordFactory(previous)


def _log_text(caplog) -> str:
    fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(fmt.format(record) for record in caplog.records)


def _no_write_lock_held():
    """A second connection can take the write lock at once: no transaction spans network I/O."""
    conn = sqlite3.connect(str(economy_db.DB_PATH), timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------- SSRF


@pytest.fixture()
def socket_trap(monkeypatch):
    """Any socket connect or DNS lookup is recorded and refused."""
    attempts: list[tuple[str, object]] = []

    def _refuse(kind):
        def _call(*args, **_kwargs):
            attempts.append((kind, args[1:2] if kind == "connect" else args[:1]))
            raise OSError(f"socket trap: {kind} refused")

        return _call

    monkeypatch.setattr(socket.socket, "connect", _refuse("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse("connect"))
    monkeypatch.setattr(socket, "create_connection", _refuse("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _refuse("getaddrinfo"))
    return attempts


@pytest.fixture()
def fake_dns(monkeypatch):
    """``answers[host]`` is a list of IPs, or a callable returning one per lookup."""
    state = SimpleNamespace(answers={}, lookups=[])

    def _resolve(host, port):
        state.lookups.append(host)
        answer = state.answers.get(host)
        if answer is None:
            raise socket.gaierror("fake dns: no such host")
        return list(answer() if callable(answer) else answer)

    monkeypatch.setattr(safe_fetch, "_resolve", _resolve)
    return state


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"", chunk=4096, delay=0.0):
        self.status = status
        self.headers = dict(headers or {})
        self._body = body
        self._pos = 0
        self._chunk = chunk
        self._delay = delay
        self.closed = False

    def read(self, amt=None, decode_content=None):
        if self._delay:
            time.sleep(self._delay)
        if self._pos >= len(self._body):
            return b""
        size = min(amt or len(self._body), self._chunk)
        piece = self._body[self._pos : self._pos + size]
        self._pos += len(piece)
        return piece

    def close(self):
        self.closed = True


def _html(title="Public Page", extra=""):
    return f"<html><head><title>{title}</title>{extra}</head><body>ok</body></html>".encode()


@pytest.fixture()
def fake_http(monkeypatch):
    """``routes[(host, path)]`` → FakeResponse (or callable); records every pinned connection."""
    state = SimpleNamespace(routes={}, calls=[])

    def _transport(*, target, ip, headers, timeout):
        state.calls.append({"host": target.host, "ip": ip, "path": target.path, "headers": dict(headers)})
        route = state.routes.get((target.host, target.path))
        if route is None:
            return FakeResponse(404, {"Content-Type": "text/html"}, b"missing")
        return route() if callable(route) else route

    monkeypatch.setattr(safe_fetch, "_transport", _transport)
    return state


def _expect_unsafe(url, socket_trap, **kwargs):
    with pytest.raises(safe_fetch.UnsafeUrlError):
        safe_fetch.fetch(url, **kwargs)
    assert socket_trap == [], f"a connection was attempted for {url}"


# 1
def test_ssrf_01_loopback_ipv4_is_refused_without_connecting(socket_trap):
    for url in ("http://127.0.0.1/", "https://127.0.0.1/admin", "http://127.0.0.1:8080/", "http://127.255.255.254/"):
        _expect_unsafe(url, socket_trap)


# 2
def test_ssrf_02_localhost_names_are_refused_without_dns(socket_trap, fake_dns):
    for url in ("http://localhost/", "http://LOCALHOST./x", "http://app.localhost/", "http://printer.local/",
                "http://db.internal/", "http://intranet/"):
        _expect_unsafe(url, socket_trap)
    assert fake_dns.lookups == []


# 3
def test_ssrf_03_ipv6_loopback_is_refused(socket_trap):
    for url in ("http://[::1]/", "http://[0:0:0:0:0:0:0:1]/", "https://[::1]:8443/"):
        _expect_unsafe(url, socket_trap)


# 4
def test_ssrf_04_private_ranges_are_refused(socket_trap):
    for url in ("http://10.0.0.5/", "http://172.16.0.1/", "http://172.31.255.255/", "http://192.168.1.1/",
                "http://[fd12:3456::1]/", "http://[fc00::1]/"):
        _expect_unsafe(url, socket_trap)


# 5
def test_ssrf_05_link_local_is_refused(socket_trap):
    for url in ("http://169.254.10.10/", "http://[fe80::1]/", "http://[fe80::1%25eth0]/"):
        _expect_unsafe(url, socket_trap)


# 6
def test_ssrf_06_cloud_metadata_addresses_are_refused(socket_trap, fake_dns):
    for url in ("http://169.254.169.254/latest/meta-data/", "http://metadata.google.internal/computeMetadata/v1/",
                "http://[fd00:ec2::254]/", "http://100.100.100.200/", "http://192.0.0.192/"):
        _expect_unsafe(url, socket_trap)
    assert fake_dns.lookups == []


# 7
def test_ssrf_07_ipv4_mapped_and_embedded_ipv6_are_refused(socket_trap):
    for url in ("http://[::ffff:127.0.0.1]/", "http://[::ffff:a9fe:a9fe]/", "http://[::ffff:10.0.0.1]/",
                "http://[2002:7f00:1::1]/", "http://[64:ff9b::7f00:1]/", "http://[2001:0:4136:e378::1]/"):
        _expect_unsafe(url, socket_trap)


# 8
def test_ssrf_08_reserved_unspecified_cgnat_and_multicast_are_refused(socket_trap):
    for url in ("http://0.0.0.0/", "http://[::]/", "http://240.0.0.1/", "http://255.255.255.255/",
                "http://100.64.0.1/", "http://198.18.0.1/", "http://224.0.0.1/", "http://192.0.2.10/",
                "http://[ff02::1]/"):
        _expect_unsafe(url, socket_trap)


# 9
def test_ssrf_09_public_name_resolving_to_private_ip_is_refused(socket_trap, fake_dns, fake_http):
    fake_dns.answers["evil.example.com"] = ["10.0.0.7"]
    fake_dns.answers["evil6.example.com"] = ["::1"]
    fake_dns.answers["meta.example.com"] = ["169.254.169.254"]
    for url in ("http://evil.example.com/", "https://evil6.example.com/", "http://meta.example.com/latest"):
        _expect_unsafe(url, socket_trap)
    assert fake_http.calls == []


# 10
def test_ssrf_10_mixed_dns_answer_with_any_private_ip_is_refused(socket_trap, fake_dns, fake_http):
    fake_dns.answers["mixed.example.com"] = [PUBLIC_IP, "127.0.0.1"]
    fake_dns.answers["mixed6.example.com"] = ["2606:2800:220:1:248:1893:25c8:1946", "fe80::1"]
    _expect_unsafe("http://mixed.example.com/", socket_trap)
    _expect_unsafe("http://mixed6.example.com/", socket_trap)
    assert fake_http.calls == []


# 11
def test_ssrf_11_dns_rebinding_cannot_swap_the_connected_address(fake_dns, fake_http):
    answers = iter([[PUBLIC_IP], ["127.0.0.1"], ["127.0.0.1"]])
    fake_dns.answers["rebind.example.com"] = lambda: next(answers)
    fake_http.routes[("rebind.example.com", "/")] = FakeResponse(200, {"Content-Type": "text/html"}, _html())
    result = safe_fetch.fetch("http://rebind.example.com/", allowed_content_types=("text/html",))
    assert result.status == 200
    assert fake_dns.lookups == ["rebind.example.com"]
    assert [c["ip"] for c in fake_http.calls] == [PUBLIC_IP]
    assert fake_http.calls[0]["headers"]["Host"] == "rebind.example.com"


def test_ssrf_11b_transport_connects_to_the_pinned_ip_and_verifies_tls_for_the_hostname(monkeypatch):
    import urllib3

    built = []

    class _Pool:
        def __init__(self, host, **kwargs):
            built.append((host, kwargs))

        def urlopen(self, method, url, **kwargs):
            built.append(("urlopen", method, url, kwargs))
            return FakeResponse(200, {"Content-Type": "text/html"}, b"<html></html>")

        def close(self):
            built.append(("closed",))

    monkeypatch.setattr(urllib3, "HTTPSConnectionPool", _Pool)
    monkeypatch.setattr(urllib3, "HTTPConnectionPool", _Pool)
    target = safe_fetch.parse_target("https://news.example.org/a?b=1")
    response = safe_fetch._transport(target=target, ip=PUBLIC_IP, headers={"Host": "news.example.org"}, timeout=None)
    host, kwargs = built[0]
    assert host == PUBLIC_IP
    assert kwargs["server_hostname"] == "news.example.org"
    assert kwargs["assert_hostname"] == "news.example.org"
    assert kwargs["cert_reqs"] == "CERT_REQUIRED"
    _, method, url, call = built[1]
    assert (method, url) == ("GET", "/a?b=1")
    assert call["redirect"] is False and call["retries"] is False
    safe_fetch._close(response)
    assert ("closed",) in built


# 12
def test_ssrf_12_redirect_to_private_ip_is_refused(fake_dns, fake_http, socket_trap):
    fake_dns.answers["start.example.com"] = [PUBLIC_IP]
    fake_dns.answers["10.0.0.1"] = ["10.0.0.1"]
    fake_http.routes[("start.example.com", "/")] = FakeResponse(302, {"Location": "http://10.0.0.1/internal"})
    _expect_unsafe("http://start.example.com/", socket_trap)
    assert [c["host"] for c in fake_http.calls] == ["start.example.com"]


# 13
def test_ssrf_13_redirect_to_localhost_is_refused(fake_dns, fake_http, socket_trap):
    fake_dns.answers["start.example.com"] = [PUBLIC_IP]
    fake_dns.answers["internal.example.com"] = ["127.0.0.1"]
    fake_http.routes[("start.example.com", "/a")] = FakeResponse(301, {"Location": "http://localhost:8000/admin"})
    fake_http.routes[("start.example.com", "/b")] = FakeResponse(307, {"Location": "//internal.example.com/x"})
    fake_http.routes[("start.example.com", "/c")] = FakeResponse(302, {"Location": "http://[::1]/"})
    for path in ("/a", "/b", "/c"):
        _expect_unsafe(f"http://start.example.com{path}", socket_trap)
    assert {c["host"] for c in fake_http.calls} == {"start.example.com"}


# 14
def test_ssrf_14_redirect_to_metadata_is_refused(fake_dns, fake_http, socket_trap):
    fake_dns.answers["start.example.com"] = [PUBLIC_IP]
    fake_dns.answers["169.254.169.254"] = ["169.254.169.254"]
    fake_http.routes[("start.example.com", "/")] = FakeResponse(
        308, {"Location": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}
    )
    _expect_unsafe("http://start.example.com/", socket_trap)
    assert len(fake_http.calls) == 1


# 15
def test_ssrf_15_credentials_in_url_are_refused(socket_trap, fake_dns):
    for url in ("http://user:pass@example.com/", "http://user@example.com/", "http://example.com@127.0.0.1/",
                "http://evil.com\\@127.0.0.1/", "http://:@example.com/"):
        _expect_unsafe(url, socket_trap)
    assert fake_dns.lookups == []


# 16
def test_ssrf_16_non_http_schemes_are_refused(socket_trap):
    for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://127.0.0.1:6379/_INFO", "dict://127.0.0.1:11211/",
                "javascript:alert(1)", "data:text/html,hi", "ldap://example.com/", "jar:http://example.com/!/"):
        _expect_unsafe(url, socket_trap)


# 17
def test_ssrf_17_alternate_numeric_ip_formats_are_refused(socket_trap, fake_dns):
    for url in ("http://2130706433/", "http://0x7f000001/", "http://0177.0.0.1/", "http://127.1/",
                "http://0x7f.0.0.1/", "http://127.000.000.001/", "http://0/", "http://017700000001/",
                "http://\u2460\u2461\u2466.0.0.1/", "http://169.254.169.254./", "http://3232235777/"):
        _expect_unsafe(url, socket_trap)
    assert fake_dns.lookups == []


def test_ssrf_17b_unusual_ports_and_malformed_urls_are_refused(socket_trap):
    for url in ("http://example.com:22/", "http://example.com:6379/", "http://example.com:99999/",
                "http://exa mple.com/", "http://example.com/\nHost: x", "", "http:///nohost"):
        _expect_unsafe(url, socket_trap)


# 18
def test_ssrf_18_excessive_redirects_stop(fake_dns, fake_http):
    fake_dns.answers["loop.example.com"] = [PUBLIC_IP]
    for i in range(10):
        fake_http.routes[("loop.example.com", f"/{i}")] = FakeResponse(302, {"Location": f"/{i + 1}"})
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch("http://loop.example.com/0", max_redirects=3)
    assert len(fake_http.calls) == 4


# 19
def test_ssrf_19_oversized_bodies_are_refused(fake_dns, fake_http):
    fake_dns.answers["big.example.com"] = [PUBLIC_IP]
    fake_http.routes[("big.example.com", "/declared")] = FakeResponse(
        200, {"Content-Type": "text/html", "Content-Length": str(50 * 1024 * 1024)}, b"x"
    )
    fake_http.routes[("big.example.com", "/streamed")] = lambda: FakeResponse(
        200, {"Content-Type": "text/html"}, b"x" * (3 * 1024 * 1024), chunk=64 * 1024
    )
    for path in ("/declared", "/streamed"):
        with pytest.raises(safe_fetch.FetchError):
            safe_fetch.fetch(f"http://big.example.com{path}", max_bytes=1024 * 1024)


# 20
def test_ssrf_20_slow_response_hits_the_total_deadline(fake_dns, fake_http):
    fake_dns.answers["slow.example.com"] = [PUBLIC_IP]
    fake_http.routes[("slow.example.com", "/")] = FakeResponse(
        200, {"Content-Type": "text/html"}, b"x" * 100, chunk=1, delay=0.05
    )
    started = time.monotonic()
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch("http://slow.example.com/", total_timeout=0.5)
    assert time.monotonic() - started < 3


# 21
def test_ssrf_21_decompression_bomb_is_refused(fake_dns, fake_http):
    fake_dns.answers["bomb.example.com"] = [PUBLIC_IP]
    bomb = gzip.compress(b"\0" * (40 * 1024 * 1024))
    assert len(bomb) < 200 * 1024
    fake_http.routes[("bomb.example.com", "/")] = FakeResponse(
        200, {"Content-Type": "text/html", "Content-Encoding": "gzip"}, bomb, chunk=16 * 1024
    )
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch("http://bomb.example.com/", max_bytes=1024 * 1024)


def test_ssrf_21b_unknown_content_encoding_and_type_are_refused(fake_dns, fake_http):
    fake_dns.answers["enc.example.com"] = [PUBLIC_IP]
    fake_http.routes[("enc.example.com", "/br")] = FakeResponse(200, {"Content-Type": "text/html", "Content-Encoding": "br"}, b"x")
    fake_http.routes[("enc.example.com", "/bin")] = FakeResponse(200, {"Content-Type": "application/octet-stream"}, b"x")
    fake_http.routes[("enc.example.com", "/err")] = FakeResponse(500, {"Content-Type": "text/html"}, b"x")
    for path in ("/br", "/bin", "/err"):
        with pytest.raises(safe_fetch.FetchError):
            safe_fetch.fetch(f"http://enc.example.com{path}", allowed_content_types=("text/html",))


# 22
def test_ssrf_22_redirects_do_not_carry_credentials_cookies_or_internal_headers(fake_dns, fake_http):
    fake_dns.answers["a.example.com"] = [PUBLIC_IP]
    fake_dns.answers["b.example.net"] = [PUBLIC_IP_2]
    fake_http.routes[("a.example.com", "/")] = FakeResponse(
        302, {"Location": "https://b.example.net/harvest", "Set-Cookie": "sid=from-a; Path=/"}
    )
    fake_http.routes[("b.example.net", "/harvest")] = FakeResponse(200, {"Content-Type": "text/html"}, _html())
    sent = {
        "User-Agent": "UA/1", "Accept": "text/html", "Authorization": "Bearer internal-secret-token",
        "Cookie": "session=abc", "Proxy-Authorization": "Basic xyz", "X-Internal-Token": "tok",
        "X-Goog-Api-Key": GEMINI_KEY,
    }
    result = safe_fetch.fetch("http://a.example.com/", headers=sent, allowed_content_types=("text/html",))
    assert result.url == "https://b.example.net/harvest"
    second = fake_http.calls[1]["headers"]
    assert set(second) == {"User-Agent", "Accept", "Accept-Encoding", "Host"}
    assert second["Host"] == "b.example.net"
    assert "sid" not in json.dumps(second)


def test_ssrf_legitimate_public_fetch_follows_safe_redirects_and_decodes_gzip(fake_dns, fake_http):
    fake_dns.answers["example.org"] = [PUBLIC_IP]
    fake_dns.answers["www.example.org"] = [PUBLIC_IP_2, "2606:2800:220:1:248:1893:25c8:1946"]
    fake_http.routes[("example.org", "/article")] = FakeResponse(301, {"Location": "https://www.example.org/article"})
    fake_http.routes[("www.example.org", "/article")] = FakeResponse(
        200, {"Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip"}, gzip.compress(_html("Hello"))
    )
    result = safe_fetch.fetch("http://example.org/article", allowed_content_types=("text/html",))
    assert result.url == "https://www.example.org/article"
    assert b"<title>Hello</title>" in result.content
    assert [c["ip"] for c in fake_http.calls] == [PUBLIC_IP, PUBLIC_IP_2]


class _LocalSite(http.server.BaseHTTPRequestHandler):
    hosts: list[str] = []
    bomb = gzip.compress(b"\0" * (20 * 1024 * 1024))

    def log_message(self, *args):
        pass

    def _head(self, status=200, ctype="text/html", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        type(self).hosts.append(self.headers.get("Host"))
        if self.path == "/page":
            self._head(extra={"Content-Encoding": "gzip"})
            self.wfile.write(gzip.compress(_html("Local Page")))
        elif self.path == "/bomb":
            self._head(extra={"Content-Encoding": "gzip"})
            self.wfile.write(self.bomb)
        elif self.path == "/big":
            self._head()
            for _ in range(48):
                self.wfile.write(b"y" * 65536)
        elif self.path == "/stall":
            self._head()
            self.wfile.flush()
            time.sleep(3)
        elif self.path == "/trickle":
            self._head()
            for _ in range(50):
                self.wfile.write(b"z")
                self.wfile.flush()
                time.sleep(0.1)
        elif self.path == "/to-private":
            self._head(302, extra={"Location": "http://10.1.2.3/"})
        else:
            self._head(404)


@pytest.fixture()
def local_site(monkeypatch):
    """A real HTTP server reached only through the pinned address of ``public.example``.

    Loopback is let through for this one address so the real urllib3 transport is exercised;
    every other check stays in force.
    """
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LocalSite)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _LocalSite.hosts = []
    real_forbidden = safe_fetch.is_forbidden_ip
    lookups: list[str] = []
    answers = {"public.example": ["127.0.0.1"]}

    def _resolve(host, _port):
        lookups.append(host)
        if host not in answers:
            raise socket.gaierror("no such host")
        return answers[host]

    monkeypatch.setattr(safe_fetch, "ALLOWED_PORTS", frozenset({port}))
    monkeypatch.setattr(safe_fetch, "is_forbidden_ip", lambda ip: str(ip) != "127.0.0.1" and real_forbidden(ip))
    monkeypatch.setattr(safe_fetch, "_resolve", _resolve)
    yield SimpleNamespace(base=f"http://public.example:{port}", port=port, lookups=lookups, answers=answers)
    server.shutdown()
    server.server_close()


def test_ssrf_real_transport_pins_ip_sends_hostname_and_decodes(local_site):
    result = safe_fetch.fetch(f"{local_site.base}/page", allowed_content_types=("text/html",))
    assert b"Local Page" in result.content
    assert _LocalSite.hosts == [f"public.example:{local_site.port}"]
    assert local_site.lookups == ["public.example"]


def test_ssrf_real_transport_never_re_resolves_after_validation(local_site, monkeypatch):
    calls = iter([["127.0.0.1"]])

    def _once(host, _port):
        local_site.lookups.append(host)
        return next(calls)

    monkeypatch.setattr(safe_fetch, "_resolve", _once)
    result = safe_fetch.fetch(f"{local_site.base}/page", allowed_content_types=("text/html",))
    assert result.status == 200
    assert local_site.lookups == ["public.example"]


def test_ssrf_real_transport_limits_size_bomb_stall_and_trickle(local_site):
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch(f"{local_site.base}/big", max_bytes=1024 * 1024)
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch(f"{local_site.base}/bomb", max_bytes=1024 * 1024)
    started = time.monotonic()
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch(f"{local_site.base}/stall", read_timeout=0.5)
    with pytest.raises(safe_fetch.FetchError):
        safe_fetch.fetch(f"{local_site.base}/trickle", read_timeout=2, total_timeout=1.0)
    assert time.monotonic() - started < 6


def test_ssrf_real_transport_redirect_to_private_is_refused(local_site):
    with pytest.raises(safe_fetch.UnsafeUrlError):
        safe_fetch.fetch(f"{local_site.base}/to-private")
    assert len(_LocalSite.hosts) == 1


def test_reference_route_refuses_internal_targets_with_a_generic_error(economy, socket_trap, fake_dns, fake_http):
    client = _client()
    fake_dns.answers["rebound.example.com"] = ["127.0.0.1"]
    fake_dns.answers["hop.example.com"] = [PUBLIC_IP]
    fake_http.routes[("hop.example.com", "/")] = FakeResponse(302, {"Location": "http://127.0.0.1:8000/"})
    for url in ("http://127.0.0.1/", "169.254.169.254/latest/meta-data/", "http://[::1]/", "http://localhost:9222/json",
                "http://rebound.example.com/", "file:///etc/passwd", "http://hop.example.com/"):
        res = client.post("/api/reference", json={"mode": "url", "url": url})
        assert res.status_code == 400, (url, res.get_data(as_text=True))
        body = res.get_data(as_text=True)
        assert "127.0.0.1" not in body and "169.254" not in body and "Traceback" not in body
    assert socket_trap == []
    assert [c["host"] for c in fake_http.calls] == ["hop.example.com"]


def test_reference_route_legitimate_url_and_rate_limit(economy, fake_dns, fake_http, monkeypatch):
    monkeypatch.setenv("REFERENCE_LOOKUPS_PER_MINUTE", "2")
    fake_dns.answers["news.example.org"] = [PUBLIC_IP]

    def _page():
        _no_write_lock_held()
        return FakeResponse(200, {"Content-Type": "text/html"}, _html(
            "Climate Report", '<meta property="og:site_name" content="UN News" />'
            '<meta property="article:published_time" content="2021-09-01" />'))

    fake_http.routes[("news.example.org", "/story/1")] = _page
    client = _client()
    first = client.post("/api/reference", json={"mode": "url", "url": "https://news.example.org/story/1", "style": "APA"})
    assert first.status_code == 200, first.get_data(as_text=True)
    assert "Climate Report" in first.get_json()["citation"]
    assert client.post("/api/reference", json={"mode": "url", "url": "https://news.example.org/story/1"}).status_code == 200
    limited = _client().post("/api/reference", json={"mode": "url", "url": "https://news.example.org/story/1"})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    manual = client.post("/api/reference", json={"mode": "manual", "manual": {"title": "Local only", "authors": "A, B"}})
    assert manual.status_code == 200


def test_citation_engine_and_formatter_v2_url_helpers_share_the_guard(socket_trap, fake_dns):
    from formatter_v2.citations.sources import from_url
    from services.citation_engine import generate_citation

    with pytest.raises(ValueError):
        generate_citation(mode="url", url="http://169.254.169.254/latest/meta-data/")
    item, err = from_url("http://127.0.0.1:8000/")
    assert item is None and err == "This address cannot be used"
    fake_dns.answers["inside.example.com"] = ["192.168.0.10"]
    item, err = from_url("inside.example.com/page")
    assert item is None and err == "This address cannot be used"
    assert socket_trap == []


def test_provider_image_urls_are_checked_before_download(tmp_path):
    from unittest.mock import MagicMock

    from services import assignment_figures, presentation_images

    http = MagicMock()
    for url in ("http://127.0.0.1/a.png", "http://169.254.169.254/x.jpg", "file:///etc/passwd"):
        with pytest.raises(safe_fetch.UnsafeUrlError):
            presentation_images._store(url, http)
        with pytest.raises(safe_fetch.UnsafeUrlError):
            assignment_figures.download_image(url, tmp_path / "x.png", session=http)
    assert http.get.call_count == 0


# ------------------------------------------------------------------------------------ Telegram


@pytest.fixture()
def tg(economy, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", TG_TOKEN)
    monkeypatch.setenv("CHAT_ID", str(GROUP_CHAT))
    monkeypatch.setenv("TELEGRAM_ADMIN_USER_IDS", f"{ADMIN_ID}, {SECOND_ADMIN_ID}")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", TG_WEBHOOK_SECRET)
    from services.economy.support_chat import bind_telegram_message

    alice = _user("alice@example.com")
    bob = _user("bob@example.com")
    bind_telegram_message(telegram_message_id=9001, user_id=alice["id"], chat_id=str(GROUP_CHAT))
    bind_telegram_message(telegram_message_id=9002, user_id=bob["id"], chat_id=str(GROUP_CHAT))
    return SimpleNamespace(alice=alice, bob=bob, client=_client())


def _tg_update(update_id, *, reply_to=9001, sender=ADMIN_ID, chat=GROUP_CHAT, text="Admin answer",
               message_id=None, reply_author=TG_BOT_ID, reply_text="Support from Alice\n\nhelp\n\nUser ID: 1", **extra):
    message = {
        "message_id": message_id or 50_000 + update_id,
        "date": 1_700_000_000,
        "from": {"id": sender, "is_bot": False, "first_name": "Operator"},
        "chat": {"id": chat, "type": "supergroup"},
        "text": text,
        "reply_to_message": {
            "message_id": reply_to,
            "from": {"id": reply_author, "is_bot": True},
            "chat": {"id": chat},
            "text": reply_text,
        },
    }
    message.update(extra)
    return {"update_id": update_id, "message": message}


def _hook(client, payload, secret=TG_WEBHOOK_SECRET, **kwargs):
    headers = {"X-Telegram-Bot-Api-Secret-Token": secret} if secret is not None else {}
    return client.post("/api/telegram-webhook", json=payload, headers=headers, **kwargs)


def _admin_messages(user_id):
    with economy_db.connect() as conn:
        rows = conn.execute(
            "SELECT message FROM support_messages WHERE user_id = ? AND sender = 'admin' ORDER BY id", (user_id,)
        ).fetchall()
    return [r["message"] for r in rows]


def _all_admin_messages():
    with economy_db.connect() as conn:
        return [tuple(r) for r in conn.execute("SELECT user_id, message FROM support_messages WHERE sender = 'admin'")]


# 1-3
def test_tg_01_02_03_webhook_secret_is_mandatory_and_header_only(tg, monkeypatch):
    update = _tg_update(1)
    assert _hook(tg.client, update, secret=None).status_code == 401
    assert _hook(tg.client, update, secret="wrong").status_code == 401
    assert _hook(tg.client, update, secret=TG_WEBHOOK_SECRET + "x").status_code == 401
    query_only = tg.client.post(f"/api/telegram-webhook?secret={TG_WEBHOOK_SECRET}", json=update)
    assert query_only.status_code == 401
    assert _all_admin_messages() == []
    ok = _hook(tg.client, update)
    assert ok.status_code == 200 and ok.get_json() == {"ok": True, "status": "saved"}
    assert _admin_messages(tg.alice["id"]) == ["Admin answer"]
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
    assert _hook(tg.client, _tg_update(2), secret="").status_code == 401


# 4
def test_tg_04_forged_sender_is_ignored(tg):
    res = _hook(tg.client, _tg_update(10, sender=777_000_111))
    assert res.status_code == 200 and res.get_json()["status"] == "ignored"
    assert _all_admin_messages() == []


# 5
def test_tg_05_forged_chat_id_is_ignored(tg):
    for i, chat in enumerate((-100999, ADMIN_ID, f"{GROUP_CHAT}x", None)):
        assert _hook(tg.client, _tg_update(20 + i, chat=chat)).get_json()["status"] == "ignored"
        only_outer = _tg_update(30 + i, chat=chat)
        only_outer["message"]["reply_to_message"]["chat"] = {"id": GROUP_CHAT}
        assert _hook(tg.client, only_outer).get_json()["status"] == "ignored"
    no_reply_chat = _tg_update(40)
    del no_reply_chat["message"]["reply_to_message"]["chat"]
    assert _hook(tg.client, no_reply_chat).get_json()["status"] == "ignored"
    assert _all_admin_messages() == []


# 6
def test_tg_06_unauthorized_group_member_cannot_reply_and_private_chat_admits_only_its_owner(tg, monkeypatch):
    assert _hook(tg.client, _tg_update(30, sender=999_999)).get_json()["status"] == "ignored"
    monkeypatch.delenv("TELEGRAM_ADMIN_USER_IDS")
    assert _hook(tg.client, _tg_update(31, sender=ADMIN_ID)).get_json()["status"] == "ignored"
    from services.economy.support_chat import bind_telegram_message

    monkeypatch.setenv("CHAT_ID", str(ADMIN_ID))
    bind_telegram_message(telegram_message_id=9100, user_id=tg.alice["id"], chat_id=str(ADMIN_ID))
    stranger = _tg_update(32, reply_to=9100, chat=ADMIN_ID, sender=SECOND_ADMIN_ID)
    assert _hook(tg.client, stranger).get_json()["status"] == "ignored"
    owner = _tg_update(33, reply_to=9100, chat=ADMIN_ID, sender=ADMIN_ID, text="Owner reply")
    assert _hook(tg.client, owner).get_json()["status"] == "saved"
    assert _admin_messages(tg.alice["id"]) == ["Owner reply"]


# 7
def test_tg_07_authorized_operators_reply_to_the_bound_user(tg):
    assert _hook(tg.client, _tg_update(40, text="From first admin")).get_json()["status"] == "saved"
    assert _hook(tg.client, _tg_update(41, sender=SECOND_ADMIN_ID, reply_to=9002, text="For Bob")).get_json()["status"] == "saved"
    assert _admin_messages(tg.alice["id"]) == ["From first admin"]
    assert _admin_messages(tg.bob["id"]) == ["For Bob"]


# 8
def test_tg_08_cross_user_targeting_through_text_is_impossible(tg):
    bob = tg.bob["id"]
    forged = _tg_update(50, reply_to=9001, text=f"User ID: {bob}", reply_text=f"hi\n\nUser ID: {bob}")
    assert _hook(tg.client, forged).get_json()["status"] == "saved"
    assert _admin_messages(bob) == []
    assert _admin_messages(tg.alice["id"]) == [f"User ID: {bob}"]
    unbound = _tg_update(51, reply_to=123_456_789, reply_text=f"Support\n\nUser ID: {bob}")
    assert _hook(tg.client, unbound).get_json()["status"] == "ignored"
    assert _admin_messages(bob) == []


# 9
def test_tg_09_duplicate_update_is_stored_once(tg):
    update = _tg_update(60)
    assert _hook(tg.client, update).get_json()["status"] == "saved"
    assert _hook(tg.client, update).get_json()["status"] == "duplicate"
    assert _admin_messages(tg.alice["id"]) == ["Admin answer"]


# 10
def test_tg_10_replayed_message_under_a_new_update_id_or_other_path_is_stored_once(tg):
    from services.economy import telegram_poller

    update = _tg_update(70, message_id=88_001)
    assert _hook(tg.client, update).get_json()["status"] == "saved"
    replay = _tg_update(71, message_id=88_001)
    assert _hook(tg.client, replay).get_json()["status"] == "duplicate"
    telegram_poller._process_update(update)
    telegram_poller._process_update(replay)
    assert _admin_messages(tg.alice["id"]) == ["Admin answer"]


def test_tg_10b_concurrent_workers_store_one_reply(tg):
    from services.economy.support_chat import process_admin_update

    update = _tg_update(75, message_id=88_002)

    def _worker(i, barrier, queue):
        payload = update if i % 2 == 0 else _tg_update(1075 + i, message_id=88_002)
        barrier.wait()
        queue.put(process_admin_update(payload, source="webhook" if i % 2 == 0 else "poller").status)

    statuses = _run_workers(_worker, 6)
    assert sorted(statuses) == ["duplicate"] * 5 + ["saved"]
    assert _admin_messages(tg.alice["id"]) == ["Admin answer"]


# 11
def test_tg_11_malformed_updates_are_ignored_without_errors(tg):
    good = _tg_update(80)
    bad_payloads = [
        {"message": good["message"]},
        {**good, "update_id": "80"},
        {**good, "update_id": True},
        {**good, "update_id": -1},
        {"update_id": 81, "message": "text"},
        {"update_id": 82, "message": {**good["message"], "chat": "nope"}},
        {"update_id": 83, "message": {k: v for k, v in good["message"].items() if k != "from"}},
        {"update_id": 84, "message": {**good["message"], "reply_to_message": {"message_id": "9001"}}},
        {"update_id": 85, "message": {**good["message"], "text": "   "}},
        {"update_id": 86, "message": {**good["message"], "message_id": None}},
        {"update_id": 87, "message": {**good["message"], "from": {"id": "4242", "is_bot": False}}},
        [],
    ]
    for payload in bad_payloads:
        res = _hook(tg.client, payload)
        assert res.status_code == 200, payload
        assert res.get_json()["status"] == "ignored", payload
    raw = tg.client.post("/api/telegram-webhook", data="not json", content_type="application/json",
                         headers={"X-Telegram-Bot-Api-Secret-Token": TG_WEBHOOK_SECRET})
    assert raw.status_code == 200
    assert _all_admin_messages() == []


# 12
def test_tg_12_spoofed_flags_and_unsupported_update_types_are_ignored(tg):
    base = _tg_update(90)
    variants = [
        _tg_update(91, **{"from": {"id": ADMIN_ID, "is_bot": True}}),
        _tg_update(92, **{"from": {"id": ADMIN_ID}}),
        _tg_update(93, sender_chat={"id": GROUP_CHAT, "type": "supergroup"}),
        _tg_update(94, via_bot={"id": 1, "is_bot": True}),
        _tg_update(95, forward_origin={"type": "user", "sender_user": {"id": ADMIN_ID}}),
        _tg_update(96, forward_from={"id": ADMIN_ID}),
        _tg_update(97, reply_author=ADMIN_ID),
        _tg_update(98, reply_author=987_654),
        {"update_id": 99, "edited_message": base["message"]},
        {"update_id": 100, "channel_post": base["message"]},
        {"update_id": 101, "callback_query": {"from": {"id": ADMIN_ID}, "data": "x"}},
    ]
    for payload in variants:
        assert _hook(tg.client, payload).get_json()["status"] == "ignored", payload
    assert _all_admin_messages() == []


# 13
def test_tg_13_bindings_from_another_conversation_never_match(tg, monkeypatch):
    from services.economy.support_chat import bind_telegram_message

    bind_telegram_message(telegram_message_id=9003, user_id=tg.bob["id"], chat_id="-100777")
    assert _hook(tg.client, _tg_update(110, reply_to=9003)).get_json()["status"] == "ignored"
    cross_reply_chat = _tg_update(111, reply_to=9001)
    cross_reply_chat["message"]["reply_to_message"]["chat"] = {"id": -100777}
    assert _hook(tg.client, cross_reply_chat).get_json()["status"] == "ignored"
    monkeypatch.setenv("CHAT_ID", "-100777")
    moved = _tg_update(112, reply_to=9001, chat=-100777)
    assert _hook(tg.client, moved).get_json()["status"] == "ignored"
    assert _all_admin_messages() == []


def test_tg_feedback_binds_the_chat_then_reply_returns_to_that_user_and_api_errors_fail(tg, monkeypatch, caplog):
    sent = []

    class _Res:
        def __init__(self, payload, ok=True, status=200):
            self._payload, self.ok, self.status_code, self.text = payload, ok, status, json.dumps(payload)

        def json(self):
            return self._payload

    def _post(url, json=None, timeout=None, **_kw):
        _no_write_lock_held()
        sent.append(json)
        return _Res({"ok": True, "result": {"message_id": 777_001, "chat": {"id": GROUP_CHAT}}})

    monkeypatch.setattr(requests, "post", _post)
    client = _signed_in(_client(), tg.bob)
    res = client.post("/api/feedback", json={"message": f"Hello\n\nUser ID: {tg.alice['id']}"})
    assert res.status_code == 200, res.get_data(as_text=True)
    assert sent and sent[0]["chat_id"] == str(GROUP_CHAT)
    assert _hook(tg.client, _tg_update(120, reply_to=777_001, text="Reply to Bob")).get_json()["status"] == "saved"
    assert _admin_messages(tg.bob["id"]) == ["Reply to Bob"]
    assert _admin_messages(tg.alice["id"]) == []

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Res({"ok": False, "description": "chat not found"}, False, 400))
    failed = client.post("/api/feedback", json={"message": "second"})
    assert failed.status_code == 502 and failed.get_json()["saved"] is True


def test_tg_contact_form_is_ip_limited_and_its_messages_cannot_be_answered_into_accounts(tg, monkeypatch):
    import app as app_mod

    monkeypatch.setenv("CONTACT_LIMIT_PER_IP_HOUR", "2")
    delivered = []
    monkeypatch.setattr(app_mod, "_send_telegram_text",
                        lambda text: (delivered.append(text) or {"ok": True, "result": {"message_id": 990_001}}, None, 200))
    body = {"email": "visitor@example.com", "message": f"Support from Alice\n\nUser ID: {tg.alice['id']}"}
    statuses = [_client().post("/api/contact", json=body, environ_base={"REMOTE_ADDR": "198.51.100.9"}).status_code
                for _ in range(3)]
    assert statuses == [200, 200, 429]
    assert len(delivered) == 2
    reply = _tg_update(130, reply_to=990_001, reply_text=delivered[0])
    assert _hook(tg.client, reply).get_json()["status"] == "ignored"
    assert _all_admin_messages() == []


def test_tg_poller_applies_the_same_rules_and_requests_only_messages(tg, monkeypatch):
    from services.economy import telegram_poller

    class _Stop(BaseException):
        pass

    calls = []

    class _Res:
        content = b"1"
        text = ""

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    batches = iter([[_tg_update(140, sender=31337), _tg_update(141, text="Poller reply")]])

    def _get(url, params=None, timeout=None, **_kw):
        calls.append(params)
        try:
            return _Res({"ok": True, "result": next(batches)})
        except StopIteration:
            raise _Stop() from None

    monkeypatch.setattr(requests, "get", _get)
    with pytest.raises(_Stop):
        telegram_poller._poll_loop(TG_TOKEN)
    assert calls[0]["allowed_updates"] == '["message"]'
    assert _admin_messages(tg.alice["id"]) == ["Poller reply"]


# 14
def test_tg_14_token_and_secret_never_reach_logs_or_responses(tg, monkeypatch, caplog, raw_logging):
    from services.economy import telegram_poller

    caplog.set_level(logging.DEBUG)
    bodies = [
        _hook(tg.client, _tg_update(150)).get_data(as_text=True),
        _hook(tg.client, _tg_update(151, sender=1)).get_data(as_text=True),
        _hook(tg.client, _tg_update(150), secret="bad").get_data(as_text=True),
    ]

    def _boom(url, *args, **kwargs):
        cause = OSError(f"connect failed for {url}")
        try:
            raise cause
        except OSError as inner:
            raise requests.ConnectionError(
                f"HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded with url: "
                f"/bot{TG_TOKEN}/sendMessage (Caused by {inner!r})"
            ) from inner

    monkeypatch.setattr(requests, "post", _boom)
    monkeypatch.setattr(requests, "get", _boom)
    client = _signed_in(_client(), tg.alice)
    feedback = client.post("/api/feedback", json={"message": "help"})
    bodies.append(feedback.get_data(as_text=True))
    assert feedback.status_code == 502
    telegram_poller._delete_webhook(TG_TOKEN)

    class _Stop(BaseException):
        pass

    monkeypatch.setattr(telegram_poller.time, "sleep", lambda _s: (_ for _ in ()).throw(_Stop()))
    with pytest.raises(_Stop):
        telegram_poller._poll_loop(TG_TOKEN)

    from services.alerts import telegram_alerts
    from services.economy import lemon_squeezy_gateway

    monkeypatch.setattr(telegram_alerts, "_alerts_enabled", lambda: True)
    assert telegram_alerts.send_telegram_alert("x", key="k-4d", cooldown_sec=0) is False
    lemon_squeezy_gateway.notify_unhandled_payment("test", payload={})

    text = _log_text(caplog) + "\n".join(bodies)
    secret_part = TG_TOKEN.split(":", 1)[1]
    assert secret_part not in text
    assert TG_WEBHOOK_SECRET not in text
    assert "telegram" in text.lower()


# -------------------------------------------------------------------------------------- Gemini


class _GeminiRes:
    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _key_bearing_network_error(url, key):
    try:
        raise OSError(f"[Errno 111] Connection refused while opening {url}?key={key}")
    except OSError as inner:
        try:
            raise ConnectionError(f"urllib3 MaxRetryError: url={url}?key={key}") from inner
        except ConnectionError as middle:
            raise requests.ConnectionError(
                f"HTTPSConnectionPool(host='generativelanguage.googleapis.com', port=443): Max retries exceeded "
                f"with url: /v1beta/models/m:generateContent?key={key} (Caused by {middle!r})"
            ) from middle


@pytest.fixture()
def gemini(monkeypatch):
    from services import free_ai_quota, gemini_client

    monkeypatch.setenv("GOOGLE_API_KEY", GEMINI_KEY)
    monkeypatch.setattr(gemini_client.time, "sleep", lambda _s: None)
    monkeypatch.setattr(free_ai_quota, "before_provider_call", lambda _p: True)
    calls = []
    state = SimpleNamespace(calls=calls, script=[])

    def _post(url, params=None, headers=None, json=None, timeout=None, **_kw):
        calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        step = state.script.pop(0) if state.script else _GeminiRes(500, {"error": {"message": "boom"}})
        if callable(step):
            return step(url)
        return step

    monkeypatch.setattr(requests, "post", _post)
    return state


def _all_text(*values) -> str:
    return "\n".join(json.dumps(v, default=str) if not isinstance(v, str) else v for v in values)


def test_gemini_key_travels_only_in_the_header(gemini):
    from services import gemini_client

    ok = _GeminiRes(200, {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]})
    gemini.script[:] = [ok, _GeminiRes(200, {"candidates": [{"content": {"parts": [{"text": "plain"}]}}]})]
    data, _diag = gemini_client.generate_json(system_prompt="s", user_prompt="u", max_retries=0)
    text, _diag2 = gemini_client.generate_text(system_prompt="s", content="c", max_retries=0)
    assert data == {"a": 1} and text == "plain"
    for call in gemini.calls:
        assert call["params"] == {}
        assert GEMINI_KEY not in call["url"]
        assert call["headers"].get("x-goog-api-key") == GEMINI_KEY
    assert gemini_client._gemini_auth(ODD_GEMINI_KEY) == ({}, {"x-goog-api-key": ODD_GEMINI_KEY})


@pytest.mark.parametrize("key", [GEMINI_KEY, ODD_GEMINI_KEY, "AQ.SENTINELoauthTok_0123456789abcdef"])
def test_gemini_network_errors_with_nested_causes_never_leak_the_key(gemini, monkeypatch, caplog, raw_logging, key):
    from services import gemini_client

    monkeypatch.setenv("GOOGLE_API_KEY", key)
    caplog.set_level(logging.DEBUG)
    gemini.script[:] = [lambda url: _key_bearing_network_error(url, key)] * 12
    data, diag = gemini_client.generate_json(system_prompt="s", user_prompt="u", max_retries=2, models=["m1", "m2"])
    assert data is None and diag["failure_reason"] == "unavailable"
    assert "ConnectionError" in diag["error_message"]
    gemini.script[:] = [lambda url: _key_bearing_network_error(url, key)] * 4
    text, diag2 = gemini_client.generate_text(system_prompt="s", content="c", max_retries=1)
    assert text is None
    blob = _all_text(diag, diag2, _log_text(caplog))
    assert key not in blob
    assert "retry" in _log_text(caplog).lower()


def test_gemini_http_error_bodies_and_unexpected_exceptions_are_redacted(gemini, caplog, raw_logging):
    from services import gemini_client

    caplog.set_level(logging.DEBUG)
    echo = {"error": {"message": f"API key not valid: {GEMINI_KEY}", "status": "INVALID_ARGUMENT"}}
    gemini.script[:] = [
        _GeminiRes(503, echo), _GeminiRes(503, None, text=f"overloaded ?key={GEMINI_KEY}"), _GeminiRes(400, echo),
    ]
    _data, diag_400 = gemini_client.generate_json(system_prompt="s", user_prompt="u", max_retries=2, models=["m"])
    assert diag_400["http_status"] == 400 and diag_400["failure_reason"] == "validation_error"

    def _weird(url):
        raise RuntimeError(f"unexpected failure for {url}?key={GEMINI_KEY} headers={{'x-goog-api-key': '{GEMINI_KEY}'}}")

    gemini.script[:] = [_weird]
    _data, diag_exc = gemini_client.generate_json(system_prompt="s", user_prompt="u", max_retries=0, models=["m"])
    gemini.script[:] = [_GeminiRes(401, None, text=f"denied for key {GEMINI_KEY}")]
    _text, diag_text = gemini_client.generate_text(system_prompt="s", content="c", max_retries=0)
    blob = _all_text(diag_400, diag_exc, diag_text, _log_text(caplog))
    assert GEMINI_KEY not in blob
    assert "RuntimeError" in diag_exc["error_message"]


def test_gemini_adapters_raise_sanitized_errors_and_public_payloads_drop_details(gemini):
    import app as app_mod
    from formatter_v2.chat.gemini_client import GeminiChatClient
    from formatter_v2.smartform.gemini_client import GeminiSmartformClient

    gemini.script[:] = [lambda url: _key_bearing_network_error(url, GEMINI_KEY)] * 20
    for client in (GeminiSmartformClient(), GeminiChatClient()):
        with pytest.raises(Exception) as caught:
            client.generate(system_instruction="s", user_message="u", temperature=0.1,
                            response_mime_type="application/json", response_schema={}, timeout_s=10)
        assert GEMINI_KEY not in str(caught.value)
        assert GEMINI_KEY not in app_mod._public_error(caught.value)
    payload = app_mod._public_ai_payload({"gemini_diagnostics": {"error_message": "x", "model": "m"}})
    assert payload == {"gemini_diagnostics": {"model": "m"}}


@pytest.fixture()
def admin_client(economy, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    admin = _user("ops@example.com", admin=True)
    return _signed_in(_client(), admin)


@pytest.mark.parametrize("debug", [False, True])
def test_gemini_admin_diagnostics_never_show_the_key(admin_client, gemini, monkeypatch, caplog, raw_logging, debug):
    import app as app_mod

    monkeypatch.setattr(app_mod.app, "debug", debug)
    caplog.set_level(logging.DEBUG)
    gemini.script[:] = [lambda url: _key_bearing_network_error(url, GEMINI_KEY)]
    failed = admin_client.post("/api/test/gemini")
    assert failed.status_code == 502
    echo = _GeminiRes(400, {"error": {"message": f"bad key {GEMINI_KEY}"}})
    echo.headers = {"Content-Type": "application/json", "X-Echo": f"key={GEMINI_KEY}", "x-goog-api-key": GEMINI_KEY}
    gemini.script[:] = [echo]
    shown = admin_client.post("/api/test/gemini")
    assert shown.status_code == 200 and shown.get_json()["http_status"] == 400
    assert gemini.calls[-1]["params"] == {}
    blob = _all_text(failed.get_data(as_text=True), shown.get_data(as_text=True), _log_text(caplog))
    assert GEMINI_KEY not in blob
    assert "ConnectionError" in failed.get_json()["error"]


def test_gemini_admin_diagnostics_stay_closed_to_non_admins(economy, gemini, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOOLS_ENABLED", "1")
    user = _user("user@example.com")
    assert _signed_in(_client(), user).post("/api/test/gemini").status_code == 404
    assert _client().post("/api/test/gemini").status_code == 404
    assert gemini.calls == []


def test_startup_and_preflight_diagnostics_do_not_include_keys(gemini, monkeypatch):
    from services.assignment_project.preflight import static_provider_checks

    monkeypatch.setenv("TELEGRAM_TOKEN", TG_TOKEN)
    report = json.dumps(static_provider_checks(), default=str)
    assert GEMINI_KEY not in report and TG_TOKEN not in report


# ------------------------------------------------------------------------------ Redaction core


def test_redaction_covers_formats_chains_and_configured_secrets(monkeypatch):
    monkeypatch.setenv("SOME_VENDOR_API_KEY", "vndr$Zq9!unusual-secret-value")
    samples = {
        f"https://generativelanguage.googleapis.com/v1beta/models/m:generateContent?key={GEMINI_KEY}&alt=json": GEMINI_KEY,
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage": TG_TOKEN.split(":")[1],
        "headers={'Authorization': 'Bearer abcdefghijklmnop123'}": "abcdefghijklmnop123",
        "x-api-key: sk-ant-api03-SENTINELabcdef": "SENTINELabcdef",
        "token=SENTINELtoken123&next=1": "SENTINELtoken123",
        "failed with vndr$Zq9!unusual-secret-value inside": "vndr$Zq9!unusual-secret-value",
        "X-Telegram-Bot-Api-Secret-Token: whsecSENTINEL_x": "whsecSENTINEL_x",
    }
    for text, secret in samples.items():
        assert secret not in redact(text), text
    assert redact("Gemini retry model=m attempt=2 status=503") == "Gemini retry model=m attempt=2 status=503"
    try:
        try:
            raise KeyError(f"lookup {GEMINI_KEY}")
        except KeyError as inner:
            raise RuntimeError("outer ?key=" + GEMINI_KEY) from inner
    except RuntimeError as exc:
        described = describe_exception(exc)
    assert GEMINI_KEY not in described and "RuntimeError" in described and "KeyError" in described


def test_global_log_redaction_covers_tracebacks_at_debug(caplog):
    install_log_redaction()
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger("tests.4d.redaction")
    log.debug("debug url %s", f"https://x.example/?key={GEMINI_KEY}")
    try:
        raise requests.ConnectionError(f"url: /bot{TG_TOKEN}/getUpdates")
    except requests.ConnectionError:
        log.exception("poll failed")
    text = _log_text(caplog)
    assert "poll failed" in text and "Traceback" in text
    assert GEMINI_KEY not in text and TG_TOKEN.split(":")[1] not in text
