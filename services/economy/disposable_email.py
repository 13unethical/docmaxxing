"""Disposable / temporary email domain blocker.

Uses a curated local blocklist (fast, offline) plus an optional remote check
via ``DISPOSABLE_EMAIL_API_URL`` when configured.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

# High-signal disposable / temp-mail domains (lowercase, no @).
_BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        "10minutemail.com",
        "10minutemail.net",
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamail.biz",
        "guerrillamail.de",
        "sharklasers.com",
        "grr.la",
        "guerrillamailblock.com",
        "mailinator.com",
        "mailinator.net",
        "mailinator2.com",
        "trashmail.com",
        "trashmail.me",
        "trashmail.net",
        "trash-mail.com",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
        "tempmail.com",
        "temp-mail.org",
        "temp-mail.io",
        "tempmailo.com",
        "tempail.com",
        "throwawaymail.com",
        "throwaway.email",
        "getnada.com",
        "nada.email",
        "maildrop.cc",
        "discard.email",
        "discardmail.com",
        "dispostable.com",
        "fakeinbox.com",
        "fakemailgenerator.com",
        "mailnesia.com",
        "mailcatch.com",
        "mytemp.email",
        "tmpmail.org",
        "tmpmail.net",
        "moakt.com",
        "emailondeck.com",
        "getairmail.com",
        "mailnull.com",
        "spamgourmet.com",
        "spam4.me",
        "inboxkitten.com",
        "burnermail.io",
        "mail.tm",
        "mail.gw",
        "tempmail.dev",
        "emailfake.com",
        "crazymailing.com",
        "mintemail.com",
        "mohmal.com",
        "tempinbox.com",
        "33mail.com",
        "anonbox.net",
        "anonymbox.com",
        "bccto.me",
        "binkmail.com",
        "bobmail.info",
        "bugmenot.com",
        "bumpymail.com",
        "centermail.com",
        "cool.fr.nf",
        "courriel.fr.nf",
        "curryworld.de",
        "dacoolest.com",
        "dandikmail.com",
        "dayrep.com",
        "deadaddress.com",
        "despam.it",
        "devnullmail.com",
        "digitalsanctuary.com",
        "dodgeit.com",
        "dodgit.com",
        "donemail.ru",
        "dontreg.com",
        "dontsendmespam.de",
        "dumpmail.de",
        "e4ward.com",
        "email60.com",
        "emailigo.de",
        "emailsensei.com",
        "emailtemporario.com.br",
        "emz.net",
        "explodemail.com",
        "filzmail.com",
        "frapmail.com",
        "getonemail.com",
        "gishpuppy.com",
        "great-host.in",
        "haltospam.com",
        "hidemail.de",
        "ieh-mail.de",
        "imails.info",
        "incognitomail.org",
        "insorg.org",
        "ipoo.org",
        "jetable.org",
        "kasmail.com",
        "klassmaster.com",
        "koszmail.pl",
        "kurzepost.de",
        "lifebyfood.com",
        "link2mail.net",
        "litedrop.com",
        "lookugly.com",
        "lopl.co.cc",
        "lr78.com",
        "m4ilweb.info",
        "mailbidon.com",
        "mailblocks.com",
        "maileater.com",
        "mailexpire.com",
        "mailforspam.com",
        "mailfreeonline.com",
        "mailin8r.com",
        "mailimate.com",
        "mailismagic.com",
        "mailme.lv",
        "mailmetrash.com",
        "mailmoat.com",
        "mailshell.com",
        "mailsiphon.com",
        "mailslite.com",
        "mailtemp.info",
        "mailzilla.com",
        "mbx.cc",
        "meltmail.com",
        "messagebeamer.de",
        "mierdamail.com",
        "mt2009.com",
        "mycleaninbox.net",
        "mypartyclip.de",
        "myphantomemail.com",
        "myspaceinc.com",
        "mytrashmail.com",
        "neomailbox.com",
        "nervmich.net",
        "netzidiot.de",
        "nobulk.com",
        "noclickemail.com",
        "nogmailspam.info",
        "nomail.xl.cx",
        "nomail2me.com",
        "nospam.ze.tc",
        "nospamfor.us",
        "nowmymail.com",
        "objectmail.com",
        "obobbo.com",
        "oneoffemail.com",
        "onewaymail.com",
        "ordinaryamerican.net",
        "otherinbox.com",
        "owlpic.com",
        "pookmail.com",
        "proxymail.eu",
        "putthisinyourspamdatabase.com",
        "quickinbox.com",
        "rcpt.at",
        "recode.me",
        "recursor.net",
        "rtrtr.com",
        "s0ny.net",
        "safe-mail.net",
        "safetymail.info",
        "selfdestructingmail.com",
        "sendspamhere.com",
        "shiftmail.com",
        "skeefmail.com",
        "slopsbox.com",
        "smellfear.com",
        "snakemail.com",
        "sneakemail.com",
        "sofort-mail.de",
        "sogetthis.com",
        "soodonims.com",
        "spam.la",
        "spamavert.com",
        "spambob.com",
        "spambob.net",
        "spambog.com",
        "spambox.us",
        "spamcero.com",
        "spamday.com",
        "spamex.com",
        "spamfree24.org",
        "spamfree24.de",
        "spamgourmet.net",
        "spamherelots.com",
        "spamhole.com",
        "spamify.com",
        "spaminator.de",
        "spamkill.info",
        "spaml.com",
        "spammotel.com",
        "spamobox.com",
        "spamoff.de",
        "spamslicer.com",
        "spamspot.com",
        "spamthis.co.uk",
        "spamthisplease.com",
        "speed.1s.fr",
        "suremail.info",
        "teewars.org",
        "teleosaurs.xyz",
        "tempalias.com",
        "tempe-mail.com",
        "tempemail.biz",
        "tempemail.com",
        "tempemail.net",
        "tempinbox.co.uk",
        "tempmail.it",
        "tempmail2.com",
        "tempmaildemo.com",
        "tempmailer.com",
        "tempthe.net",
        "thankyou2010.com",
        "thisisnotmyrealemail.com",
        "throwam.com",
        "tilien.com",
        "tmail.ws",
        "tmailinator.com",
        "tradermail.info",
        "trash2009.com",
        "trashymail.com",
        "trbvm.com",
        "tyldd.com",
        "uggsrock.com",
        "wegwerfadresse.de",
        "wegwerfemail.de",
        "wh4f.org",
        "whyspam.me",
        "willselfdestruct.com",
        "winemaven.info",
        "wronghead.com",
        "wuzup.net",
        "wuzupmail.net",
        "yogamaven.com",
        "yuurok.com",
        "zehnminutenmail.de",
        "zippymail.info",
        "zoemail.org",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]+)$")


class DisposableEmailError(ValueError):
    """Raised when an email uses a blocked disposable domain."""


def extract_domain(email: str) -> str | None:
    text = (email or "").strip().lower()
    match = _EMAIL_RE.match(text)
    if not match:
        return None
    return match.group(1).lower()


@lru_cache(maxsize=1)
def _extra_blocked_from_env() -> frozenset[str]:
    raw = (os.environ.get("DISPOSABLE_EMAIL_EXTRA_DOMAINS") or "").strip()
    if not raw:
        return frozenset()
    return frozenset(p.strip().lower() for p in raw.split(",") if p.strip())


def is_disposable_domain(domain: str) -> bool:
    domain = (domain or "").strip().lower().lstrip(".")
    if not domain:
        return False
    blocked = _BLOCKED_DOMAINS | _extra_blocked_from_env()
    if domain in blocked:
        return True
    # Subdomain of a blocked apex (e.g. mail.yopmail.com)
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in blocked:
            return True
    return False


def _remote_disposable_check(email: str) -> bool | None:
    """Optional remote API. Returns True/False, or None if unavailable."""
    url = (os.environ.get("DISPOSABLE_EMAIL_API_URL") or "").strip()
    if not url:
        return None
    try:
        res = requests.get(url, params={"email": email}, timeout=2.5)
        if res.status_code >= 400:
            return None
        data = res.json()
        if isinstance(data, dict):
            if "disposable" in data:
                return bool(data["disposable"])
            if "temporary" in data:
                return bool(data["temporary"])
    except Exception:  # noqa: BLE001
        logger.debug("disposable email API check failed", exc_info=True)
    return None


def assert_not_disposable(email: str) -> None:
    """Raise DisposableEmailError if the address looks temporary."""
    domain = extract_domain(email)
    if domain is None:
        raise DisposableEmailError("A valid email is required.")
    if is_disposable_domain(domain):
        raise DisposableEmailError(
            "Temporary or disposable email addresses are not allowed. "
            "Please use a permanent email (university or personal)."
        )
    remote = _remote_disposable_check((email or "").strip().lower())
    if remote is True:
        raise DisposableEmailError(
            "Temporary or disposable email addresses are not allowed. "
            "Please use a permanent email (university or personal)."
        )
