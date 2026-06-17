import re
import secrets
import string
import unicodedata


def to_ascii_handle(value: str) -> str:
    """
    Fold `value` to a URL-safe ASCII handle, keeping its existing case.

    Transliterates accents to their base letters and drops emoji and any other
    non-alphanumeric characters. It does NOT change case — the result mirrors the
    input casing (e.g. "Jön Doe" -> "JonDoe", but "jön doe" -> "jondoe").
    """
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]", "", folded)


def pad_handle(slug: str) -> str:
    """
    Pad `slug` with random digits up to an 8-char minimum and prefix a slash.

    Keeps the handle non-empty even when `slug` folded down to nothing, so the
    resulting URL path is always at least `/` + 8 characters.
    """
    if len(slug) < 8:
        slug = slug + "".join(secrets.choice(string.digits) for _ in range(8 - len(slug)))
    return f"/{slug}"
