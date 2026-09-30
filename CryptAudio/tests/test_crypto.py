"""Unit tests for the CryptAudio cryptography module (Phase 2).

These tests verify *behaviour* only. They never print or assert on secret
material (derived keys, salts, nonces, plaintext bytes) beyond what is needed
to confirm correct round-tripping and correct failure modes.

Run from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import pytest

from crypto.aes_crypto import (
    MAGIC,
    AuthenticationError,
    EmptyMessageError,
    EmptyPasswordError,
    InvalidPayloadError,
    decrypt_message,
    encrypt_message,
)

# A password reused across tests. Fine for tests only — never hardcode a real
# password in production code.
PASSWORD = "correct-password"


# --- Test 1: basic round trip ------------------------------------------------
def test_encrypt_decrypt_roundtrip():
    """plaintext -> encrypt -> decrypt must recover the exact plaintext."""
    message = "This is a secret CryptAudio message."
    payload = encrypt_message(message, PASSWORD)

    assert isinstance(payload, bytes)
    assert payload.startswith(MAGIC)

    recovered = decrypt_message(payload, PASSWORD)
    assert recovered == message


# --- Test 2: fresh salt/nonce produce different payloads ---------------------
def test_same_message_different_payloads():
    """Encrypting the same message twice must yield different bytes."""
    message = "repeatable message"
    payload_a = encrypt_message(message, PASSWORD)
    payload_b = encrypt_message(message, PASSWORD)

    # Different random salt + nonce => different payload...
    assert payload_a != payload_b
    # ...but both still decrypt to the same plaintext.
    assert decrypt_message(payload_a, PASSWORD) == message
    assert decrypt_message(payload_b, PASSWORD) == message


# --- Test 3: wrong password fails authentication -----------------------------
def test_wrong_password_fails():
    """Decrypting with a different password must raise AuthenticationError."""
    payload = encrypt_message("secret", "password-A")

    with pytest.raises(AuthenticationError):
        decrypt_message(payload, "password-B")


# --- Test 4: tampered payload fails authentication ---------------------------
@pytest.mark.parametrize("flip_index", [0, 5, -1, -8])
def test_tampered_payload_fails(flip_index):
    """Modifying any byte of the payload must break GCM authentication."""
    payload = bytearray(encrypt_message("do not tamper with me", PASSWORD))

    # Flip a single bit in the chosen byte.
    payload[flip_index] ^= 0x01

    with pytest.raises((AuthenticationError, InvalidPayloadError)):
        # Header tampering may be caught structurally (InvalidPayloadError) or
        # by the GCM tag (AuthenticationError); either way it must NOT succeed.
        decrypt_message(bytes(payload), PASSWORD)


def test_tampered_ciphertext_body_fails():
    """Flipping a bit inside the ciphertext region must fail authentication."""
    payload = bytearray(encrypt_message("integrity matters", PASSWORD))

    # The last byte is part of the GCM tag/ciphertext region.
    payload[-1] ^= 0x01

    with pytest.raises(AuthenticationError):
        decrypt_message(bytes(payload), PASSWORD)


# --- Test 5: empty message rejected ------------------------------------------
def test_empty_message_rejected():
    """An empty plaintext must be rejected before any encryption happens."""
    with pytest.raises(EmptyMessageError):
        encrypt_message("", PASSWORD)


# --- Test 6: empty password rejected -----------------------------------------
def test_empty_password_rejected():
    """An empty password must be rejected on both encrypt and decrypt."""
    with pytest.raises(EmptyPasswordError):
        encrypt_message("message", "")

    payload = encrypt_message("message", PASSWORD)
    with pytest.raises(EmptyPasswordError):
        decrypt_message(payload, "")


# --- Test 7: invalid payload rejected ----------------------------------------
@pytest.mark.parametrize(
    "bad_payload",
    [
        b"",                              # empty
        b"not a cryptaudio payload",      # wrong magic
        b"CRYPTAU",                       # truncated magic
        MAGIC + b"\x00",                  # bad version / truncated
        b"\x00\x01\x02\x03",              # random short bytes
    ],
)
def test_invalid_payload_rejected(bad_payload):
    """Arbitrary / malformed bytes must raise InvalidPayloadError."""
    with pytest.raises(InvalidPayloadError):
        decrypt_message(bad_payload, PASSWORD)


def test_payload_not_pickle_and_is_bytes():
    """Sanity check: payload is bytes and carries the CryptAudio magic."""
    payload = encrypt_message("structure check", PASSWORD)
    assert isinstance(payload, (bytes, bytearray))
    assert bytes(payload[: len(MAGIC)]) == MAGIC


# --- Test 8: Unicode round trip ----------------------------------------------
@pytest.mark.parametrize(
    "message",
    [
        "Hello CryptAudio \U0001F510",   # emoji
        "\u0928\u092E\u0938\u094D\u0924\u0947",        # Hindi: namaste
        "\u0A97\u0AC1\u0A9C\u0AB0\u0ABE\u0AA4\u0AC0 \u0AB8\u0A82\u0AA6\u0AC7\u0AB6",  # Gujarati
        "mixed: English + \u0928\u092E\u0938\u094D\u0924\u0947 + \U0001F510",
    ],
)
def test_unicode_roundtrip(message):
    """Unicode messages must be recovered exactly (UTF-8 safe)."""
    payload = encrypt_message(message, PASSWORD)
    assert decrypt_message(payload, PASSWORD) == message
