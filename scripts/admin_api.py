#!/usr/bin/env python3
"""Call admin-only DocMaxxing APIs from a shell on the server, as a signed-in verified admin.

There is no token or password in this file and no bypass: you sign in with your own admin
account once, the session cookie is kept in a private cookie jar (mode 600), and every
state-changing call sends that session's CSRF token, exactly like the admin pages do.

    python3 scripts/admin_api.py login --jar ~/.docmaxxing-admin.cookies
    python3 scripts/admin_api.py call POST /api/browser/connect --jar ~/.docmaxxing-admin.cookies
    python3 scripts/admin_api.py call GET /api/browser/health --jar ~/.docmaxxing-admin.cookies

``--base`` (default ``$DOCMAXXING_API`` or http://127.0.0.1:8000) must be https or a loopback
address; the session cookie is never sent over plain http to another host.
"""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class _LoopbackCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """The app's session cookie is Secure; gunicorn on loopback is reached over plain http."""

    def return_ok_secure(self, cookie, request):  # noqa: D401
        host = urllib.parse.urlsplit(request.get_full_url()).hostname or ""
        if host in _LOOPBACK:
            return True
        return super().return_ok_secure(cookie, request)


def _check_base(base: str) -> str:
    parts = urllib.parse.urlsplit(base)
    if parts.scheme == "https" or (parts.scheme == "http" and (parts.hostname or "") in _LOOPBACK):
        return base.rstrip("/")
    raise SystemExit("--base must be https:// or a loopback http:// address")


def _opener(jar_path: str, *, create: bool):
    jar = http.cookiejar.MozillaCookieJar(jar_path, policy=_LoopbackCookiePolicy())
    if os.path.exists(jar_path):
        jar.load(ignore_discard=True, ignore_expires=True)
    elif not create:
        raise SystemExit(f"Cookie jar {jar_path} not found. Run: admin_api.py login --jar {jar_path}")
    return jar, urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _save(jar) -> None:
    old = os.umask(0o077)
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    finally:
        os.umask(old)
    os.chmod(jar.filename, 0o600)


def _request(opener, method: str, url: str, *, body: dict | None = None, token: str | None = None,
             timeout: float = 120.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-CSRF-Token", token)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _csrf_token(opener, base: str) -> str:
    status, text = _request(opener, "GET", f"{base}/api/csrf-token", timeout=30)
    try:
        token = json.loads(text).get("csrf_token") if status == 200 else None
    except json.JSONDecodeError:
        token = None
    if not token:
        raise SystemExit(f"Could not get a CSRF token (HTTP {status}).")
    return token


def cmd_login(args) -> int:
    base = _check_base(args.base)
    jar, opener = _opener(args.jar, create=True)
    email = input("Admin email: ").strip()
    password = getpass.getpass("Password: ")
    token = _csrf_token(opener, base)
    status, text = _request(opener, "POST", f"{base}/api/auth/login",
                            body={"email": email, "password": password}, token=token, timeout=30)
    password = ""
    if status != 200:
        print(f"Sign-in failed (HTTP {status}).", file=sys.stderr)
        return 1
    _save(jar)
    print(f"Signed in; session saved to {args.jar}")
    return 0


def cmd_call(args) -> int:
    base = _check_base(args.base)
    method = args.method.upper()
    path = args.path if args.path.startswith("/") else f"/{args.path}"
    jar, opener = _opener(args.jar, create=False)
    token = None if method in _SAFE_METHODS else _csrf_token(opener, base)
    body = json.loads(args.data) if args.data else ({} if token else None)
    status, text = _request(opener, method, f"{base}{path}", body=body, token=token, timeout=args.timeout)
    _save(jar)
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        data = {"error": "Non-JSON response", "http_status": status}
    if status >= 400 and isinstance(data, dict):
        data.setdefault("http_status", status)
    print(json.dumps(data))
    return 0 if status < 400 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=os.environ.get("DOCMAXXING_API") or "http://127.0.0.1:8000")
    sub = parser.add_subparsers(dest="command", required=True)
    login = sub.add_parser("login", help="sign in and store the session cookie")
    login.add_argument("--jar", required=True)
    login.set_defaults(func=cmd_login)
    call = sub.add_parser("call", help="call an admin API with the stored session")
    call.add_argument("method")
    call.add_argument("path")
    call.add_argument("--jar", required=True)
    call.add_argument("--data", help="JSON body")
    call.add_argument("--timeout", type=float, default=120.0)
    call.set_defaults(func=cmd_call)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
