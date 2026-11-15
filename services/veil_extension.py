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
_INSTALL_TXT = """How to add Veil to Chrome
=========================

You only need the Veil folder. Do not open the files inside it.

1. Keep the Veil folder somewhere safe. Do not delete it.
2. In Chrome, open:  chrome://extensions
3. Turn on Developer mode (top right).
4. Click Load unpacked.
5. Select the Veil folder. Stop there — do not click into it.
6. Pin Veil, open it, and sign in.

Then on any page:
- Select a question and press Control+Q (Windows: Alt+Q) to ask.
- Press Control+S (Windows: Alt+S) to crop a formula or diagram.
- Select your own text and press Control+H to humanize it.

Install once. Chrome runs Veil from that folder.
"""


def pack_extension(api_base: str) -> bytes:
    """Zip the extension with its API address set to the site the visitor is on."""
    origin = api_base.strip().rstrip("/")
    if not origin.startswith(("https://", "http://")):
        raise ValueError("api_base must be an http(s) origin")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Two top-level items so unzip/7-Zip does not dump .js files in the user's face.
        archive.writestr("How to install.txt", _INSTALL_TXT.encode("utf-8"))
        for name in _FILES:
            data = (_ROOT / name).read_bytes()
            if name.endswith(".js"):
                text = data.decode("utf-8")
                if name == "background.js" and _API_PLACEHOLDER not in text:
                    raise ValueError("background.js is missing the API placeholder")
                data = text.replace(_API_PLACEHOLDER, origin).encode("utf-8")
            archive.writestr(f"Veil/{name}", data)
    return buf.getvalue()
