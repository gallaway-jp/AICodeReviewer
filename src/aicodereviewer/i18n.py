# src/aicodereviewer/i18n.py
"""
Internationalisation (i18n) support for AICodeReviewer.

Provides a lightweight dictionary-based translation system supporting
English (en) and Japanese (ja).  Every user-facing string in the CLI
and GUI should be routed through :func:`t`.

Usage::

    from aicodereviewer.i18n import t, set_locale, get_locale

    set_locale("ja")
    print(t("cli.ready"))  # → "準備完了"

Keys use dotted notation: ``module.context.identifier``.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

# ── thread-safe global locale ──────────────────────────────────────────────

_lock = threading.Lock()
_locale: str = "en"


def set_locale(lang: str) -> None:
    """Set the active locale (``'en'`` or ``'ja'``)."""
    global _locale
    with _lock:
        _locale = lang if lang in _STRINGS else "en"


def get_locale() -> str:
    """Return the current locale code."""
    with _lock:
        return _locale


def t(key: str, lang: Optional[str] = None, **kwargs: Any) -> str:
    """
    Look up a translated string.

    Args:
        key: Dotted translation key (e.g. ``'gui.tab.review'``).
        lang: Override locale for this call only.
        **kwargs: Format placeholders (``{name}``-style).

    Returns:
        The translated string, or the key itself if not found.
    """
    locale = lang or get_locale()
    table = _STRINGS.get(locale, _STRINGS["en"])
    text = table.get(key)
    if text is None:
        # Fallback to English, then to the raw key
        text = _STRINGS["en"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# ═══════════════════════════════════════════════════════════════════════════
#  String tables – loaded from per-language modules in lang/
# ═══════════════════════════════════════════════════════════════════════════

from .lang.en import STRINGS as _EN
from .lang.ja import STRINGS as _JA

_STRINGS: dict[str, dict[str, str]] = {
    "en": _EN,
    "ja": _JA,
}
