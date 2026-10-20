"""Pack the Veil Chrome extension into a zip a visitor can install."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

# Public key baked into manifest.json. Every install gets this extension id,
# so the connect page can hand the login token to the extension.
EXTENSION_ID = "kbgjgedgiahpgngmbmbheecdkfeehkec"
_API_PLACEHOLDER = "__VEIL_API_BASE__"

_ROOT = Path(__file__).resolve().parents[1] / "chrome-extension"
_FILES = (
    "manifest.json",
    "background.js",
    "content.js",
    "popup.html",
    "popup.js",
    "icons/icon16.png",
    "icons/icon48.png",
    "icons/icon128.png",
)


def pack_extension(api_base: str) -> bytes:
    """Zip the extension with its API address set to the site the visitor is on."""
    origin = api_base.strip().rstrip("/")
    if not origin.startswith(("https://", "http://")):
        raise ValueError("api_base must be an http(s) origin")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in _FILES:
            data = (_ROOT / name).read_bytes()
            if name.endswith(".js"):
                text = data.decode("utf-8")
                if name == "background.js" and _API_PLACEHOLDER not in text:
                    raise ValueError("background.js is missing the API placeholder")
                data = text.replace(_API_PLACEHOLDER, origin).encode("utf-8")
            archive.writestr(f"Veil/{name}", data)
    return buf.getvalue()
