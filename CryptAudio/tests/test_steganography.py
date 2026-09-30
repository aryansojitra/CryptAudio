"""Unit tests for the CryptAudio LSB steganography module (Phase 4).

All audio used here is small, synthetic and deterministic (seeded NumPy or
silent frames). No real music file is required, and no cryptography is
involved — these tests exercise the pure bytes-in/bytes-out LSB layer.

Run the FULL suite from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import numpy as np
import pytest

from audio.wav_handler import (
    WAVE_COMPRESSION_NONE,
    WavData,
    WavParameters,
    inspect_wav,
    read_wav,
    write_wav,
)
from steganography.lsb_embed import (
    HEADER_SIZE,
    CapacityError,
    CorruptedPayloadError,
    EmptyPayloadError,
    InvalidStegoPayloadError,
    available_payload_bytes,
    build_header,
    bytes_to_bits,
    capacity_bits,
    capacity_bytes,
    embed_payload,
    sample_count,
)
from steganography.lsb_extract import extract_payload


# --------------------------------------------------------------------------- #
# Synthetic PCM helpers (deterministic).
# --------------------------------------------------------------------------- #


def make_wav_data(
    total_samples: int,
    *,
    sample_width: int = 2,
    channels: int = 1,
    seed: int = 1234,
    frame_rate: int = 8000,
) -> WavData:
    """Build a WavData filled with deterministic pseudo-random PCM bytes."""
    assert total_samples % channels == 0, "total_samples must divide by channels"
    n_frames = total_samples // channels
    n_bytes = total_samples * sample_width
    rng = np.random.default_rng(seed)
    frames = rng.integers(0, 256, size=n_bytes, dtype=np.uint8).tobytes()
    params = WavParameters(
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        n_frames=n_frames,
        compression_type=WAVE_COMPRESSION_NONE,
        compression_name="not compressed",
    )
    return WavData(parameters=params, frames=frames)


def make_silent_wav_data(
    total_samples: int, *, sample_width: int = 2, channels: int = 1
) -> WavData:
    """Build an all-zero (silent) WavData — fully deterministic LSBs (=0)."""
    n_frames = total_samples // channels
    frames = bytes(total_samples * sample_width)
    params = WavParameters(
        channels=channels,
        sample_width=sample_width,
        frame_rate=8000,
        n_frames=n_frames,
        compression_type=WAVE_COMPRESSION_NONE,
        compression_name="not compressed",
    )
    return WavData(parameters=params, frames=frames)


def flip_sample_lsb(wav_data: WavData, sample_index: int) -> WavData:
    """Return a copy of ``wav_data`` with one sample's LSB flipped."""
    arr = bytearray(wav_data.frames)
    byte_pos = sample_index * wav_data.sample_width  # little-endian low byte
    arr[byte_pos] ^= 0x01
    return WavData(parameters=wav_data.parameters, frames=bytes(arr))


# --------------------------------------------------------------------------- #
# Test 1 — basic bit embedding / extraction.
# --------------------------------------------------------------------------- #
def test_basic_embed_extract():
    wav = make_wav_data(total_samples=2000, sample_width=2)
    payload = b"Hello CryptAudio"

    stego = embed_payload(wav, payload)
    assert extract_payload(stego) == payload


# --------------------------------------------------------------------------- #
# Test 2 — multiple bytes (larger payload).
# --------------------------------------------------------------------------- #
def test_multiple_bytes():
    payload = bytes(range(256)) * 2  # 512 bytes
    wav = make_wav_data(total_samples=8000, sample_width=2)

    stego = embed_payload(wav, payload)
    assert extract_payload(stego) == payload
    assert len(payload) == 512


# --------------------------------------------------------------------------- #
# Test 3 — all byte values 0x00 .. 0xFF.
# --------------------------------------------------------------------------- #
def test_all_byte_values():
    payload = bytes(range(256))  # every possible byte value exactly once
    wav = make_wav_data(total_samples=4000, sample_width=2)

    stego = embed_payload(wav, payload)
    assert extract_payload(stego) == payload


# --------------------------------------------------------------------------- #
# Test 4 — deterministic random binary data.
# --------------------------------------------------------------------------- #
def test_random_binary_data():
    rng = np.random.default_rng(20240930)
    payload = rng.integers(0, 256, size=300, dtype=np.uint8).tobytes()
    wav = make_wav_data(total_samples=6000, sample_width=2, seed=99)

    stego = embed_payload(wav, payload)
    assert extract_payload(stego) == payload


# --------------------------------------------------------------------------- #
# Test 5 — capacity calculation (frames x channels == LSB positions).
# --------------------------------------------------------------------------- #
def test_capacity_calculation():
    channels, n_frames = 2, 500
    wav = make_wav_data(total_samples=channels * n_frames, channels=channels)

    assert sample_count(wav) == wav.parameters.n_frames * wav.parameters.channels
    assert sample_count(wav) == 1000
    assert capacity_bits(wav) == 1000          # one LSB per sample
    assert capacity_bytes(wav) == 125          # 1000 // 8
    assert available_payload_bytes(wav) == 125 - HEADER_SIZE


# --------------------------------------------------------------------------- #
# Test 6 — oversized payload is rejected.
# --------------------------------------------------------------------------- #
def test_oversized_payload():
    wav = make_wav_data(total_samples=1000, sample_width=2)  # 125 bytes capacity
    payload = b"x" * 200                                     # far too large

    with pytest.raises(CapacityError):
        embed_payload(wav, payload)


