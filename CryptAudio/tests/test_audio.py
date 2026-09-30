"""Unit tests for the CryptAudio WAV/PCM audio handler (Phase 3).

All WAV files used here are small, synthetic and generated programmatically
with Python's :mod:`wave` module. The tests are therefore reproducible,
deterministic and independent of any real audio file in the repository.

Run from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

import pytest

from audio.wav_handler import (
    WAVE_COMPRESSION_NONE,
    Capacity,
    InvalidWavError,
    UnsupportedWavError,
    WavError,
    WavNotFoundError,
    calculate_capacity,
    capacity_of,
    inspect_wav,
    read_wav,
    write_wav,
)


# --------------------------------------------------------------------------- #
# Synthetic WAV helpers.
# --------------------------------------------------------------------------- #


def _synth_frames(n_frames: int, channels: int, sample_width: int) -> bytes:
    """Generate deterministic PCM frame bytes for the given format.

    The pattern is reproducible (no randomness) so round-trip comparisons are
    exact and stable across runs.
    """
    data = bytearray()
    for f in range(n_frames):
        for c in range(channels):
            if sample_width == 1:
                data.append((f + c) % 256)                       # unsigned 8-bit
            elif sample_width == 2:
                v = ((f * 7 + c * 13) % 65536) - 32768           # signed 16-bit
                data += struct.pack("<h", v)
            elif sample_width == 3:
                v = ((f * 7 + c * 13) % 16777216) - 8388608      # signed 24-bit
                data += (v & 0xFFFFFF).to_bytes(3, "little")
            elif sample_width == 4:
                v = ((f * 7 + c * 13) % 4294967296) - 2147483648  # signed 32-bit
                data += struct.pack("<i", v)
            else:  # pragma: no cover - guarded by parametrization
                raise ValueError("unsupported sample width in test helper")
    return bytes(data)


def _make_wav(
    path: Path,
    *,
    channels: int = 1,
    sample_width: int = 2,
    n_frames: int = 100,
    frame_rate: int = 8000,
) -> bytes:
    """Create a synthetic PCM WAV file and return the exact frame bytes used."""
    frames = _synth_frames(n_frames, channels, sample_width)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(frame_rate)
        wf.writeframes(frames)
    return frames


def _make_nonpcm_wav(path: Path) -> None:
    """Write a minimal IEEE-float (non-PCM) WAV to trigger UnsupportedWavError."""
    channels, sample_rate, bits = 1, 8000, 32
    block_align = channels * (bits // 8)
    byte_rate = sample_rate * block_align
    fmt = struct.pack("<HHLLHH", 3, channels, sample_rate, byte_rate, block_align, bits)
    data = b"\x00" * (block_align * 4)
    riff_size = 4 + (8 + len(fmt)) + (8 + len(data))
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", riff_size) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(data)) + data)


# --------------------------------------------------------------------------- #
# Test 1 — create a valid synthetic WAV and inspect it.
# --------------------------------------------------------------------------- #
def test_create_and_inspect_valid_wav(tmp_path):
    wav_path = tmp_path / "valid.wav"
    _make_wav(wav_path, channels=1, sample_width=2, n_frames=50)

    info = inspect_wav(wav_path)
    assert info.path.endswith("valid.wav")
    assert info.is_pcm is True


# --------------------------------------------------------------------------- #
# Test 2 — metadata is reported correctly.
# --------------------------------------------------------------------------- #
def test_metadata(tmp_path):
    wav_path = tmp_path / "meta.wav"
    _make_wav(wav_path, channels=2, sample_width=2, n_frames=1600, frame_rate=8000)

    info = inspect_wav(wav_path)
    assert info.channels == 2
    assert info.sample_width == 2
    assert info.sample_width_bits == 16
    assert info.frame_rate == 8000
    assert info.n_frames == 1600
    # duration = n_frames / frame_rate = 1600 / 8000 = 0.2 s
    assert info.duration_seconds == pytest.approx(0.2)
    assert info.total_samples == 3200
    assert info.frame_size_bytes == 4


# --------------------------------------------------------------------------- #
# Test 3 — PCM WAV is accepted.
# --------------------------------------------------------------------------- #
def test_pcm_accepted(tmp_path):
    wav_path = tmp_path / "pcm.wav"
    _make_wav(wav_path)

    info = inspect_wav(wav_path)
    assert info.is_pcm is True
    assert info.compression_type == WAVE_COMPRESSION_NONE
    assert info.compression_name == "not compressed"


# --------------------------------------------------------------------------- #
# Test 4 — invalid (non-WAV) file produces a clear validation error.
# --------------------------------------------------------------------------- #
def test_invalid_file(tmp_path):
    bad = tmp_path / "not_really.wav"
    bad.write_bytes(b"this is definitely not a wav file at all")

    with pytest.raises(InvalidWavError):
        inspect_wav(bad)
    with pytest.raises(InvalidWavError):
        read_wav(bad)


def test_directory_rejected(tmp_path):
    with pytest.raises(InvalidWavError):
        inspect_wav(tmp_path)


# --------------------------------------------------------------------------- #
# Test 5 — missing file produces a clear not-found error.
# --------------------------------------------------------------------------- #
def test_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.wav"
    with pytest.raises(WavNotFoundError):
        inspect_wav(missing)
    with pytest.raises(WavNotFoundError):
        read_wav(missing)
    with pytest.raises(WavNotFoundError):
        capacity_of(missing)


# --------------------------------------------------------------------------- #
# Test 6 — read/write round trip preserves parameters and PCM bytes.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("channels", [1, 2])
@pytest.mark.parametrize("sample_width", [1, 2, 3, 4])
def test_read_write_roundtrip(tmp_path, channels, sample_width):
    src = tmp_path / f"src_{channels}_{sample_width}.wav"
    original_frames = _make_wav(src, channels=channels, sample_width=sample_width, n_frames=64)

    data = read_wav(src)
    # Read frames must equal exactly what we wrote.
    assert data.frames == original_frames

    dst = tmp_path / f"dst_{channels}_{sample_width}.wav"
    write_wav(dst, data.parameters, data.frames, source_path=src)

    # Re-read and confirm the format and PCM bytes survived the round trip.
    reread = read_wav(dst)
    assert reread.parameters.channels == data.parameters.channels
    assert reread.parameters.sample_width == data.parameters.sample_width
    assert reread.parameters.frame_rate == data.parameters.frame_rate
    assert reread.parameters.n_frames == data.parameters.n_frames
    assert reread.frames == data.frames


# --------------------------------------------------------------------------- #
# Test 7 — capacity math for a known WAV.
# --------------------------------------------------------------------------- #
def test_capacity(tmp_path):
    wav_path = tmp_path / "cap.wav"
    _make_wav(wav_path, channels=2, sample_width=2, n_frames=1000)

    cap = capacity_of(wav_path)
    assert isinstance(cap, Capacity)
    assert cap.frames == 1000
    assert cap.channels == 2
    assert cap.total_samples == 2000        # 1000 frames * 2 channels
    assert cap.capacity_bits == 2000        # one LSB per sample
    assert cap.capacity_bytes == 250        # 2000 // 8


def test_calculate_capacity_pure():
    cap = calculate_capacity(n_frames=8, channels=1)
    assert cap.total_samples == 8
    assert cap.capacity_bits == 8
    assert cap.capacity_bytes == 1


# --------------------------------------------------------------------------- #
# Test 8 — mono vs stereo capacity.
# --------------------------------------------------------------------------- #
def test_mono_and_stereo_capacity(tmp_path):
    mono = tmp_path / "mono.wav"
    stereo = tmp_path / "stereo.wav"
    _make_wav(mono, channels=1, sample_width=2, n_frames=500)
    _make_wav(stereo, channels=2, sample_width=2, n_frames=500)

    mono_cap = capacity_of(mono)
    stereo_cap = capacity_of(stereo)

    assert mono_cap.total_samples == 500
    assert stereo_cap.total_samples == 1000
    # Stereo holds twice the capacity of mono for the same frame count.
    assert stereo_cap.capacity_bits == 2 * mono_cap.capacity_bits


# --------------------------------------------------------------------------- #
# Test 9 — supported sample widths (8/16/24/32-bit).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "sample_width,expected_bits",
    [(1, 8), (2, 16), (3, 24), (4, 32)],
)
def test_sample_widths(tmp_path, sample_width, expected_bits):
    wav_path = tmp_path / f"w{sample_width}.wav"
    _make_wav(wav_path, channels=1, sample_width=sample_width, n_frames=32)

    info = inspect_wav(wav_path)
    assert info.sample_width == sample_width
    assert info.sample_width_bits == expected_bits

    # 24-bit must be handled correctly, not silently misinterpreted.
    data = read_wav(wav_path)
    assert data.sample_width == sample_width
    assert len(data.frames) == 32 * sample_width


# --------------------------------------------------------------------------- #
# Extras — non-PCM rejection and source-overwrite protection.
# --------------------------------------------------------------------------- #
def test_nonpcm_wav_rejected(tmp_path):
    float_wav = tmp_path / "float.wav"
    _make_nonpcm_wav(float_wav)

    with pytest.raises(UnsupportedWavError):
        inspect_wav(float_wav)
    with pytest.raises(UnsupportedWavError):
        read_wav(float_wav)


def test_write_refuses_to_overwrite_source(tmp_path):
    src = tmp_path / "src.wav"
    _make_wav(src, channels=1, sample_width=2, n_frames=16)
    data = read_wav(src)

    with pytest.raises(WavError):
        write_wav(src, data.parameters, data.frames, source_path=src)


def test_write_rejects_inconsistent_frames(tmp_path):
    src = tmp_path / "src.wav"
    _make_wav(src, channels=1, sample_width=2, n_frames=16)
    data = read_wav(src)

    dst = tmp_path / "dst.wav"
    # Drop one byte so the length is no longer a whole number of frames.
    with pytest.raises(WavError):
        write_wav(dst, data.parameters, data.frames[:-1])
