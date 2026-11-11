"""Ed25519 signing and verification for evidence content (RFC 8032).

Uses the maintained ``cryptography`` library.  Two key roles exist:

- the **gateway key** signs every chain event and the package manifest,
- the **checkpoint key** (held by the independent checkpoint store under
  audit-team control) signs execution start records and final checkpoints.

Key identity is content-derived (``ed25519:<16 hex>`` of the SHA-256 of
the raw public key), so a key registry can list current and historical
gateway keys without coordination.
"""

from __future__ import annotations

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

__all__ = [
    "ALGORITHM",
    "SignatureError",
    "EvidenceSigner",
    "key_id_for_public_key",
    "key_id_for_public_pem",
    "load_public_key",
    "verify_signature",
]

ALGORITHM = "ed25519"


class SignatureError(ValueError):
    """Raised when a signature is malformed or fails verification."""


def _public_key_bytes(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def key_id_for_public_key(public_key: Ed25519PublicKey) -> str:
    """Stable content-derived key id: ``ed25519:<first 16 hex of sha256>``."""
    digest = hashlib.sha256(_public_key_bytes(public_key)).hexdigest()
    return f"{ALGORITHM}:{digest[:16]}"


def load_public_key(pem: bytes | str) -> Ed25519PublicKey:
    """Load an Ed25519 public key from PEM bytes (registry files store PEM)."""
    if isinstance(pem, str):
        pem = pem.encode("utf-8")
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError(f"expected an Ed25519 public key, got {type(key).__name__}")
    return key


def key_id_for_public_pem(pem: bytes | str) -> str:
    """Key id for a PEM-encoded public key."""
    return key_id_for_public_key(load_public_key(pem))


def verify_signature(public_pem: bytes | str, payload: bytes, signature_hex: str) -> bool:
    """Verify an Ed25519 signature (hex) over *payload*; never raises."""
    try:
        verify_signature_or_raise(public_pem, payload, signature_hex)
    except SignatureError:
        return False
    return True


def verify_signature_or_raise(public_pem: bytes | str, payload: bytes, signature_hex: str) -> None:
    """Verify and raise :class:`SignatureError` on any failure."""
    public_key = load_public_key(public_pem)
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise SignatureError(f"signature is not valid hex: {exc}") from exc
    if not signature:
        raise SignatureError("signature is empty")
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise SignatureError("signature verification failed") from exc


class EvidenceSigner:
    """Holder of one Ed25519 private key (gateway or checkpoint role)."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key

    @classmethod
    def generate(cls) -> EvidenceSigner:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_pem(cls, pem: bytes, password: bytes | None = None) -> EvidenceSigner:
        key = serialization.load_pem_private_key(pem, password=password)
        if not isinstance(key, Ed25519PrivateKey):
            raise SignatureError(f"expected an Ed25519 private key, got {type(key).__name__}")
        return cls(key)

    @property
    def key_id(self) -> str:
        return key_id_for_public_key(self._private_key.public_key())

    def public_pem(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def private_pem(self, password: bytes | None = None) -> bytes:
        """Serialize the private key; callers are responsible for file permissions."""
        if password is None:
            return self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password),
        )

    def sign(self, payload: bytes) -> str:
        """Sign *payload* and return the signature as hex."""
        return self._private_key.sign(payload).hex()
