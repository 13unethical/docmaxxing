"""Data and account actions for the admin panel in the new app (/app#/admin).

Overview KPIs per period, the user list with flags (staff / test / suspicious /
blocked), the activity feed ("one action = one line") and credit / block actions.
Day boundaries follow Tashkent time, like the daily counters in site_settings.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Iterable

from .activity_log import ensure_activity_schema, log_activity
from .db import connect
from .disposable_email import extract_domain, is_disposable_domain
from .pricing import WELCOME_BONUS
from .wallet import WalletService

TZ = timezone(timedelta(hours=5))
_FMT = "%Y-%m-%d %H:%M:%S"
PERIODS: dict[str, int | None] = {"today": 1, "d7": 7, "d30": 30, "all": None}
PERIOD_LABELS = {"today": "today", "d7": "7 days", "d30": "30 days", "all": "all time"}
_PREV_LABEL = {"today": "yesterday", "d7": "prev. week", "d30": "prev. 30d"}
ADMIN_FEATURES = ("admin_set", "admin_adjust", "admin_adjustment")
FLAGS = ("staff", "test")
_LOOPBACK = {"127.0.0.1", "::1", "localhost", ""}
_SCANNER_RE = re.compile(
    r"\.php|wp-|xmlrpc|\.env|graphql|/\.git|/cgi-bin|/admin\.|/vendor/|/\.well-known/(?!security)|setup|/boaform",
    re.IGNORECASE,
)

FEATURE_LABELS = {
    "humanize": "Humanizer",
    "turnitin": "AI check",
    "detect": "AI check",
    "assignment": "Assignment",
    "presentation": "Slides",
    "presentation_research": "Slides",
    "cite": "Citation",
    "veil": "Veil pass",
    "topup": "Credits purchase",
    "purchase": "Credits purchase",
    "plan": "Plan credits",
    "welcome_bonus": "Welcome bonus",
    "referral_signup": "Referral bonus",
    "referral_convert": "Referral balance → credits",
}
CATEGORY_LABELS = {
    "humanizer": "Humanizer",
    "turnitin": "AI check",
    "detector": "AI check",
    "assignment": "Assignment",
    "formatter": "Formatting",
    "payment": "Checkout",
    "auth": "Sign-in",
    "account": "Account",
    "support": "Support chat",
    "referral": "Referral",
    "admin": "Admin",
}
USAGE_FEATURES = [("Humanizer", ("humanize",)), ("AI check", ("turnitin", "detect")),
                  ("Formatting", ()), ("Assignment", ("assignment",)),
                  ("Slides", ("presentation", "presentation_research")), ("Veil", ("veil",))]


class AdminPanelError(Exception):
    """Rejected admin action (shown to the admin as is)."""


# ------------------------------------------------------------------ time helpers


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("T", " ").replace("Z", "")[:19]
    try:
        return datetime.strptime(text, _FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(_FMT)


def _local_midnight(now: datetime | None = None) -> datetime:
    local = (now or datetime.now(timezone.utc)).astimezone(TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _window(period: str, now: datetime | None = None) -> tuple[str | None, str | None, str | None]:
    """(start, prev_start, end_of_prev) as UTC stamps; None for all time."""
    days = PERIODS.get(period)
    if days is None:
        return None, None, None
    start = _local_midnight(now) - timedelta(days=days - 1)
    prev = start - timedelta(days=days)
    return _stamp(start), _stamp(prev), _stamp(start)


def _day_label(moment: datetime, now: datetime | None = None) -> str:
    local = moment.astimezone(TZ)
    today = _local_midnight(now).date()
    stamp = local.strftime("%b ") + str(local.day)
    if local.date() == today:
        return f"Today · {stamp}"
    if local.date() == today - timedelta(days=1):
        return f"Yesterday · {stamp}"
    return stamp


def _ago(moment: datetime | None, now: datetime | None = None) -> str:
    if moment is None:
        return "—"
    now = now or datetime.now(timezone.utc)
    secs = (now - moment).total_seconds()
    if secs < 120:
        return "Now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if moment.astimezone(TZ).date() == now.astimezone(TZ).date():
        return f"{int(secs // 3600)} h ago"
    if moment.astimezone(TZ).date() == now.astimezone(TZ).date() - timedelta(days=1):
        return "Yesterday"
    return _short_date(moment, now)


def _short_date(moment: datetime | None, now: datetime | None = None) -> str:
    if moment is None:
        return "—"
    local = moment.astimezone(TZ)
    now_local = (now or datetime.now(timezone.utc)).astimezone(TZ)
    out = local.strftime("%b ") + str(local.day)
    return out if local.year == now_local.year else f"{out}, {local.year}"


# ------------------------------------------------------------------ users and flags


def _user_rows(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT u.id, u.email, u.name, u.is_admin, u.created_at, u.ip_address, u.device_fingerprint,
               u.is_blocked, u.account_flag, u.flag_cleared, u.welcome_bonus_granted,
               COALESCE(w.balance, 0) AS balance,
               (SELECT COALESCE(SUM(t.amount), 0) FROM transactions t
                 WHERE t.user_id = u.id AND t.kind = 'debit'
                   AND t.feature NOT IN ('admin_set', 'admin_adjust', 'admin_adjustment')) AS spent,
               (SELECT MAX(a.created_at) FROM activity_log a WHERE a.user_id = u.id) AS last_at
        FROM users u LEFT JOIN wallets w ON w.user_id = u.id
        ORDER BY u.id DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _email_base(email: str) -> str:
    local, _, domain = str(email or "").lower().partition("@")
    return local.split("+", 1)[0] + "@" + domain


def _annotate(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add flag / reasons / staff to each user (in place) and return the list."""
    by_ip: dict[str, list[int]] = {}
    by_fp: dict[str, list[int]] = {}
    by_base: dict[str, list[int]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for u in users:
        ip = str(u.get("ip_address") or "").strip()
        if ip not in _LOOPBACK:
            by_ip.setdefault(ip, []).append(u["id"])
        if u.get("device_fingerprint"):
            by_fp.setdefault(u["device_fingerprint"], []).append(u["id"])
        by_base.setdefault(_email_base(u["email"]), []).append(u["id"])
        name = str(u.get("name") or "").strip().lower()
        if len(name) >= 2:
            by_name.setdefault(name, []).append(u)

    def others(ids: list[int], me: int) -> str:
        rest = [f"#{i}" for i in ids if i != me][:3]
        return ", ".join(rest)

    for u in users:
        staff = bool(u.get("is_admin")) or u.get("account_flag") == "staff"
        test = u.get("account_flag") == "test"
        reasons: list[str] = []
        if not staff and not test:
            domain = extract_domain(u["email"]) or ""
            if domain and is_disposable_domain(domain):
                reasons.append(f"Disposable email domain ({domain})")
            ip = str(u.get("ip_address") or "").strip()
            if ip not in _LOOPBACK and len(by_ip.get(ip, [])) > 1:
                reasons.append(f"Same IP as {others(by_ip[ip], u['id'])}")
            fp = u.get("device_fingerprint")
            if fp and len(by_fp.get(fp, [])) > 1:
                reasons.append(f"Same device as {others(by_fp[fp], u['id'])}")
            base = _email_base(u["email"])
            if len(by_base.get(base, [])) > 1:
                reasons.append(f"Look-alike of {others(by_base[base], u['id'])} (same email before +)")
            name = str(u.get("name") or "").strip().lower()
            mine = _parse(u.get("created_at"))
            for other in by_name.get(name, []):
                theirs = _parse(other.get("created_at"))
                if other["id"] != u["id"] and mine and theirs and abs((mine - theirs).total_seconds()) <= 600:
                    mins = max(1, round(abs((mine - theirs).total_seconds()) / 60))
                    reasons.append(f"Look-alike of #{other['id']} (same name, registered {mins} min apart)")
                    break
        if u.get("is_blocked"):
            flag = "blocked"
        elif staff:
            flag = "staff"
        elif test:
            flag = "test"
        elif reasons and not u.get("flag_cleared"):
            flag = "susp"
        else:
            flag = None
        u["flag"] = flag
        u["reasons"] = reasons
        u["hidden"] = staff or test
    return users


def _hidden_ids(conn) -> set[int]:
    rows = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 OR account_flag IN ('staff', 'test')"
    ).fetchall()
    return {int(r["id"]) for r in rows}


