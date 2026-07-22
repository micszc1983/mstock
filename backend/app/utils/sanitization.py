from __future__ import annotations

import re
from collections.abc import Iterable


_SECRET_PARAMETER_RE = re.compile(
    r"(?i)(\b(?:api[ _-]?key|apikey|api_token|access_token|x-rapidapi-key|authorization)"
    r"\b\s*(?:=|:|\bas\b)\s*)([^&\s,;\"'}]+)"
)


def redact_sensitive_text(value: object, secrets: Iterable[str] = ()) -> str:
    """Usuwa tokeny z komunikatów providerów przed logowaniem lub zwrotem API."""
    text = str(value)
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return _SECRET_PARAMETER_RE.sub(r"\1***", text)
