"""Sign in with Google, Apple, or Microsoft (OIDC authorization code).

Identity is always ``(provider, subject)``. Email is used only to link or create
accounts when the provider asserts a verified address. Apple often omits email
after the first consent — those return visits must match an existing identity.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from jwt import PyJWKClient

from .db import connect
from .disposable_email import DisposableEmailError

logger = logging.getLogger(__name__)

PROVIDERS = ("google", "apple", "microsoft")
SESSION_STATE_KEY = "oauth_state"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_identities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider   TEXT NOT NULL,
    subject    TEXT NOT NULL,
    email      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (provider, subject)
);
CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities(user_id);
"""

_GOOGLE = {
    "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
    "token": "https://oauth2.googleapis.com/token",
    "jwks": "https://www.googleapis.com/oauth2/v3/certs",
    "issuer": ("https://accounts.google.com",),
    "scope": "openid email profile",
}
_MICROSOFT = {
    "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "jwks": "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    "scope": "openid email profile offline_access",
}
_APPLE = {
    "authorize": "https://appleid.apple.com/auth/authorize",
    "token": "https://appleid.apple.com/auth/token",
    "jwks": "https://appleid.apple.com/auth/keys",
    "issuer": ("https://appleid.apple.com",),
    "scope": "name email",
}


class OAuthError(Exception):
    """User-facing OAuth failure."""


def ensure_schema(conn=None) -> None:
    if conn is not None:
        conn.executescript(_SCHEMA)
        return
    with connect() as owned:
        owned.executescript(_SCHEMA)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def provider_configured(provider: str) -> bool:
    p = (provider or "").strip().lower()
    if p == "google":
        return bool(_env("GOOGLE_OAUTH_CLIENT_ID") and _env("GOOGLE_OAUTH_CLIENT_SECRET"))
    if p == "microsoft":
        return bool(_env("MICROSOFT_OAUTH_CLIENT_ID") and _env("MICROSOFT_OAUTH_CLIENT_SECRET"))
    if p == "apple":
        return bool(
            _env("APPLE_OAUTH_CLIENT_ID")
            and _env("APPLE_OAUTH_TEAM_ID")
            and _env("APPLE_OAUTH_KEY_ID")
            and (_env("APPLE_OAUTH_PRIVATE_KEY") or _env("APPLE_OAUTH_PRIVATE_KEY_PATH"))
        )
    return False


def configured_providers() -> list[str]:
    return [p for p in PROVIDERS if provider_configured(p)]


def callback_url(provider: str) -> str:
    from services.public_origin import canonical_origin

    base = canonical_origin().rstrip("/")
    return f"{base}/auth/oauth/{provider}/callback"


def _apple_client_secret() -> str:
    """Apple requires a short-lived JWT signed with the .p8 key as client_secret."""
    client_id = _env("APPLE_OAUTH_CLIENT_ID")
    team_id = _env("APPLE_OAUTH_TEAM_ID")
    key_id = _env("APPLE_OAUTH_KEY_ID")
    pem = _env("APPLE_OAUTH_PRIVATE_KEY")
    path = _env("APPLE_OAUTH_PRIVATE_KEY_PATH")
    if not pem and path:
        with open(path, "r", encoding="utf-8") as fh:
            pem = fh.read()
    if not pem:
        raise OAuthError("Apple Sign In is not configured.")
    pem = pem.replace("\\n", "\n")
    now = int(time.time())
    return jwt.encode(
        {
            "iss": team_id,
            "iat": now,
            "exp": now + 1500,
            "aud": "https://appleid.apple.com",
            "sub": client_id,
        },
        pem,
        algorithm="ES256",
        headers={"kid": key_id},
    )


def _client_creds(provider: str) -> tuple[str, str]:
    if provider == "google":
        return _env("GOOGLE_OAUTH_CLIENT_ID"), _env("GOOGLE_OAUTH_CLIENT_SECRET")
    if provider == "microsoft":
        return _env("MICROSOFT_OAUTH_CLIENT_ID"), _env("MICROSOFT_OAUTH_CLIENT_SECRET")
    if provider == "apple":
        return _env("APPLE_OAUTH_CLIENT_ID"), _apple_client_secret()
    raise OAuthError("Unknown sign-in provider.")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode(
        "ascii"
    )
    return verifier, challenge


