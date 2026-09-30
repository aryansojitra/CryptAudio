"""CryptAudio — high-level application service (Phase 5).

This module is a thin **orchestration layer**. It contains no cryptography, no
WAV parsing and no LSB algorithm of its own — it only calls the public APIs of
the stable modules and enforces the correct, secure order of operations:

* :mod:`crypto.aes_crypto`       — AES-256-GCM + PBKDF2 (Phase 2)
* :mod:`audio.wav_handler`       — PCM WAV read/write/inspect (Phase 3)
* :mod:`steganography.lsb_embed` / :mod:`steganography.lsb_extract` — LSB (Phase 4)

Embedding workflow
------------------
::

    message ──encrypt_message()──► encrypted bytes
    input WAV ──read_wav()──► PCM samples
    (capacity check: encrypted bytes must fit)
    encrypted bytes + PCM ──embed_payload()──► modified PCM
    modified PCM ──write_wav()──► stego WAV   (atomic; source never touched)

Extraction workflow
-------------------
::

    stego WAV ──read_wav()──► PCM samples
    PCM ──extract_payload()──► encrypted bytes
    encrypted bytes ──decrypt_message()──► plaintext  (only after GCM auth OK)

Security boundary
-----------------
The plaintext is **never** handed to the LSB layer. Only AES-encrypted bytes are
embedded, and plaintext is only produced after AES-256-GCM authentication
succeeds. The password is passed directly to the crypto module and is never
stored, logged, written to the WAV, or used to derive any key here.

Error abstraction
-----------------
Low-level exceptions from the three layers are translated into clear,
GUI-friendly :class:`ServiceError` subclasses, while the original exception is
preserved via ``raise ... from exc`` for debugging.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from audio.wav_handler import WavError, read_wav, write_wav
from crypto.aes_crypto import (
    AuthenticationError,
    CryptAudioError,
    EmptyMessageError,
    EmptyPasswordError,
    InvalidPayloadError,
    decrypt_message,
    encrypt_message,
)
from steganography.lsb_embed import (
    HEADER_SIZE,
    CapacityError,
    available_payload_bytes,
    embed_payload,
)
from steganography.lsb_extract import (
    CorruptedPayloadError,
    InvalidStegoPayloadError,
    extract_payload,
)

# A user-facing message shared by the "cannot trust the hidden data" cases.
_AUTH_FAILURE_MSG = "Incorrect password or corrupted hidden data."
_NO_PAYLOAD_MSG = "No valid CryptAudio payload found in this WAV file."


# --------------------------------------------------------------------------- #
# Service-level exceptions (high-level, GUI-safe).
# --------------------------------------------------------------------------- #


class ServiceError(Exception):
    """Base class for all high-level CryptAudio service errors."""


class InputValidationError(ServiceError):
    """Raised for invalid arguments: empty message/password, bad paths, etc."""


class AudioError(ServiceError):
    """Raised when a WAV file cannot be read or written."""


class CapacityExceededError(ServiceError):
    """Raised when the encrypted message does not fit in the WAV's capacity."""


class NoHiddenMessageError(ServiceError):
    """Raised when the WAV does not contain a valid CryptAudio payload."""


class AuthenticationFailureError(ServiceError):
    """Raised on wrong password or tampered hidden data (never returns plaintext)."""


# --------------------------------------------------------------------------- #
# Result container.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EmbedResult:
    """Summary of a successful :func:`embed_message` operation."""

    output_path: str
    encrypted_payload_bytes: int   # size of the AES payload (bytes)
    used_bytes: int                # stego header + encrypted payload (bytes)
    capacity_bytes: int            # total LSB capacity of the WAV (bytes)
    available_payload_bytes: int   # capacity left for payload after the header


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _validate_paths(
    input_wav: "str | os.PathLike[str]", output_wav: "str | os.PathLike[str]"
) -> tuple[Path, Path]:
    """Validate input/output paths for embedding.

    Ensures the output is not a directory, its parent exists, and that input and
    output do not resolve to the same file (the source must never be
    overwritten).
    """
    in_path = Path(input_wav)
    out_path = Path(output_wav)

    if out_path.is_dir():
        raise InputValidationError(f"Output path is a directory: {output_wav}")

    parent = out_path.parent
    if str(parent) and not parent.exists():
        raise InputValidationError(f"Output directory does not exist: {parent}")

    try:
        same = in_path.resolve() == out_path.resolve()
    except OSError:
        same = str(in_path) == str(out_path)
    if same:
        raise InputValidationError(
            "Input and output paths must be different; refusing to overwrite "
            "the source WAV."
        )
    return in_path, out_path


def _atomic_write_wav(
    out_path: Path, parameters, frames: bytes, source_path: Path
) -> None:
    """Write the stego WAV atomically, so a failure leaves no corrupt output.

    Data is written to a temporary ``.part`` file and then moved into place with
    :func:`os.replace` (atomic on the same filesystem). The temporary file is
    always cleaned up.
    """
    tmp_path = out_path.with_name(out_path.name + ".part")
    try:
        write_wav(tmp_path, parameters, frames, source_path=source_path)
        os.replace(tmp_path, out_path)
    except WavError as exc:
        raise AudioError(f"Could not write output WAV: {exc}") from exc
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Public API — capacity helper.
# --------------------------------------------------------------------------- #


def available_capacity_bytes(input_wav: "str | os.PathLike[str]") -> int:
    """Return how many encrypted-payload bytes ``input_wav`` can hold.

    This accounts for the LSB framing header reserved by Phase 4. Useful for the
    future GUI to warn the user before attempting to embed.

    Raises:
        AudioError: If the WAV cannot be read.
    """
    try:
        wav_data = read_wav(input_wav)
    except WavError as exc:
        raise AudioError(f"Could not read input WAV: {exc}") from exc
    return available_payload_bytes(wav_data)