def _client_user(u: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    joined = _parse(u.get("created_at"))
    return {
        "id": int(u["id"]),
        "name": u.get("name") or "—",
        "email": u["email"],
        "credits": int(u.get("balance") or 0),
        "spent": int(u.get("spent") or 0),
        "joined": _short_date(joined, now),
        "joinedAt": u.get("created_at"),
        "last": _ago(_parse(u.get("last_at")), now),
        "ip": u.get("ip_address") or "",
        "flag": u.get("flag"),
        "reasons": u.get("reasons") or [],
        "isAdmin": bool(u.get("is_admin")),
        "accountFlag": u.get("account_flag"),
        "blocked": bool(u.get("is_blocked")),
    }


def list_users(*, query: str = "", filter_: str = "all", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with connect() as conn:
        users = _annotate(_user_rows(conn))
    week_ago = now - timedelta(days=7)
    tests = {
        "all": lambda u: True,
        "susp": lambda u: u["flag"] == "susp",
        "staff": lambda u: u["hidden"],
        "zero": lambda u: int(u.get("balance") or 0) == 0,
        "new": lambda u: (_parse(u.get("created_at")) or now) >= week_ago,
    }
    counts = {k: sum(1 for u in users if fn(u)) for k, fn in tests.items()}
    q = (query or "").strip().lower()
    if q.startswith("#") and q[1:].isdigit():
        q = q[1:]

    def matches(u: dict[str, Any]) -> bool:
        if not q:
            return True
        hay = f"{u['email']} {u.get('name') or ''} {u.get('ip_address') or ''}".lower()
        return q in hay or q == str(u["id"])

    shown = [u for u in users if tests.get(filter_, tests["all"])(u) and matches(u)]
    staff = sum(1 for u in users if bool(u.get("is_admin")) or u.get("account_flag") == "staff")
    test = sum(1 for u in users if u.get("account_flag") == "test" and not u.get("is_admin"))
    return {
        "users": [_client_user(u, now) for u in shown[offset:offset + limit]],
        "total": len(shown),
        "offset": offset,
        "limit": limit,
        "counts": counts,
        "totals": {"all": len(users), "real": len(users) - staff - test, "staff": staff, "test": test},
    }


def users_csv() -> str:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        users = _annotate(_user_rows(conn))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "email", "name", "credits", "spent", "joined", "last_active", "flag", "reasons"])
    for u in users:
        writer.writerow([u["id"], u["email"], u.get("name") or "", int(u.get("balance") or 0),
                         int(u.get("spent") or 0), u.get("created_at") or "", u.get("last_at") or "",
                         u.get("flag") or "", "; ".join(u.get("reasons") or [])])
    return out.getvalue()