def begin_login(provider: str, *, next_url: str | None, session: Any) -> str:
    """Store OAuth state in the session and return the provider authorize URL."""
    p = (provider or "").strip().lower()
    if p not in PROVIDERS or not provider_configured(p):
        raise OAuthError("That sign-in option is not available right now.")
    client_id, _secret = _client_creds(p)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    session[SESSION_STATE_KEY] = {
        "provider": p,
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "next": (next_url or "")[:500],
    }
    redirect_uri = callback_url(p)
    if p == "google":
        conf = _GOOGLE
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": conf["scope"],
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        return conf["authorize"] + "?" + urlencode(params)
    if p == "microsoft":
        conf = _MICROSOFT
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": conf["scope"],
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        return conf["authorize"] + "?" + urlencode(params)
    conf = _APPLE
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code id_token",
        "scope": conf["scope"],
        "state": state,
        "nonce": nonce,
        "response_mode": "form_post",
    }
    return conf["authorize"] + "?" + urlencode(params)


def _exchange_code(provider: str, code: str, *, verifier: str) -> dict[str, Any]:
    client_id, client_secret = _client_creds(provider)
    redirect_uri = callback_url(provider)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if provider in ("google", "microsoft"):
        data["code_verifier"] = verifier
    try:
        token_url = {"google": _GOOGLE["token"], "microsoft": _MICROSOFT["token"], "apple": _APPLE["token"]}[
            provider
        ]
        resp = requests.post(token_url, data=data, timeout=20)
    except requests.RequestException as exc:
        logger.warning("oauth token exchange failed provider=%s err=%s", provider, type(exc).__name__)
        raise OAuthError("Sign-in provider is unavailable. Try again.") from None
    if resp.status_code >= 400:
        logger.warning("oauth token HTTP %s provider=%s", resp.status_code, provider)
        raise OAuthError("Sign-in was denied or expired. Try again.")
    payload = resp.json()
    if not isinstance(payload, dict) or not payload.get("id_token"):
        raise OAuthError("Sign-in provider did not return an identity token.")
    return payload


def _truthy_claim(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes"):
        return True
    return False


def _hmac_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _verify_id_token(provider: str, id_token: str, *, nonce: str | None) -> dict[str, Any]:
    client_id, _ = _client_creds(provider)
    if provider == "google":
        jwks_url, issuers = _GOOGLE["jwks"], _GOOGLE["issuer"]
    elif provider == "microsoft":
        jwks_url, issuers = _MICROSOFT["jwks"], None
    else:
        jwks_url, issuers = _APPLE["jwks"], _APPLE["issuer"]

    try:
        jwk_client = PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=client_id,
            options={"require": ["sub", "iss", "aud", "exp"]},
        )
    except Exception:  # noqa: BLE001
        logger.warning("oauth id_token invalid provider=%s", provider)
        raise OAuthError("Could not verify the sign-in token.") from None

    iss = str(claims.get("iss") or "")
    if provider == "microsoft":
        if not iss.startswith("https://login.microsoftonline.com/") or "/v2.0" not in iss:
            raise OAuthError("Could not verify the sign-in token.")
    elif issuers and iss not in issuers:
        raise OAuthError("Could not verify the sign-in token.")

    if nonce:
        got = claims.get("nonce")
        if not got or not _hmac_compare(str(got), nonce):
            raise OAuthError("Could not verify the sign-in token.")
    return claims


def _find_identity(provider: str, subject: str) -> int | None:
    with connect() as conn:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT user_id FROM oauth_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        ).fetchone()
    return int(row["user_id"]) if row else None


def _find_user_by_email(email: str) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, is_blocked FROM users WHERE lower(email) = ?",
            (email.strip().lower(),),
        ).fetchone()
    if row is None:
        return None
    if int(row["is_blocked"] or 0):
        return None
    return int(row["id"])


def _link_identity(user_id: int, provider: str, subject: str, email: str | None) -> None:
    with connect() as conn:
        ensure_schema(conn)
        conn.execute(
            "INSERT INTO oauth_identities (user_id, provider, subject, email) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(provider, subject) DO UPDATE SET "
            "email = COALESCE(excluded.email, oauth_identities.email)",
            (int(user_id), provider, subject, (email or None)),
        )


