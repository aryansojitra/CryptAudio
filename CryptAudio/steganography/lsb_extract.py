"""CryptAudio — LSB extraction (Phase 4).

This module recovers arbitrary **bytes** previously hidden in PCM WAV audio by
:mod:`steganography.lsb_embed`. Like the embedder, it is completely unaware of
passwords, AES, plaintext or the GUI — it only reads LSBs and returns bytes.

    >>> Extraction reverses embedding: it reads the fixed framing header,
    >>> validates it, then reads exactly the declared number of payload bytes.
    >>> It provides concealment recovery only — NOT confidentiality. The hidden
    >>> bytes are expected to be AES-256-GCM ciphertext (Phase 5).

The frame format, bit ordering and low-level LSB reader are imported from
:mod:`steganography.lsb_embed` so that the embedding and extraction sides can
never disagree about the layout. See that module's docstring for the full
format, sample-representation and endianness discussion.

Extraction procedure
--------------------
::

    read fixed 13-byte header (104 LSBs)
        -> validate STEGO_MAGIC
        -> validate VERSION
        -> read PAYLOAD_LENGTH
        -> validate the audio actually holds that many bits
        -> read exactly PAYLOAD_LENGTH bytes
        -> verify CRC32 checksum
        -> return payload bytes
"""

from __future__ import annotations

import zlib

from audio.wav_handler import WavData

# Reuse the canonical framing + LSB core defined by the embedder so both sides
# stay byte-for-byte compatible.
from steganography.lsb_embed import (
    HEADER_SIZE,
    CorruptedPayloadError,
    InvalidStegoPayloadError,
    bits_to_bytes,
    capacity_bits,
    parse_header,
    read_lsb_bits,
)

__all__ = [
    "extract_payload",
    "CorruptedPayloadError",
    "InvalidStegoPayloadError",
]


def extract_payload(wav_data: WavData) -> bytes:
    """Extract and return the hidden payload bytes from ``wav_data``.

    The number of bytes to read is taken from the embedded framing header, so
    the caller does not need to know the payload length in advance.

    Args:
        wav_data: PCM audio (from :func:`audio.wav_handler.read_wav`) that is
            expected to contain a CryptAudio LSB frame.

    Returns:
        The exact payload bytes that were embedded.

    Raises:
        InvalidStegoPayloadError: If the audio is too small to hold a header,
            the magic/version do not match (i.e. no CryptAudio payload is
            present), or the declared length exceeds the available audio.
        CorruptedPayloadError: If the frame checksum does not match, indicating
            the embedded bits were altered. (Subclass of
            :class:`InvalidStegoPayloadError`.)
    """
    total_bits = capacity_bits(wav_data)

    # Need at least the header before we can learn anything.
    if total_bits < HEADER_SIZE * 8:
        raise InvalidStegoPayloadError(
            "Audio is too small to contain a CryptAudio LSB frame."
        )

    header_bits = read_lsb_bits(
        wav_data.frames, wav_data.sample_width, HEADER_SIZE * 8
    )
    header = parse_header(bits_to_bytes(header_bits))

    # Validate that the declared payload actually fits in this audio.
    total_frame_bytes = HEADER_SIZE + header.payload_length
    if header.payload_length <= 0:
        raise InvalidStegoPayloadError("Frame declares an empty payload.")
    if total_frame_bytes * 8 > total_bits:
        raise InvalidStegoPayloadError(
            f"Frame declares {header.payload_length} payload bytes but the audio "
            f"can only hold {total_bits // 8 - HEADER_SIZE}."
        )

    frame_bits = read_lsb_bits(
        wav_data.frames, wav_data.sample_width, total_frame_bytes * 8
    )
    frame_bytes = bits_to_bytes(frame_bits)
    payload = frame_bytes[HEADER_SIZE:]

    actual_checksum = zlib.crc32(payload) & 0xFFFFFFFF
    if actual_checksum != header.checksum:
        raise CorruptedPayloadError(
            "Embedded payload failed its checksum — the hidden bits appear to "
            "be corrupted."
        )

    return payload