def _find_user(conn, user_id: int) -> dict[str, Any]:
    users = _annotate(_user_rows(conn))
    for u in users:
        if int(u["id"]) == int(user_id):
            return u
    raise AdminPanelError("User not found.")


def user_detail(user_id: int) -> dict[str, Any]:
    from .plans import payment_history

    now = datetime.now(timezone.utc)
    with connect() as conn:
        u = _find_user(conn, user_id)
        tx = conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 30", (int(user_id),)
        ).fetchall()
        ensure_activity_schema(conn)
        checkout_opens = conn.execute(
            "SELECT COUNT(*) AS c FROM activity_log WHERE user_id = ? AND path = '/api/payments/create'",
            (int(user_id),),
        ).fetchone()["c"]
    payments = payment_history(int(user_id), limit=30)
    paid = [p for p in payments if str(p.get("status") or "").lower() == "paid"]
    ledger = []
    for row in tx:
        signed = int(row["amount"]) * (-1 if row["kind"] == "debit" else 1)
        feature = str(row["feature"] or "")
        if feature in ADMIN_FEATURES:
            label = "Admin adjustment"
        elif row["kind"] == "refund":
            label = f"{FEATURE_LABELS.get(feature, feature.title())} refund"
        else:
            label = FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize())
        at = _parse(row["created_at"])
        ledger.append({
            "label": label,
            "when": f"{_short_date(at, now)}, {at.astimezone(TZ).strftime('%H:%M')}" if at else "",
            "amount": signed,
            "balance": int(row["balance_after"] or 0),
        })
    return {
        "user": _client_user(u, now),
        "paidUsd": round(sum(float(p.get("amount") or 0) for p in paid), 2),
        "purchases": [{"date": p.get("date"), "item": p.get("item"), "amount": p.get("amount"),
                       "status": p.get("status")} for p in payments],
        "checkoutOpens": int(checkout_opens),
        "ledger": ledger,
    }


# ------------------------------------------------------------------ account actions


def adjust_credits(user_id: int, delta: int, *, reason: str, admin_id: int) -> dict[str, Any]:
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise AdminPanelError("Amount must be a non-zero whole number.")
    if abs(delta) > 1_000_000:
        raise AdminPanelError("Amount is too large.")
    wallet = WalletService()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (int(user_id),)).fetchone() is None:
            raise AdminPanelError("User not found.")
    meta = {"admin_id": int(admin_id), "reason": (reason or "").strip()[:200] or "Admin adjustment"}
    if delta > 0:
        tx = wallet.credit(int(user_id), delta, "admin_adjust", meta=meta)
    else:
        amount = min(-delta, wallet.get_balance(int(user_id)))
        if amount <= 0:
            raise AdminPanelError("The balance is already 0.")
        tx = wallet.debit(int(user_id), amount, "admin_adjust", meta=meta)
    return {"userId": int(user_id), "balance": int(tx["balance_after"]), "delta": int(tx["credits"])}


