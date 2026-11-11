"""Canonical JSON (RFC 8785 subset) for signed evidence content.

Every hash and signature in the evidence pipeline is computed over the
canonical JSON encoding produced here, so the encoding rules are the
bottom of the trust boundary:

- Objects: keys sorted by UTF-16 code unit sequence (RFC 8785 §2.2.3).
- Strings: minimal escaping — only ``"`` ``\\`` and the control-character
  shorthands ``\\b \\f \\n \\r \\t``; everything else is raw UTF-8.
  Lone surrogates are rejected (they cannot round-trip through UTF-8).
- Numbers: integers within the IEEE-754 double-safe range
  (``-(2**53 - 1) <= n <= 2**53 - 1``).  Floats are rejected outright:
  ES6 number formatting is the hard part of full JCS, and the evidence
  schema intentionally carries no floats (timestamps are ISO-8601
  strings, durations are integer milliseconds).  Keeping floats out of
  the signed surface keeps canonicalization exactly verifiable with the
  subset implemented here.
- No whitespace anywhere; output encoding is UTF-8.

https://www.rfc-editor.org/info/rfc8785
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["CanonicalizationError", "canonical_json", "canonicalize", "sha256_hex"]

# ECMAScript Number.MAX_SAFE_INTEGER: largest integer that round-trips
# through an IEEE-754 double without ambiguity.
_MAX_SAFE_INTEGER = 2**53 - 1


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented in canonical JSON."""


def _validate(value: Any) -> None:
    """Recursively check that *value* is representable in the JCS subset."""
    if value is None or isinstance(value, bool):
        return
    # bool must be checked before int (bool is an int subclass).
    if isinstance(value, int):
        if not (-_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER):
            raise CanonicalizationError(
                f"integer {value} outside the IEEE-754 double-safe range "
                f"[{-_MAX_SAFE_INTEGER}, {_MAX_SAFE_INTEGER}]"
            )
        return
    if isinstance(value, float):
        raise CanonicalizationError(
            "floats are not representable in the signed evidence subset; "
            "use strings or integer milliseconds instead"
        )
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CanonicalizationError(f"string contains unpaired surrogates: {exc}") from exc
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(
                    f"object keys must be strings, got {type(key).__name__}"
                )
            _validate(key)
            _validate(item)
        return
    raise CanonicalizationError(f"unsupported type for canonical JSON: {type(value).__name__}")


def _utf16_code_unit_key(key: str) -> bytes:
    """Sort key implementing RFC 8785's UTF-16 code unit ordering.

    Encoding to big-endian UTF-16 turns surrogate pairs into byte
    sequences that compare exactly like code unit sequences, which
    differs from plain code-point order for astral characters
    (e.g. U+1F600 sorts *before* U+FB33 because its first code unit
    D83D is smaller than FB33, even though its code point is larger).
    """
    return key.encode("utf-16-be")


def _ordered(value: Any) -> Any:
    """Rebuild *value* with object keys inserted in canonical order."""
    if isinstance(value, dict):
        return {key: _ordered(value[key]) for key in sorted(value, key=_utf16_code_unit_key)}
    if isinstance(value, (list, tuple)):
        return [_ordered(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Return the canonical JSON text for *value* (RFC 8785 subset)."""
    _validate(value)
    return json.dumps(_ordered(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def canonicalize(value: Any) -> bytes:
    """Return the canonical JSON encoding of *value* as UTF-8 bytes."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 digest of *data* — the single hash primitive of the pipeline."""
    return hashlib.sha256(data).hexdigest()
