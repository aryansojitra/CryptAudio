"""CryptAudio — password-based cryptography module (Phase 2).

This module turns a human-memorable *password* and a *secret message* into a
self-contained, authenticated, binary payload using industry-standard
primitives from the ``cryptography`` library. No cryptographic algorithm is
implemented by hand here; we deliberately rely on the audited ``cryptography``
package.

Cryptographic design
--------------------
Pipeline (encryption)::

    password + random salt ──PBKDF2-HMAC-SHA256──► 32-byte AES key
    key + random nonce ──AES-256-GCM──► ciphertext ‖ 16-byte auth tag

* **AES-256-GCM** is an *AEAD* cipher: it provides confidentiality
  (encryption) *and* authenticity/integrity (a 16-byte authentication tag).
  If the ciphertext, the tag, or the authenticated header is altered in any
  way, decryption fails instead of returning corrupted plaintext.
* **PBKDF2-HMAC-SHA256** stretches the low-entropy password into a uniform
  256-bit key. The iteration count (``PBKDF2_ITERATIONS``) makes brute-force
  attacks expensive. The password is **never** used directly as the AES key.
* A fresh **salt** (16 bytes) and a fresh **nonce** (12 bytes) are generated
  from a cryptographically secure source for *every* encryption. A GCM nonce
  is never reused with the same key.

Payload format
--------------
The payload is a deterministic, binary-safe byte string. All multi-byte
integers are big-endian (network byte order). It is intentionally *not* pickle
or any other unsafe/opaque serialization::

    Offset  Field            Size   Description
    0       MAGIC            8 B    b"CRYPTAUD" — identifies a CryptAudio payload
    8       VERSION          1 B    payload format version (0x01)
    9       KDF_ID           1 B    key-derivation id (0x01 = PBKDF2-HMAC-SHA256)
    10      KDF_ITERATIONS   4 B    uint32 — PBKDF2 iteration count used
    14      SALT_LEN         1 B    length of SALT in bytes (16)
    15      SALT             var    PBKDF2 salt
    ..      NONCE_LEN        1 B    length of NONCE in bytes (12)
    ..      NONCE            var    AES-GCM nonce
    ..      CT_LEN           4 B    uint32 — length of CIPHERTEXT (incl. tag)
    ..      CIPHERTEXT       var    AES-GCM ciphertext + 16-byte auth tag

Everything from MAGIC up to and including NONCE forms the **header**. The
header is passed to AES-GCM as *Additional Authenticated Data* (AAD), so its
integrity is protected by the authentication tag even though it is not
encrypted (salt/nonce/parameters are not secret).

The password is **never** stored in the payload.

Error handling
--------------
This module raises clear, project-specific exceptions instead of leaking
low-level errors:

* :class:`EmptyMessageError`  — plaintext message is empty.
* :class:`EmptyPasswordError` — password is empty.
* :class:`InvalidPayloadError` — bytes are not a well-formed CryptAudio payload.
* :class:`AuthenticationError` — wrong password or tampered data (GCM tag mismatch).

No sensitive material (password, derived key, salt, nonce, plaintext,
ciphertext) is ever printed or logged by this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidTag

# --------------------------------------------------------------------------- #
# Cryptographic and format constants (single source of truth).
# --------------------------------------------------------------------------- #

#: Identifies a CryptAudio payload; the first bytes of every payload.
MAGIC: bytes = b"CRYPTAUD"

#: Payload format version. Bump when the binary layout changes incompatibly.
VERSION: int = 1

#: Identifier for the KDF used. 0x01 == PBKDF2-HMAC-SHA256.
KDF_PBKDF2_HMAC_SHA256: int = 1

#: PBKDF2 iteration count. Current OWASP guidance for PBKDF2-HMAC-SHA256.
#: Exposed as a named constant so it can be raised later in exactly one place.
PBKDF2_ITERATIONS: int = 600_000

#: AES-256 key length in bytes (256 bits).
KEY_SIZE: int = 32

#: Salt length in bytes for PBKDF2.
SALT_SIZE: int = 16

#: Nonce length in bytes for AES-GCM (96 bits is the standard GCM nonce size).
NONCE_SIZE: int = 12

#: Length of the GCM authentication tag appended to the ciphertext.
GCM_TAG_SIZE: int = 16

# Fixed-size portion of the header: MAGIC(8) + VERSION(1) + KDF_ID(1) + ITER(4)
_FIXED_HEADER_SIZE: int = len(MAGIC) + 1 + 1 + 4


# --------------------------------------------------------------------------- #
# Project-specific exceptions.
# --------------------------------------------------------------------------- #


class CryptAudioError(Exception):
    """Base class for all CryptAudio cryptography errors."""


class EmptyMessageError(CryptAudioError, ValueError):
    """Raised when an empty plaintext message is supplied."""


class EmptyPasswordError(CryptAudioError, ValueError):
    """Raised when an empty password is supplied."""


class InvalidPayloadError(CryptAudioError):
    """Raised when bytes are not a well-formed CryptAudio payload."""


class AuthenticationError(CryptAudioError):
    """Raised when GCM authentication fails (wrong password or tampering)."""


# --------------------------------------------------------------------------- #
# Internal data container for a parsed payload.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _ParsedPayload:
    """Internal, immutable view of a decoded payload."""

    iterations: int
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    header: bytes  # MAGIC .. NONCE, used as AES-GCM AAD


# --------------------------------------------------------------------------- #
# Private helpers.
# --------------------------------------------------------------------------- #


def _generate_salt() -> bytes:
    """Return a cryptographically secure random salt of :data:`SALT_SIZE` bytes."""
    return os.urandom(SALT_SIZE)


def _generate_nonce() -> bytes:
    """Return a cryptographically secure random nonce of :data:`NONCE_SIZE` bytes.

    A fresh nonce must be generated for every encryption operation; GCM nonce
    reuse under the same key completely breaks confidentiality and authenticity.
    """
    return os.urandom(NONCE_SIZE)


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derive a 256-bit AES key from ``password`` and ``salt`` via PBKDF2.

    Args:
        password: The user-supplied password (never stored or logged).
        salt: Random per-encryption salt.
        iterations: PBKDF2 iteration count.

    Returns:
        A 32-byte key suitable for AES-256.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def _build_payload(
    iterations: int, salt: bytes, nonce: bytes, ciphertext: bytes
) -> bytes:
    """Serialize the components into the deterministic binary payload format."""
    header = (
        MAGIC
        + VERSION.to_bytes(1, "big")
        + KDF_PBKDF2_HMAC_SHA256.to_bytes(1, "big")
        + iterations.to_bytes(4, "big")
        + len(salt).to_bytes(1, "big")
        + salt
        + len(nonce).to_bytes(1, "big")
        + nonce
    )
    return header + len(ciphertext).to_bytes(4, "big") + ciphertext


def _parse_payload(payload: bytes) -> _ParsedPayload:
    """Validate and decode ``payload`` into a :class:`_ParsedPayload`.

    Raises:
        InvalidPayloadError: If the bytes are not a well-formed CryptAudio
            payload (bad magic, unknown version/KDF, or truncated fields).
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise InvalidPayloadError("Payload must be bytes.")

    data = bytes(payload)

    # Minimum size = fixed header + SALT_LEN(1) + NONCE_LEN(1) + CT_LEN(4).
    if len(data) < _FIXED_HEADER_SIZE + 1 + 1 + 4:
        raise InvalidPayloadError("Payload is too short to be valid.")

    offset = 0

    magic = data[offset : offset + len(MAGIC)]
    offset += len(MAGIC)
    if magic != MAGIC:
        raise InvalidPayloadError("Not a CryptAudio payload (bad magic).")

    version = data[offset]
    offset += 1
    if version != VERSION:
        raise InvalidPayloadError(f"Unsupported payload version: {version}.")

    kdf_id = data[offset]
    offset += 1
    if kdf_id != KDF_PBKDF2_HMAC_SHA256:
        raise InvalidPayloadError(f"Unsupported KDF id: {kdf_id}.")

    iterations = int.from_bytes(data[offset : offset + 4], "big")
    offset += 4
    if iterations <= 0:
        raise InvalidPayloadError("Invalid KDF iteration count.")

    salt_len = data[offset]
    offset += 1
    salt = data[offset : offset + salt_len]
    offset += salt_len
    if len(salt) != salt_len:
        raise InvalidPayloadError("Truncated salt field.")

    nonce_len = data[offset]
    offset += 1
    nonce = data[offset : offset + nonce_len]
    offset += nonce_len
    if len(nonce) != nonce_len:
        raise InvalidPayloadError("Truncated nonce field.")

    ct_len = int.from_bytes(data[offset : offset + 4], "big")
    offset += 4
    ciphertext = data[offset : offset + ct_len]
    if len(ciphertext) != ct_len:
        raise InvalidPayloadError("Truncated ciphertext field.")
    if ct_len < GCM_TAG_SIZE:
        raise InvalidPayloadError("Ciphertext shorter than a GCM tag.")

    # AAD header covers MAGIC .. NONCE, i.e. everything before the CT_LEN
    # field (offset currently points just past CT_LEN, so subtract its 4 bytes).
    header = data[: offset - 4]

    return _ParsedPayload(
        iterations=iterations,
        salt=salt,
        nonce=nonce,
        ciphertext=ciphertext,
        header=header,
    )


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


