"""Ed25519 signing contract tests."""

import pytest

from evidence.signing import (
    EvidenceSigner,
    SignatureError,
    key_id_for_public_pem,
    verify_signature,
    verify_signature_or_raise,
)


@pytest.fixture(scope="module")
def signer() -> EvidenceSigner:
    return EvidenceSigner.generate()


class TestKeyIdentity:
    def test_key_id_format(self, signer):
        assert signer.key_id.startswith("ed25519:")
        assert len(signer.key_id) == len("ed25519:") + 16

    def test_key_id_stable_for_same_key(self):
        key = EvidenceSigner.generate()
        assert key.key_id == EvidenceSigner.from_pem(key.private_pem()).key_id

    def test_different_keys_have_different_ids(self):
        assert EvidenceSigner.generate().key_id != EvidenceSigner.generate().key_id

    def test_key_id_from_public_pem_matches_signer(self, signer):
        assert key_id_for_public_pem(signer.public_pem()) == signer.key_id


class TestSignVerify:
    def test_roundtrip(self, signer):
        payload = b'{"a":1}'
        signature = signer.sign(payload)
        assert verify_signature(signer.public_pem(), payload, signature)

    def test_tampered_payload_fails(self, signer):
        signature = signer.sign(b'{"a":1}')
        assert not verify_signature(signer.public_pem(), b'{"a":2}', signature)

    def test_tampered_signature_fails(self, signer):
        payload = b"payload"
        signature = signer.sign(payload)
        flipped = ("f" if signature[0] != "f" else "0") + signature[1:]
        assert not verify_signature(signer.public_pem(), payload, flipped)

    def test_wrong_key_fails(self, signer):
        other = EvidenceSigner.generate()
        signature = signer.sign(b"payload")
        assert not verify_signature(other.public_pem(), b"payload", signature)

    def test_non_hex_signature_raises(self, signer):
        with pytest.raises(SignatureError):
            verify_signature_or_raise(signer.public_pem(), b"payload", "zz-not-hex")

    def test_empty_signature_raises(self, signer):
        with pytest.raises(SignatureError):
            verify_signature_or_raise(signer.public_pem(), b"payload", "")

    def test_verify_never_raises(self, signer):
        assert verify_signature(signer.public_pem(), b"payload", "deadbeef") is False


class TestSerialization:
    def test_private_pem_roundtrip(self, signer):
        restored = EvidenceSigner.from_pem(signer.private_pem())
        payload = b"same payload"
        assert restored.sign(payload) == signer.sign(payload)

    def test_encrypted_private_pem_roundtrip(self, signer):
        pem = signer.private_pem(password=b"secret")
        restored = EvidenceSigner.from_pem(pem, password=b"secret")
        assert restored.key_id == signer.key_id

    def test_public_pem_is_ascii_armored(self, signer):
        assert signer.public_pem().startswith(b"-----BEGIN PUBLIC KEY-----")