# --------------------------------------------------------------------------- #
# Public API — embedding.
# --------------------------------------------------------------------------- #


def embed_message(
    input_wav: "str | os.PathLike[str]",
    output_wav: "str | os.PathLike[str]",
    message: str,
    password: str,
) -> EmbedResult:
    """Encrypt ``message`` and hide it inside ``input_wav``, writing ``output_wav``.

    The message is encrypted with AES-256-GCM (via PBKDF2-derived key) *before*
    any LSB embedding, and only encrypted bytes are ever passed to the
    steganography layer. All validation, encryption and embedding happen in
    memory; the output file is written last and atomically, so the source WAV is
    never modified and no partial output is left behind on failure.

    Args:
        input_wav: Path to a cover PCM WAV file.
        output_wav: Path for the resulting stego WAV (must differ from input).
        message: Non-empty secret plaintext.
        password: Non-empty password (used only by the crypto module).

    Returns:
        An :class:`EmbedResult` summarising sizes and capacity.

    Raises:
        InputValidationError: Empty message/password, identical input/output
            paths, or an invalid output path.
        AudioError: If the input cannot be read or the output cannot be written.
        CapacityExceededError: If the encrypted payload + framing exceeds the
            WAV's LSB capacity (no output file is created).
        ServiceError: On any other unexpected cryptographic failure.
    """
    # 1. Validate scalar inputs.
    if not isinstance(message, str) or message == "":
        raise InputValidationError("Message must be a non-empty string.")
    if not isinstance(password, str) or password == "":
        raise InputValidationError("Password must be a non-empty string.")

    # 2. Validate paths (never overwrite the source).
    in_path, out_path = _validate_paths(input_wav, output_wav)

    # 3. Read the cover audio.
    try:
        wav_data = read_wav(in_path)
    except WavError as exc:
        raise AudioError(f"Could not read input WAV: {exc}") from exc

    # 4. Encrypt the message (plaintext stops here).
    try:
        encrypted = encrypt_message(message, password)
    except (EmptyMessageError, EmptyPasswordError) as exc:
        raise InputValidationError(str(exc)) from exc
    except CryptAudioError as exc:
        raise ServiceError("Encryption failed.") from exc

    # 5. Verify capacity BEFORE creating any output file.
    available = available_payload_bytes(wav_data)
    if len(encrypted) > available:
        raise CapacityExceededError(
            f"Encrypted message needs {len(encrypted)} bytes but this WAV can "
            f"hold at most {available} payload bytes (stego framing reserves "
            f"{HEADER_SIZE} bytes)."
        )

    # 6. Embed the encrypted bytes into the PCM samples (in memory).
    try:
        stego = embed_payload(wav_data, encrypted)
    except CapacityError as exc:  # defensive; already pre-checked above
        raise CapacityExceededError(str(exc)) from exc

    # 7. Atomically write the stego WAV.
    _atomic_write_wav(out_path, stego.parameters, stego.frames, in_path)

    return EmbedResult(
        output_path=str(out_path),
        encrypted_payload_bytes=len(encrypted),
        used_bytes=HEADER_SIZE + len(encrypted),
        capacity_bytes=available + HEADER_SIZE,
        available_payload_bytes=available,
    )


# --------------------------------------------------------------------------- #
# Public API — extraction.
# --------------------------------------------------------------------------- #


def extract_message(
    stego_wav: "str | os.PathLike[str]", password: str
) -> str:
    """Recover the hidden message from ``stego_wav`` using ``password``.

    The LSB frame is extracted first, then AES-256-GCM decrypts and
    authenticates it. Plaintext is returned **only** after successful
    authentication; a wrong password or tampered audio raises an error instead
    of returning corrupted data.

    Args:
        stego_wav: Path to a WAV produced by :func:`embed_message`.
        password: The password used during embedding.

    Returns:
        The original secret message.

    Raises:
        InputValidationError: If the password is empty.
        AudioError: If the WAV cannot be read.
        NoHiddenMessageError: If the file contains no valid CryptAudio payload.
        AuthenticationFailureError: If the password is wrong or the hidden data
            was tampered with.
    """
    if not isinstance(password, str) or password == "":
        raise InputValidationError("Password must be a non-empty string.")

    # 1. Read the stego audio.
    try:
        wav_data = read_wav(stego_wav)
    except WavError as exc:
        raise AudioError(f"Could not read stego WAV: {exc}") from exc

    # 2. Extract the encrypted payload from the LSBs.
    try:
        encrypted = extract_payload(wav_data)
    except CorruptedPayloadError as exc:
        # Frame checksum mismatch => tampered hidden data.
        raise AuthenticationFailureError(_AUTH_FAILURE_MSG) from exc
    except InvalidStegoPayloadError as exc:
        # No CryptAudio framing present (e.g. an ordinary/clean WAV).
        raise NoHiddenMessageError(_NO_PAYLOAD_MSG) from exc

    # 3. Decrypt + authenticate (plaintext appears only on success).
    try:
        return decrypt_message(encrypted, password)
    except AuthenticationError as exc:
        raise AuthenticationFailureError(_AUTH_FAILURE_MSG) from exc
    except InvalidPayloadError as exc:
        raise NoHiddenMessageError(
            "Hidden data is not a valid CryptAudio encrypted payload."
        ) from exc
    except EmptyPasswordError as exc:
        raise InputValidationError(str(exc)) from exc
    except CryptAudioError as exc:
        raise ServiceError("Decryption failed.") from exc