# --------------------------------------------------------------------------- #
# Test 7 — empty payload is rejected (documented behaviour).
# --------------------------------------------------------------------------- #
def test_empty_payload_rejected():
    wav = make_wav_data(total_samples=1000, sample_width=2)

    with pytest.raises(EmptyPayloadError):
        embed_payload(wav, b"")


# --------------------------------------------------------------------------- #
# Test 8 — extraction from clean audio (no payload) fails clearly.
# --------------------------------------------------------------------------- #
def test_extract_from_clean_audio():
    clean = make_silent_wav_data(total_samples=2000, sample_width=2)

    with pytest.raises(InvalidStegoPayloadError):
        extract_payload(clean)


def test_extract_from_too_small_audio():
    tiny = make_silent_wav_data(total_samples=HEADER_SIZE * 8 - 1, sample_width=2)

    with pytest.raises(InvalidStegoPayloadError):
        extract_payload(tiny)


# --------------------------------------------------------------------------- #
# Test 9 — corrupted header is rejected.
# --------------------------------------------------------------------------- #
def test_corrupted_header():
    wav = make_wav_data(total_samples=3000, sample_width=2)
    stego = embed_payload(wav, b"header integrity")

    # Flip the very first embedded bit (part of STEGO_MAGIC).
    corrupted = flip_sample_lsb(stego, 0)

    with pytest.raises(InvalidStegoPayloadError):
        extract_payload(corrupted)


# --------------------------------------------------------------------------- #
# Test 10 — corrupted payload is detected via the frame checksum.
# --------------------------------------------------------------------------- #
def test_corrupted_payload_detected():
    wav = make_wav_data(total_samples=4000, sample_width=2)
    payload = b"payload integrity check"
    stego = embed_payload(wav, payload)

    # First payload bit lives right after the header (HEADER_SIZE * 8 samples).
    corrupted = flip_sample_lsb(stego, HEADER_SIZE * 8)

    with pytest.raises(CorruptedPayloadError):
        extract_payload(corrupted)


# --------------------------------------------------------------------------- #
# Test 11 — only the LSB is ever modified (across every supported width).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
def test_lsb_only_modification(sample_width):
    wav = make_wav_data(total_samples=2000, sample_width=sample_width, seed=5)
    payload = b"minimal change test"
    stego = embed_payload(wav, payload)

    orig = np.frombuffer(wav.frames, dtype=np.uint8)
    mod = np.frombuffer(stego.frames, dtype=np.uint8)
    w = sample_width

    # Every non-low byte of each sample must be identical.
    for byte_index in range(1, w):
        assert np.array_equal(orig[byte_index::w], mod[byte_index::w])

    # Low bytes may differ only in bit 0.
    diff = orig[0::w] ^ mod[0::w]
    assert np.all((diff & 0xFE) == 0)

    # Samples beyond the embedded frame must be completely untouched.
    frame_len = HEADER_SIZE + len(payload)
    used_samples = frame_len * 8
    assert np.array_equal(orig[used_samples * w :], mod[used_samples * w :])


# --------------------------------------------------------------------------- #
# Test 12 — samples whose LSB already matches are left unchanged.
# --------------------------------------------------------------------------- #
def test_matching_lsb_unchanged():
    wav = make_wav_data(total_samples=2000, sample_width=2, seed=7)
    payload = b"match test"
    stego = embed_payload(wav, payload)

    frame_bytes = build_header(payload) + payload
    target_bits = bytes_to_bits(frame_bytes)

    w = wav.sample_width
    orig_low = np.frombuffer(wav.frames, dtype=np.uint8)[0::w]
    mod_low = np.frombuffer(stego.frames, dtype=np.uint8)[0::w]

    already_matched = 0
    for i in range(target_bits.size):
        original = int(orig_low[i])
        modified = int(mod_low[i])
        bit = int(target_bits[i])
        if (original & 1) == bit:
            assert modified == original  # unchanged when LSB already correct
            already_matched += 1
        else:
            assert modified == (original & 0xFE) | bit  # exactly bit 0 flipped

    # Ensure the test actually exercised the "already matches" branch.
    assert already_matched > 0


# --------------------------------------------------------------------------- #
# Extra — full WAV-file round trip proves the header/metadata is preserved.
# --------------------------------------------------------------------------- #
def test_full_wav_roundtrip_preserves_metadata(tmp_path):
    payload = b"end-to-end through real WAV files"

    src = tmp_path / "orig.wav"
    original = make_wav_data(
        total_samples=4000, sample_width=2, channels=2, seed=42
    )
    write_wav(src, original.parameters, original.frames)

    data = read_wav(src)
    stego = embed_payload(data, payload)

    dst = tmp_path / "stego.wav"
    write_wav(dst, stego.parameters, stego.frames, source_path=src)

    info_orig = inspect_wav(src)
    info_stego = inspect_wav(dst)

    # Audio format metadata must be identical (headers untouched).
    assert info_stego.channels == info_orig.channels
    assert info_stego.sample_width == info_orig.sample_width
    assert info_stego.frame_rate == info_orig.frame_rate
    assert info_stego.n_frames == info_orig.n_frames
    assert info_stego.duration_seconds == pytest.approx(info_orig.duration_seconds)

    # And the payload survives the write -> read cycle through real files.
    assert extract_payload(read_wav(dst)) == payload


def test_deterministic_embedding():
    """Same audio + same payload must produce identical stego bytes."""
    wav_a = make_wav_data(total_samples=2000, sample_width=2, seed=11)
    wav_b = make_wav_data(total_samples=2000, sample_width=2, seed=11)
    payload = b"determinism"

    assert embed_payload(wav_a, payload).frames == embed_payload(wav_b, payload).frames
