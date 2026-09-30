"""CryptAudio — LSB embedding and shared stego framing (Phase 4).

This module hides arbitrary **bytes** inside PCM WAV audio by overwriting the
least significant bit (LSB) of each audio sample. It is deliberately ignorant
of *what* those bytes mean: it knows nothing about passwords, AES, PBKDF2,
plaintext or the GUI. That separation keeps cryptography (Phase 2) and
steganography (Phase 4) fully modular; they are only combined in Phase 5.

    >>> LSB steganography provides concealment, NOT cryptographic
    >>> confidentiality. Anyone who knows the format can extract the hidden
    >>> bytes. Real confidentiality comes from AES-256-GCM (Phase 5), which
    >>> encrypts the message *before* it is handed to this layer.

What is an LSB?
---------------
Each PCM sample is an integer amplitude. Its least significant bit contributes
only +/-1 to that amplitude — inaudible under normal listening. We overwrite
that single bit with one payload bit:

    payload bit 1 -> sample LSB becomes 1
    payload bit 0 -> sample LSB becomes 0
    already equal -> sample left completely unchanged

One sample carries one bit, so::

    capacity_bits  = number_of_samples = n_frames * channels
    capacity_bytes = capacity_bits // 8

Only the PCM ``data`` samples are modified. The RIFF header, ``fmt `` chunk,
``data`` chunk metadata, sample rate, channel count and sample width are NEVER
touched — this module only ever returns modified *frame bytes*; WAV file I/O
stays in :mod:`audio.wav_handler`.

Payload framing
---------------
The extractor must know how many bits to read, so a fixed-size, self-describing
header is embedded first, using the same LSB mechanism::

    Offset  Field           Size  Description
    0       STEGO_MAGIC     4 B   b"CALS" — identifies a CryptAudio LSB frame
    4       VERSION         1 B   frame format version (0x01)
    5       PAYLOAD_LENGTH  4 B   uint32 big-endian — payload length in bytes
    9       CHECKSUM        4 B   uint32 big-endian — CRC32 of the payload
    ------------------------------------------------ 13-byte header (104 bits)
    13      PAYLOAD         var   the hidden bytes

The CRC32 is a *non-cryptographic* integrity sanity check so accidental bit
corruption can be detected; it is not a security mechanism.

Sample representation & byte ordering
-------------------------------------
WAV PCM samples are stored **little-endian** (8-bit PCM is unsigned, stored as
a single byte). Therefore the least significant byte of every sample is its
*first* stored byte, and the sample's LSB is bit 0 of that byte. The LSB
positions across the whole ``data`` chunk are simply the strided slice::

    frame_bytes[0::sample_width]

This rule is identical for 8/16/24/32-bit PCM — only the stride changes. We
operate on a ``uint8`` view and never decode samples to ``int16``/``int32``,
which keeps 24-bit PCM (no native NumPy dtype) correct and preserves endianness
exactly. Flipping only bit 0 changes each sample by at most +/-1 and can never
overflow.

Supported PCM widths: 8, 16, 24 and 32 bits (as validated by Phase 3).

Limitations of LSB steganography
--------------------------------
* Concealment only — no confidentiality without encryption.
* Fragile: any lossy conversion (MP3/AAC/OGG), resampling or re-quantisation
  destroys the hidden bits. Only lossless PCM WAV survives.
* Capacity is bounded by the audio length (1 bit per sample here).
* A statistical steganalysis (e.g. RS analysis) can detect LSB embedding; this
  academic implementation prioritises clarity over steganographic undetectability.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from audio.wav_handler import WavData

# --------------------------------------------------------------------------- #
# Frame-format constants (single source of truth shared with lsb_extract).
# --------------------------------------------------------------------------- #

#: Magic bytes identifying a CryptAudio LSB frame.
STEGO_MAGIC: bytes = b"CALS"

#: Frame format version.
STEGO_VERSION: int = 1

_MAGIC_SIZE: int = len(STEGO_MAGIC)      # 4
_VERSION_SIZE: int = 1
_LENGTH_SIZE: int = 4                     # uint32 payload length
_CHECKSUM_SIZE: int = 4                   # uint32 CRC32

#: Total fixed header size in bytes (embedded as HEADER_SIZE * 8 LSB bits).
HEADER_SIZE: int = _MAGIC_SIZE + _VERSION_SIZE + _LENGTH_SIZE + _CHECKSUM_SIZE  # 13


# --------------------------------------------------------------------------- #
# Exceptions.
# --------------------------------------------------------------------------- #


class StegoError(Exception):
    """Base class for all CryptAudio steganography errors."""


class CapacityError(StegoError):
    """Raised when a payload does not fit in the available audio capacity."""


class EmptyPayloadError(StegoError, ValueError):
    """Raised when an empty payload is supplied to the embedder."""


class InvalidStegoPayloadError(StegoError):
    """Raised when audio does not contain a valid CryptAudio LSB frame."""


class CorruptedPayloadError(InvalidStegoPayloadError):
    """Raised when the frame checksum does not match (corrupted embedded bits).

    Subclasses :class:`InvalidStegoPayloadError` so callers can catch either.
    """


# --------------------------------------------------------------------------- #
# Header data container.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StegoHeader:
    """Decoded fixed-size stego frame header."""

    version: int
    payload_length: int
    checksum: int


# --------------------------------------------------------------------------- #
# Bit <-> byte utilities (MSB-first bit order within each byte).
# --------------------------------------------------------------------------- #


def bytes_to_bits(data: bytes) -> np.ndarray:
    """Expand bytes into a ``uint8`` array of bits (MSB first within each byte)."""
    return np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8), bitorder="big")


def bits_to_bytes(bits) -> bytes:
    """Pack an array of bits (MSB first) back into bytes.

    The bit count must be a multiple of 8; callers always read whole bytes.
    """
    bit_array = np.asarray(bits, dtype=np.uint8)
    if bit_array.size % 8 != 0:
        raise StegoError("Bit count must be a multiple of 8 to form bytes.")
    return np.packbits(bit_array, bitorder="big").tobytes()


# --------------------------------------------------------------------------- #
# Sample / capacity helpers.
# --------------------------------------------------------------------------- #


def sample_count(wav_data: WavData) -> int:
    """Return the number of PCM samples (= n_frames * channels) in ``wav_data``."""
    width = wav_data.sample_width
    if width <= 0:
        raise StegoError("Invalid sample width in audio data.")
    return len(wav_data.frames) // width


def capacity_bits(wav_data: WavData) -> int:
    """Usable LSB positions = one bit per sample."""
    return sample_count(wav_data)


def capacity_bytes(wav_data: WavData) -> int:
    """Usable capacity expressed in whole bytes."""
    return capacity_bits(wav_data) // 8


def available_payload_bytes(wav_data: WavData) -> int:
    """Maximum *payload* bytes that fit, after reserving room for the header."""
    return max(0, capacity_bytes(wav_data) - HEADER_SIZE)


# --------------------------------------------------------------------------- #
# Low-level LSB core (operate on the little-endian low byte of each sample).
# --------------------------------------------------------------------------- #


def read_lsb_bits(frames: bytes, sample_width: int, count: int) -> np.ndarray:
    """Read ``count`` LSBs from ``frames`` (one per sample) as a bit array.

    Raises:
        InvalidStegoPayloadError: If ``count`` exceeds the available samples.
    """
    if sample_width <= 0:
        raise StegoError("Invalid sample width.")
    array = np.frombuffer(bytes(frames), dtype=np.uint8)
    low_bytes = array[0::sample_width]  # little-endian low byte of each sample
    if count > low_bytes.size:
        raise InvalidStegoPayloadError(
            f"Requested {count} bits but audio holds only {low_bytes.size} samples."
        )
    return (low_bytes[:count] & 1).astype(np.uint8)


def write_lsb_bits(frames: bytes, sample_width: int, bits) -> bytes:
    """Return a copy of ``frames`` with sample LSBs overwritten by ``bits``.

    Only bit 0 of each sample's little-endian low byte is changed; every other
    byte is preserved exactly. The input ``frames`` are never mutated.

    Raises:
        CapacityError: If there are more bits than available samples.
    """
    if sample_width <= 0:
        raise StegoError("Invalid sample width.")
    bit_array = np.asarray(bits, dtype=np.uint8) & 1
    array = np.frombuffer(bytes(frames), dtype=np.uint8).copy()  # writable copy
    low_bytes = array[0::sample_width]  # view into the writable copy
    if bit_array.size > low_bytes.size:
        raise CapacityError(
            f"Need {bit_array.size} samples but audio provides {low_bytes.size}."
        )
    n = bit_array.size
    # Clear bit 0, then set it to the payload bit. Higher bits untouched.
    low_bytes[:n] = (low_bytes[:n] & 0xFE) | bit_array[:n]
    return array.tobytes()


# --------------------------------------------------------------------------- #
# Framing header build / parse.
# --------------------------------------------------------------------------- #


def build_header(payload: bytes) -> bytes:
    """Construct the fixed-size frame header for ``payload``."""
    checksum = zlib.crc32(payload) & 0xFFFFFFFF
    return (
        STEGO_MAGIC
        + bytes([STEGO_VERSION])
        + len(payload).to_bytes(_LENGTH_SIZE, "big")
        + checksum.to_bytes(_CHECKSUM_SIZE, "big")
    )


def parse_header(header: bytes) -> StegoHeader:
    """Validate and decode a fixed-size frame header.

    Raises:
        InvalidStegoPayloadError: If the header is truncated, the magic does not
            match, or the version is unsupported.
    """
    if len(header) != HEADER_SIZE:
        raise InvalidStegoPayloadError("Stego header is truncated.")
    if header[:_MAGIC_SIZE] != STEGO_MAGIC:
        raise InvalidStegoPayloadError(
            "No CryptAudio LSB payload found (magic mismatch)."
        )
    version = header[_MAGIC_SIZE]
    if version != STEGO_VERSION:
        raise InvalidStegoPayloadError(f"Unsupported stego frame version: {version}.")

    offset = _MAGIC_SIZE + _VERSION_SIZE
    payload_length = int.from_bytes(header[offset : offset + _LENGTH_SIZE], "big")
    offset += _LENGTH_SIZE
    checksum = int.from_bytes(header[offset : offset + _CHECKSUM_SIZE], "big")
    return StegoHeader(
        version=version, payload_length=payload_length, checksum=checksum
    )


# --------------------------------------------------------------------------- #
# Public API — embedding.
# --------------------------------------------------------------------------- #


def embed_payload(wav_data: WavData, payload: bytes) -> WavData:
    """Hide ``payload`` bytes inside ``wav_data`` using LSB steganography.

    The payload is prefixed with a fixed framing header (magic, version,
    length, CRC32) and the combined bytes are written one bit per sample into
    the LSBs of the PCM data.

    This function does **not** write any file and does **not** mutate its input.
    It returns a new :class:`~audio.wav_handler.WavData` with identical
    parameters and modified frame bytes, ready for :func:`audio.wav_handler.write_wav`.

    Args:
        wav_data: PCM audio (from :func:`audio.wav_handler.read_wav`).
        payload: Arbitrary non-empty bytes to conceal.

    Returns:
        A new ``WavData`` with the payload embedded.

    Raises:
        EmptyPayloadError: If ``payload`` is empty.
        CapacityError: If header + payload exceed the audio's LSB capacity.
        TypeError: If ``payload`` is not bytes-like.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes-like.")
    if len(payload) == 0:
        raise EmptyPayloadError("Cannot embed an empty payload.")

    frame_bytes = build_header(bytes(payload)) + bytes(payload)
    needed_bits = len(frame_bytes) * 8

    if needed_bits > capacity_bits(wav_data):
        raise CapacityError(
            f"Payload too large: needs {len(frame_bytes)} bytes of LSB capacity "
            f"(header {HEADER_SIZE} + payload {len(payload)}); audio holds at "
            f"most {available_payload_bytes(wav_data)} payload bytes."
        )

    bits = bytes_to_bits(frame_bytes)
    modified_frames = write_lsb_bits(
        wav_data.frames, wav_data.sample_width, bits
    )
    # Parameters (channels, sample width, frame rate, n_frames) are unchanged.
    return WavData(parameters=wav_data.parameters, frames=modified_frames)