def _guard_target(conn, user_id: int, admin_id: int) -> Any:
    row = conn.execute("SELECT id, email, is_admin FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if row is None:
        raise AdminPanelError("User not found.")
    if int(user_id) == int(admin_id):
        raise AdminPanelError("You cannot do this to your own account.")
    if int(row["is_admin"]):
        raise AdminPanelError("Remove admin access first.")
    return row


def set_blocked(user_id: int, blocked: bool, *, admin_id: int, remove_bonus: bool = False) -> dict[str, Any]:
    with connect() as conn:
        row = _guard_target(conn, user_id, admin_id) if blocked else conn.execute(
            "SELECT id, email FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None:
            raise AdminPanelError("User not found.")
        bonus = conn.execute("SELECT welcome_bonus_granted FROM users WHERE id = ?", (int(user_id),)).fetchone()
        conn.execute("UPDATE users SET is_blocked = ? WHERE id = ?", (1 if blocked else 0, int(user_id)))
    removed = 0
    if blocked and remove_bonus and bonus and int(bonus["welcome_bonus_granted"] or 0):
        wallet = WalletService()
        removed = min(int(WELCOME_BONUS), wallet.get_balance(int(user_id)))
        if removed > 0:
            wallet.debit(int(user_id), removed, "admin_adjust",
                         meta={"admin_id": int(admin_id), "reason": "Welcome bonus removed (blocked)"})
    log_activity(
        "admin.user_blocked" if blocked else "admin.user_unblocked",
        category="admin",
        user_id=int(user_id),
        user_email=row["email"],
        actor_id=int(admin_id),
        summary=f"{'Blocked' if blocked else 'Unblocked'} #{user_id} {row['email']}"
                + (f" · −{removed} bonus credits" if removed else ""),
    )
    return {"userId": int(user_id), "blocked": bool(blocked), "bonusRemoved": removed,
            "balance": WalletService().get_balance(int(user_id))}


def block_many(ids: Iterable[int], *, admin_id: int, remove_bonus: bool = True) -> dict[str, Any]:
    done, skipped = [], []
    for uid in ids:
        try:
            set_blocked(int(uid), True, admin_id=admin_id, remove_bonus=remove_bonus)
            done.append(int(uid))
        except (AdminPanelError, ValueError, TypeError):
            skipped.append(uid)
    return {"blocked": done, "skipped": skipped}


def set_account_flag(user_id: int, flag: str | None, *, admin_id: int) -> dict[str, Any]:
    flag = (flag or "").strip().lower() or None
    if flag is not None and flag not in FLAGS:
        raise AdminPanelError("Flag must be staff, test or empty.")
    with connect() as conn:
        row = conn.execute("SELECT id, email FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None:
            raise AdminPanelError("User not found.")
        conn.execute("UPDATE users SET account_flag = ? WHERE id = ?", (flag, int(user_id)))
    log_activity("admin.account_flag", category="admin", user_id=int(user_id), user_email=row["email"],
                 actor_id=int(admin_id), summary=f"Marked #{user_id} as {flag or 'regular user'}")
    return {"userId": int(user_id), "accountFlag": flag}


def set_flag_cleared(user_id: int, cleared: bool, *, admin_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT id, email FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if row is None:
            raise AdminPanelError("User not found.")
        conn.execute("UPDATE users SET flag_cleared = ? WHERE id = ?", (1 if cleared else 0, int(user_id)))
    log_activity("admin.flag_cleared", category="admin", user_id=int(user_id), user_email=row["email"],
                 actor_id=int(admin_id),
                 summary=f"{'Cleared' if cleared else 'Restored'} the suspicious flag on #{user_id}")
    return {"userId": int(user_id), "cleared": bool(cleared)}


# ------------------------------------------------------------------ overview


def _not_in(column: str, ids: set[int]) -> tuple[str, list[int]]:
    if not ids:
        return "", []
    return f" AND ({column} IS NULL OR {column} NOT IN ({','.join('?' * len(ids))}))", sorted(ids)


def _range(column: str, start: str | None, end: str | None) -> tuple[str, list[str]]:
    sql, params = "", []
    if start:
        sql += f" AND {column} >= ?"
        params.append(start)
    if end:
        sql += f" AND {column} < ?"
        params.append(end)
    return sql, params


def _paid_rows(conn) -> list[tuple[int | None, str | None, float]]:
    """(user_id, paid_at, usd) for every paid purchase across providers."""
    out: list[tuple[int | None, str | None, float]] = []
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    queries = {
        "cryptomus_payments": "SELECT user_id, COALESCE(paid_at, created_at) AS at, amount AS usd, status FROM cryptomus_payments",
        "paddle_purchases": "SELECT user_id, created_at AS at, amount AS usd, status FROM paddle_purchases",
        "gumroad_payments": "SELECT user_id, COALESCE(paid_at, created_at) AS at, price_cents / 100.0 AS usd, status FROM gumroad_payments",
        "lemon_squeezy_payments": "SELECT user_id, COALESCE(paid_at, created_at) AS at, "
                                  "COALESCE(json_extract(payload_json, '$.data.attributes.total_usd'), 0) / 100.0 AS usd, status "
                                  "FROM lemon_squeezy_payments",
    }
    for table, sql in queries.items():
        if table not in tables:
            continue
        try:
            for r in conn.execute(sql):
                if str(r["status"] or "").lower() == "paid":
                    out.append((r["user_id"], r["at"], float(r["usd"] or 0)))
        except Exception:  # noqa: BLE001
            continue
    return out


def _in_window(at: str | None, start: str | None, end: str | None) -> bool:
    moment = _parse(at)
    if moment is None:
        return start is None
    return (start is None or moment >= _parse(start)) and (end is None or moment < _parse(end))


def _change(cur: float, prev: float, period: str, *, pct: bool = False) -> tuple[str, int]:
    label = _PREV_LABEL[period]
    if cur == prev:
        return (f"Same as {label}" if period == "today" else f"Same as {label}"), 0
    if pct:
        if prev == 0:
            return f"+{int(cur):,} vs {label}", 1
        change = round((cur - prev) / prev * 100)
        return f"{'+' if change > 0 else '−'}{abs(change)}% vs {label}", 1 if change > 0 else -1
    diff = int(cur - prev)
    return f"{'+' if diff > 0 else '−'}{abs(diff):,} vs {label}", 1 if diff > 0 else -1


def _fmt_int(n: float) -> str:
    return f"{int(n):,}"


def _money(n: float) -> str:
    return f"${n:,.2f}".replace(".00", "")


def _period_kpis(conn, period: str, hidden: set[int], paid: list) -> dict[str, Any]:
    start, prev_start, prev_end = _window(period)

    def counts(excl: set[int], s: str | None, e: str | None) -> dict[str, float]:
        out: dict[str, float] = {}
        f_sql, f_par = _not_in("id", excl)
        r_sql, r_par = _range("created_at", s, e)
        out["signups"] = conn.execute(f"SELECT COUNT(*) AS c FROM users WHERE 1=1{f_sql}{r_sql}",
                                      [*f_par, *r_par]).fetchone()["c"]
        f_sql, f_par = _not_in("user_id", excl)
        out["active"] = conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS c FROM activity_log WHERE user_id IS NOT NULL "
            f"AND action NOT LIKE 'admin.%' AND action NOT LIKE 'wallet.admin%'{f_sql}{r_sql}",
            [*f_par, *r_par]).fetchone()["c"]
        used = conn.execute(
            "SELECT COALESCE(SUM(CASE kind WHEN 'debit' THEN amount WHEN 'refund' THEN -amount ELSE 0 END), 0) AS c "
            "FROM transactions WHERE feature NOT IN ('admin_set', 'admin_adjust', 'admin_adjustment')"
            f"{f_sql}{r_sql}", [*f_par, *r_par]).fetchone()["c"]
        out["used"] = max(0, int(used or 0))
        rows = [p for p in paid if (p[0] not in excl) and _in_window(p[1], s, e)]
        out["revenue"] = sum(p[2] for p in rows)
        out["purchases"] = len(rows)
        out["checkouts"] = conn.execute(
            f"SELECT COUNT(*) AS c FROM activity_log WHERE path = '/api/payments/create'{f_sql}{r_sql}",
            [*f_par, *r_par]).fetchone()["c"]
        return out

    real, everyone = counts(hidden, start, None), counts(set(), start, None)
    if period == "all":
        users_total = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        real_users = users_total - len(hidden)
        ever_real, ever_all = real["active"], everyone["active"]
        k = [
            ["Real users", _fmt_int(real_users), _fmt_int(users_total),
             f"{len(hidden)} staff & test hidden", 0],
            ["Ever active", _fmt_int(ever_real), _fmt_int(ever_all),
             f"{round(ever_real / real_users * 100) if real_users else 0}% of real users", 0],
            ["Credits used", _fmt_int(real["used"]), _fmt_int(everyone["used"]),
             f"~{round(real['used'] / real_users) if real_users else 0} per real user", 0],
        ]
    else:
        prev = counts(hidden, prev_start, prev_end)
        k = [
            ["New sign-ups", _fmt_int(real["signups"]), _fmt_int(everyone["signups"]), *_change(real["signups"], prev["signups"], period)],
            ["Active users", _fmt_int(real["active"]), _fmt_int(everyone["active"]), *_change(real["active"], prev["active"], period)],
            ["Credits used", _fmt_int(real["used"]), _fmt_int(everyone["used"]), *_change(real["used"], prev["used"], period, pct=True)],
        ]
    any_paid = any(p[0] not in hidden for p in paid)
    rev_note = (f"{real['purchases']} purchase{'s' if real['purchases'] != 1 else ''}" if real["purchases"]
                else "No purchases in this period" if any_paid else "No purchases yet")
    k.append(["Revenue", _money(real["revenue"]), _money(everyone["revenue"]), rev_note, 1 if real["purchases"] else 0])
    k.append(["Checkout opens", _fmt_int(real["checkouts"]), _fmt_int(everyone["checkouts"]),
              f"{real['purchases']} completed", -1 if real["checkouts"] and not real["purchases"] else 0])

    def features(excl: set[int]) -> list[list[Any]]:
        f_sql, f_par = _not_in("user_id", excl)
        r_sql, r_par = _range("created_at", start, None)
        rows = conn.execute(
            f"SELECT feature, COUNT(*) AS c FROM transactions WHERE kind = 'debit'{f_sql}{r_sql} GROUP BY feature",
            [*f_par, *r_par]).fetchall()
        by_feature = {str(r["feature"]): int(r["c"]) for r in rows}
        formatting = conn.execute(
            "SELECT COUNT(*) AS c FROM activity_log WHERE category = 'formatter' AND action = 'request.download'"
            f"{f_sql}{r_sql}", [*f_par, *r_par]).fetchone()["c"]
        out = []
        for label, keys in USAGE_FEATURES:
            n = int(formatting) if label == "Formatting" else sum(by_feature.get(key, 0) for key in keys)
            if label == "Veil" and not n:
                continue
            out.append([label, n])
        return out

    return {"label": PERIOD_LABELS[period], "k": k, "f": [features(hidden), features(set())]}


def _feed_alerts(conn, settings: dict[str, Any], susp: int, now: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pool = int(settings.get("turnitin_global_balance") or 0)
    if pool <= 0:
        out.append({"level": "red", "title": "Turnitin pool is empty — AI checks fail for everyone",
                    "text": "0 checks left. Top it up in Settings.", "cta": "Top up pool",
                    "to": "admin-settings", "anchor": "adm-limits"})
    elif pool < 50:
        out.append({"level": "amber", "title": f"Turnitin pool is running low — {pool} checks left",
                    "text": "AI checks stop when it reaches 0.", "cta": "Top up pool",
                    "to": "admin-settings", "anchor": "adm-limits"})
    today = _stamp(_local_midnight(now))
    errs = conn.execute(
        "SELECT created_at, status_code, user_id FROM activity_log WHERE category = 'humanizer' "
        "AND status_code >= 400 AND created_at >= ? ORDER BY created_at DESC", (today,)).fetchall()
    if errs:
        last = errs[0]
        at = _parse(last["created_at"])
        who = f"#{last['user_id']}" if last["user_id"] else "A guest"
        out.append({"level": "amber", "title": f"{len(errs)} Humanizer error{'s' if len(errs) > 1 else ''} today",
                    "text": f"{who} got “{_status_text(last['status_code'])}” at {at.astimezone(TZ).strftime('%H:%M') if at else '—'}. "
                            "Users saw an error instead of a result.",
                    "cta": "See errors", "to": "admin-activity", "cat": "error"})
    if susp:
        out.append({"level": "amber", "title": f"{susp} suspicious account{'s' if susp > 1 else ''}",
                    "text": "Disposable emails, shared IPs or look-alike sign-ups collecting the welcome bonus.",
                    "cta": "Review", "to": "admin-users", "filter": "susp"})
    pending = 0
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='withdrawal_requests'").fetchone():
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM withdrawal_requests WHERE LOWER(status) = 'pending'").fetchone()["c"]
    if pending:
        out.append({"level": "amber", "title": f"{pending} withdrawal request{'s' if pending > 1 else ''} waiting",
                    "text": "Referral payouts need your approval.", "cta": "Open withdrawals", "href": "/admin#withdrawals"})
    return out


def _status_text(code: Any) -> str:
    try:
        return f"{int(code)} {HTTPStatus(int(code)).phrase}"
    except (ValueError, TypeError):
        return str(code or "error")


def overview() -> dict[str, Any]:
    from .site_settings import get_admin_dashboard_stats

    now = datetime.now(timezone.utc)
    dash = get_admin_dashboard_stats()
    settings = dash.get("settings") or {}
    with connect() as conn:
        ensure_activity_schema(conn)
        users = _annotate(_user_rows(conn))
        hidden = {int(u["id"]) for u in users if u["hidden"]}
        paid = _paid_rows(conn)
        periods = {p: _period_kpis(conn, p, hidden, paid) for p in PERIODS}
        susp = sum(1 for u in users if u["flag"] == "susp")
        alerts = _feed_alerts(conn, settings, susp, now)
        f_sql, f_par = _not_in("user_id", hidden)
        used_all = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS c FROM transactions WHERE kind = 'debit' "
            "AND feature NOT IN ('admin_set', 'admin_adjust', 'admin_adjustment')").fetchone()["c"]
        used_real = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS c FROM transactions WHERE kind = 'debit' "
            f"AND feature NOT IN ('admin_set', 'admin_adjust', 'admin_adjustment'){f_sql}", f_par).fetchone()["c"]
        pending = 0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='withdrawal_requests'").fetchone():
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM withdrawal_requests WHERE LOWER(status) = 'pending'").fetchone()["c"]
    staff = sum(1 for u in users if u.get("is_admin") or u.get("account_flag") == "staff")
    test = sum(1 for u in users if u.get("account_flag") == "test" and not u.get("is_admin"))
    share = round((used_all - used_real) / used_all * 100) if used_all else 0
    latest = [e for e in activity_feed(hide_bots=True, hide_staff=True, limit=5)["events"]]
    return {
        "periods": periods,
        "alerts": alerts,
        "hiddenNote": {"staff": staff, "test": test, "share": share},
        "withdrawalsPending": int(pending),
        "today": dash.get("today") or {},
        "settings": settings,
        "discount": dash.get("discount") or {},
        "totals": {"all": len(users), "suspicious": susp},
        "latest": [[e["time"] if e["day"].startswith("Today") else e["day"].split(" · ")[-1],
                    e["text"] + (f" · {e['amt']} credits" if e["amt"] and e["amt"] not in ("free",) else ""),
                    e["user"]] for e in latest],
    }


# ------------------------------------------------------------------ activity feed


def _wallet_amount(details: dict[str, Any]) -> str:
    credits = int(details.get("credits") or 0)
    if credits > 0:
        return f"+{credits:,}"
    if credits < 0:
        return f"−{abs(credits):,}"
    return ""


def _map_event(row: Any, hidden: set[int]) -> dict[str, Any] | None:
    import json

    action = str(row["action"] or "")
    category = str(row["category"] or "")
    status = int(row["status_code"] or 0)
    path = str(row["path"] or "")
    method = str(row["method"] or "")
    uid = row["user_id"]
    try:
        details = json.loads(row["details_json"]) if row["details_json"] else {}
    except (TypeError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    summary = str(row["summary"] or "")
    cat, text, sub, amt, bot = "credits", summary, "", "", False

    admin_wallet = action.startswith("wallet.") and (
        action.startswith("wallet.admin") or str(details.get("feature") or "") in ADMIN_FEATURES)
    if admin_wallet or action.startswith("admin."):
        cat = "admin"
        if action.startswith("wallet."):
            text = f"Credits {_wallet_amount(details)} by admin"
            sub = str(details.get("reason") or "")
            actor = row["actor_id"]
            if actor:
                sub = (sub + " · " if sub else "") + f"by #{actor}"
        else:
            text = summary or action.split(".", 1)[-1].replace("_", " ").capitalize()
    elif action == "auth.login_failed":
        cat, text, sub = "error", "Sign-in failed", "Wrong email or password"
    elif action.startswith("auth.") or action == "user.register":
        cat = "auth"
        text = {"auth.login": "Signed in", "auth.logout": "Signed out", "user.register": "New account"}.get(
            action, summary or action.split(".", 1)[-1].replace("_", " ").capitalize())
    elif action.startswith("wallet."):
        feature = str(details.get("feature") or "")
        label = FEATURE_LABELS.get(feature, feature.replace("_", " ").capitalize() or "Credits")
        text = f"{label} refund" if action == "wallet.refund" else label
        amt = _wallet_amount(details)
    elif action.startswith("request."):
        is_scan = bool(_SCANNER_RE.search(path))
        if uid is None and (status in (404, 405) or is_scan):
            cat, bot, text, sub = "bot", True, "Bot request blocked", f"{method} {path}"[:120]
        elif status >= 400:
            label = CATEGORY_LABELS.get(category, "Request")
            cat, text, sub = "error", f"{label} failed", _status_text(status)
        elif action == "request.download":
            label = CATEGORY_LABELS.get(category, "File")
            text, amt = f"{label} · file downloaded", "free" if category == "formatter" else ""
        else:
            return None
    else:
        cat = "auth" if category == "account" else "credits"
        text = summary or action

    at = _parse(row["created_at"])
    raw = summary if action.startswith("request.") else f"{action}{' · ' + summary if summary else ''}"
    return {
        "id": int(row["id"]),
        "at": at,
        "cat": cat,
        "text": text[:160],
        "sub": sub[:200],
        "amt": amt,
        "user": f"#{uid}" if uid else ("—" if bot else "Guest"),
        "email": row["user_email"] or "",
        "staff": bool(uid and int(uid) in hidden),
        "bot": bot,
        "raw": raw[:300] or action,
        "ip": row["ip"] or "",
    }


def _sum_amounts(a: str, b: str) -> str:
    def num(s: str) -> int | None:
        if not s or s == "free":
            return None
        try:
            return int(s.replace("−", "-").replace("+", "").replace(",", ""))
        except ValueError:
            return None
    x, y = num(a), num(b)
    if x is None or y is None:
        return a
    total = x + y
    return f"+{total:,}" if total > 0 else f"−{abs(total):,}" if total < 0 else "0"


def activity_feed(*, category: str = "all", query: str = "", hide_bots: bool = True, hide_staff: bool = True,
                  limit: int = 60, offset: int = 0) -> dict[str, Any]:
    """Grouped, human-readable events, newest first. ``offset`` counts raw ledger rows."""
    now = datetime.now(timezone.utc)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    clauses, params = [], []
    q = (query or "").strip().lower()
    if q:
        if q.startswith("#") and q[1:].isdigit():
            clauses.append("user_id = ?")
            params.append(int(q[1:]))
        else:
            like = f"%{q}%"
            clauses.append("(LOWER(COALESCE(user_email, '')) LIKE ? OR COALESCE(ip, '') LIKE ? "
                           "OR LOWER(COALESCE(summary, '')) LIKE ? OR LOWER(COALESCE(path, '')) LIKE ? "
                           "OR CAST(user_id AS TEXT) = ?)")
            params.extend([like, like, like, like, q])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    events: list[dict[str, Any]] = []
    hidden_bots = 0
    errors_today = 0
    today = _local_midnight(now)
    scanned = offset
    batch = 400
    with connect() as conn:
        ensure_activity_schema(conn)
        hidden = _hidden_ids(conn)
        exhausted = False
        while len(events) < limit and not exhausted:
            rows = conn.execute(
                f"SELECT * FROM activity_log {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*params, batch, scanned]).fetchall()
            if len(rows) < batch:
                exhausted = True
            for row in rows:
                scanned += 1
                ev = _map_event(row, hidden)
                if ev is None:
                    continue
                if ev["cat"] == "error" and ev["at"] and ev["at"] >= today:
                    errors_today += 1
                if hide_bots and ev["bot"]:
                    hidden_bots += 1
                    continue
                if hide_staff and ev["staff"]:
                    continue
                if category != "all" and ev["cat"] != category:
                    continue
                prev = events[-1] if events else None
                ev_day = _day_label(ev["at"], now) if ev["at"] else ""
                if (prev and prev["day"] == ev_day and prev["cat"] == ev["cat"] and prev["text"] == ev["text"]
                        and prev["sub"] == ev["sub"] and prev["user"] == ev["user"]):
                    prev["times"] += 1
                    prev["amt"] = _sum_amounts(prev["amt"], ev["amt"])
                    continue
                if len(events) >= limit:
                    scanned -= 1
                    break
                ev["day"] = ev_day
                ev["time"] = ev["at"].astimezone(TZ).strftime("%H:%M") if ev["at"] else ""
                ev["date"] = ev["at"].astimezone(TZ).strftime("%b %d, %Y") if ev["at"] else ""
                ev["times"] = 1
                events.append(ev)
            if not rows:
                break
        more = conn.execute(
            f"SELECT 1 FROM activity_log {where} ORDER BY created_at DESC, id DESC LIMIT 1 OFFSET ?",
            [*params, scanned]).fetchone() is not None
    for ev in events:
        ev.pop("at", None)
    return {
        "events": events,
        "nextOffset": scanned if more else None,
        "hiddenBots": hidden_bots,
        "errorsToday": errors_today,
    }