def encrypt_message(message: str, password: str) -> bytes:
    """Encrypt ``message`` under ``password`` into a CryptAudio payload.

    The password is stretched with PBKDF2-HMAC-SHA256 using a fresh random
    salt, and the message is encrypted with AES-256-GCM using a fresh random
    nonce. The salt, nonce and KDF parameters are stored in the returned
    payload; the password is **not**.

    Args:
        message: Non-empty plaintext to encrypt (any Unicode text).
        password: Non-empty password used for key derivation.

    Returns:
        A self-contained binary payload (see module docstring for the format).

    Raises:
        EmptyMessageError: If ``message`` is empty.
        EmptyPasswordError: If ``password`` is empty.
        TypeError: If the arguments are not strings.
    """
    if not isinstance(message, str):
        raise TypeError("message must be a str.")
    if not isinstance(password, str):
        raise TypeError("password must be a str.")
    if message == "":
        raise EmptyMessageError("Message must not be empty.")
    if password == "":
        raise EmptyPasswordError("Password must not be empty.")

    salt = _generate_salt()
    nonce = _generate_nonce()
    key = _derive_key(password, salt, PBKDF2_ITERATIONS)

    # Reconstruct the header exactly as _build_payload will, to use as AAD.
    header = (
        MAGIC
        + VERSION.to_bytes(1, "big")
        + KDF_PBKDF2_HMAC_SHA256.to_bytes(1, "big")
        + PBKDF2_ITERATIONS.to_bytes(4, "big")
        + len(salt).to_bytes(1, "big")
        + salt
        + len(nonce).to_bytes(1, "big")
        + nonce
    )

    aesgcm = AESGCM(key)
    # encrypt() returns ciphertext with the 16-byte tag appended.
    ciphertext = aesgcm.encrypt(nonce, message.encode("utf-8"), header)

    return _build_payload(PBKDF2_ITERATIONS, salt, nonce, ciphertext)


def decrypt_message(payload: bytes, password: str) -> str:
    """Decrypt a CryptAudio ``payload`` using ``password``.

    Args:
        payload: Bytes produced by :func:`encrypt_message`.
        password: The password originally used for encryption.

    Returns:
        The recovered plaintext message as ``str``.

    Raises:
        InvalidPayloadError: If ``payload`` is not a well-formed CryptAudio
            payload.
        EmptyPasswordError: If ``password`` is empty.
        AuthenticationError: If the password is wrong or the payload has been
            tampered with (GCM authentication failure). No plaintext is
            returned in this case.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a str.")
    if password == "":
        raise EmptyPasswordError("Password must not be empty.")

    parsed = _parse_payload(payload)
    key = _derive_key(password, parsed.salt, parsed.iterations)

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(
            parsed.nonce, parsed.ciphertext, parsed.header
        )
    except InvalidTag as exc:
        # Wrong password or tampered data. Do not distinguish the two, to
        # avoid leaking any information about which occurred.
        raise AuthenticationError(
            "Authentication failed: incorrect password or corrupted payload."
        ) from exc

    return plaintext.decode("utf-8")