def _create_oauth_user(*, email: str, name: str | None) -> int:
    """Create a user for a first-time OAuth sign-in (unusable random password)."""
    from .auth import DuplicateEmail, create_user

    password = secrets.token_urlsafe(24)
    try:
        user = create_user(email, password, name=name)
    except DisposableEmailError as exc:
        raise OAuthError(str(exc) or "That email provider is not allowed.") from None
    except DuplicateEmail:
        uid = _find_user_by_email(email)
        if uid is None:
            raise OAuthError("Could not create an account for that email.") from None
        return uid
    uid = int(user["id"])
    with connect() as conn:
        conn.execute(
            "UPDATE users SET is_verified = 1, password_set = 0, verification_code = NULL, "
            "verification_code_expires = NULL, verification_attempts = 0 WHERE id = ?",
            (uid,),
        )
    return uid


def linked_providers(user_id: int) -> list[str]:
    ensure_schema()
    with connect() as conn:
        rows = conn.execute(
            "SELECT provider FROM oauth_identities WHERE user_id = ? ORDER BY provider",
            (int(user_id),),
        ).fetchall()
    return [str(r["provider"]) for r in rows]


def _parse_apple_user(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _display_name(claims: dict[str, Any], form_user: dict[str, Any] | None) -> str | None:
    if form_user:
        name_obj = form_user.get("name")
        if isinstance(name_obj, dict):
            first = str(name_obj.get("firstName") or "").strip()
            last = str(name_obj.get("lastName") or "").strip()
            combined = f"{first} {last}".strip()
            if combined:
                return combined[:80]
    name = str(claims.get("name") or "").strip()
    return name[:80] if name else None


def complete_login(
    provider: str,
    *,
    code: str | None,
    id_token: str | None,
    state: str | None,
    session: Any,
    form_user: Any = None,
) -> dict[str, Any]:
    """Validate callback params, resolve/create the user, return ``{user_id, next}``."""
    p = (provider or "").strip().lower()
    saved = session.pop(SESSION_STATE_KEY, None)
    if not isinstance(saved, dict) or saved.get("provider") != p:
        raise OAuthError("Sign-in expired. Start again.")
    if not state or not _hmac_compare(str(saved.get("state") or ""), str(state)):
        raise OAuthError("Sign-in expired. Start again.")

    nonce = str(saved.get("nonce") or "")
    verifier = str(saved.get("verifier") or "")
    next_url = str(saved.get("next") or "")

    token_id = (id_token or "").strip() or None
    if code and not token_id:
        tokens = _exchange_code(p, code.strip(), verifier=verifier)
        token_id = str(tokens.get("id_token") or "")
    if not token_id:
        raise OAuthError("Sign-in provider did not return an identity token.")

    claims = _verify_id_token(p, token_id, nonce=nonce or None)
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise OAuthError("Sign-in provider did not return a stable identity.")

    email = (str(claims.get("email") or "").strip().lower() or None)
    email_verified = _truthy_claim(claims.get("email_verified"))
    if p == "apple" and email:
        # Apple only returns email when the address is verified for the Apple ID.
        email_verified = True
    if p == "microsoft" and not email:
        pref = str(claims.get("preferred_username") or "").strip().lower()
        if "@" in pref:
            email = pref
            email_verified = True
    elif p == "microsoft" and email:
        email_verified = True

    apple_user = _parse_apple_user(form_user)
    name = _display_name(claims, apple_user)

    existing = _find_identity(p, subject)
    if existing is not None:
        return {"user_id": existing, "next": next_url, "provider": p}

    if email and email_verified:
        uid = _find_user_by_email(email)
        if uid is None:
            uid = _create_oauth_user(email=email, name=name)
        else:
            with connect() as conn:
                conn.execute(
                    "UPDATE users SET is_verified = 1, verification_code = NULL, "
                    "verification_code_expires = NULL, verification_attempts = 0 "
                    "WHERE id = ? AND is_verified = 0",
                    (uid,),
                )
        _link_identity(uid, p, subject, email)
        return {"user_id": uid, "next": next_url, "provider": p}

    raise OAuthError(
        "We could not match that sign-in to an email. "
        "Sign in with email once, or try Google / Microsoft."
    )
