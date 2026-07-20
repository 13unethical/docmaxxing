"""Economy: accounts, coin wallet, ledger and pricing.

Single source of truth for the app's virtual currency ("coins"). Everything a
user can pay for (Humanize, AI Detect, Academic Check, Cite, Turnitin,
Assignments) is charged through :class:`WalletService`, which writes an
append-only ledger row for every movement.
"""

from __future__ import annotations

from .db import DB_PATH, connect, init_db
from .pricing import (
    FEATURE_LABELS,
    TOPUP_PACKAGES,
    WELCOME_BONUS,
    assignment_cost_coins,
    feature_cost,
    package,
)
from .wallet import InsufficientCoins, WalletError, WalletService

__all__ = [
    "DB_PATH",
    "connect",
    "init_db",
    "FEATURE_LABELS",
    "TOPUP_PACKAGES",
    "WELCOME_BONUS",
    "assignment_cost_coins",
    "feature_cost",
    "package",
    "InsufficientCoins",
    "WalletError",
    "WalletService",
]
