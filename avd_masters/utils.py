"""Shared utilities: env-var config resolution and error sanitization."""

from __future__ import annotations

import os
import re
from typing import Any

# Matches http(s)://user:pass@host or ftp://user:pass@host
_CRED_URL_RE = re.compile(r'(https?://|ftp://)[^:@\s/]+:[^@\s]+@')
# Matches   password=secret  /  "password": "secret"  / password: secret
_PASSWORD_KV_RE = re.compile(
    r'(?i)(password|passwd|secret|token|api[_-]?key|auth)\s*[=:"\s]\s*\S+',
)


def sanitize_error(exc: BaseException | str) -> str:
    """Return a safe string representation of an exception or message.

    Redacts credential-like patterns so error strings can be safely logged,
    stored in snapshot.errors, or forwarded to notifiers.
    """
    msg = str(exc)
    msg = _CRED_URL_RE.sub(r'\1***:***@', msg)
    msg = _PASSWORD_KV_RE.sub(lambda m: m.group(1) + '=***', msg)
    return msg


_ENV_RE = re.compile(r'\$\{([^}]+)\}')


def resolve_env_vars(obj: Any) -> Any:
    """Recursively replace ``${VAR}`` placeholders in config string values.

    Raises ``ValueError`` if a referenced variable is not set, so operators
    get a clear error at startup rather than passing empty strings to auth.
    """
    if isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_env_vars(item) for item in obj]
    if isinstance(obj, str):
        def _replace(match: re.Match) -> str:
            var = match.group(1)
            val = os.environ.get(var)
            if val is None:
                raise ValueError(
                    f"Config references ${{{var}}} but that environment variable is not set."
                )
            return val
        return _ENV_RE.sub(_replace, obj)
    return obj
