"""Tests for audio quality evaluation (Phase 7).

Synthetic WAV data only — no real music files required. Tests cover:
    - MSE, SNR, PSNR correctness
    - Modified sample counting
    - Metadata mismatch detection
    - 8/16/24/32-bit PCM interpretation
    - Real integration with the CryptAudio service

Run the FULL regression suite from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from audio.wav_handler import WavParameters, write_wav
from evaluation.audio_quality import (
    AudioQualityResult,
    EvaluationError,
    calculate_metrics,
    compare_audio,
    decode_pcm,
)
from services.cryptaudio_service import embed_message


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _make_wav(path, frames: bytes, channels: int, sample_width: int, rate: int):
    """Write a synthetic WAV with the given raw PCM frames."""
    n_frames = len(frames) // (channels * sample_width)
    params = WavParameters(
        channels=channels,
        sample_width=sample_width,
        frame_rate=rate,
        n_frames=n_frames,
        compression_type=1,
        compression_name="not compressed",
    )
    write_wav(path, params, frames)


def _pcm_bytes_16(samples: list[int]) -> bytes:
    """Convert a list of 16-bit signed ints to little-endian bytes."""
    return b"".join(int(s).to_bytes(2, "little", signed=True) for s in samples)


def _pcm_bytes_24(samples: list[int]) -> bytes:
    """Convert a list of 24-bit signed ints to little-endian bytes."""
    return b"".join(int(s).to_bytes(3, "little", signed=True) for s in samples)


def _pcm_bytes_32(samples: list[int]) -> bytes:
    """Convert a list of 32-bit signed ints to little-endian bytes."""
    return b"".join(int(s).to_bytes(4, "little", signed=True) for s in samples)


# --------------------------------------------------------------------------- #
# Test 1 — Identical audio.
# --------------------------------------------------------------------------- #
def test_identical_audio():
    """Compare a WAV with itself: MSE=0, SNR=inf, PSNR=inf, modified=0."""
    samples = np.array([100, -200, 300, -400], dtype=np.int64)
    result = calculate_metrics(samples, samples.copy(), sample_width=2)

    assert result.mse == 0.0
    assert math.isinf(result.snr_db) and result.snr_db > 0
    assert math.isinf(result.psnr_db) and result.psnr_db > 0
    assert result.modified_samples == 0
    assert result.modification_percentage == 0.0
    assert result.max_sample_difference == 0


# --------------------------------------------------------------------------- #
# Test 2 — Known MSE.
# --------------------------------------------------------------------------- #
def test_known_mse():
    """Manually calculate MSE for small synthetic arrays."""
    orig = np.array([0, 100, -100, 50], dtype=np.int64)
    stego = np.array([0, 101, -99, 51], dtype=np.int64)
    # diff = [0, 1, 1, 1], squared = [0, 1, 1, 1], MSE = 3/4 = 0.75
    result = calculate_metrics(orig, stego, sample_width=2)

    assert result.mse == pytest.approx(0.75, rel=1e-9)


# --------------------------------------------------------------------------- #
# Test 3 — Known SNR.
# --------------------------------------------------------------------------- #
def test_known_snr():
    """Verify SNR against a manually calculated value."""
    orig = np.array([1000, -1000, 500, -500], dtype=np.int64)
    stego = np.array([1001, -999, 501, -499], dtype=np.int64)
    # signal_power = mean([1e6, 1e6, 250000, 250000]) = 625000
    # noise = [-1, -1, -1, -1], noise_power = 1
    # SNR = 10 * log10(625000 / 1) ≈ 57.9588 dB
    result = calculate_metrics(orig, stego, sample_width=2)

    expected_snr = 10.0 * math.log10(625000.0 / 1.0)
    assert result.snr_db == pytest.approx(expected_snr, rel=1e-6)


# --------------------------------------------------------------------------- #
# Test 4 — Known PSNR.
# --------------------------------------------------------------------------- #
def test_known_psnr():
    """Verify PSNR against a manually calculated value (16-bit)."""
    orig = np.array([1000, -1000], dtype=np.int64)
    stego = np.array([1001, -999], dtype=np.int64)
    # MSE = (1 + 1) / 2 = 1.0
    # MAX = 32767, PSNR = 10 * log10(32767^2 / 1) ≈ 90.309 dB
    result = calculate_metrics(orig, stego, sample_width=2)

    expected_psnr = 10.0 * math.log10((32767 ** 2) / 1.0)
    assert result.psnr_db == pytest.approx(expected_psnr, rel=1e-6)


# --------------------------------------------------------------------------- #
# Test 5 — Modified sample count.
# --------------------------------------------------------------------------- #
def test_modified_sample_count():
    """Verify modified_samples is counted correctly."""
    orig = np.array([10, 20, 30, 40], dtype=np.int64)
    stego = np.array([10, 21, 30, 41], dtype=np.int64)
    result = calculate_metrics(orig, stego, sample_width=2)

    assert result.modified_samples == 2


# --------------------------------------------------------------------------- #
# Test 6 — Modification percentage.
# --------------------------------------------------------------------------- #
def test_modification_percentage():
    """Verify modification_percentage = (modified / total) * 100."""
    orig = np.array([10, 20, 30, 40], dtype=np.int64)
    stego = np.array([10, 21, 30, 41], dtype=np.int64)
    result = calculate_metrics(orig, stego, sample_width=2)

    assert result.modification_percentage == pytest.approx(50.0, rel=1e-9)


# --------------------------------------------------------------------------- #
# Test 7 — Maximum difference.
# --------------------------------------------------------------------------- #
def test_max_difference():
    """Verify max_sample_difference is calculated correctly."""
    orig = np.array([100, -200, 300], dtype=np.int64)
    stego = np.array([101, -198, 305], dtype=np.int64)
    # diff = [-1, -2, -5], abs = [1, 2, 5], max = 5
    result = calculate_metrics(orig, stego, sample_width=2)

    assert result.max_sample_difference == 5


# --------------------------------------------------------------------------- #
# Test 8 — Metadata mismatch.
# --------------------------------------------------------------------------- #
def test_metadata_mismatch(tmp_path):
    """Compare WAVs with different sample rates → EvaluationError."""
    cover = tmp_path / "cover.wav"
    stego = tmp_path / "stego.wav"

    frames = _pcm_bytes_16([100, -100, 200, -200])
    _make_wav(str(cover), frames, channels=1, sample_width=2, rate=44100)
    _make_wav(str(stego), frames, channels=1, sample_width=2, rate=48000)

    with pytest.raises(EvaluationError, match="Frame rate mismatch"):
        compare_audio(str(cover), str(stego))


# --------------------------------------------------------------------------- #
# Test 9 — Different frame counts.
# --------------------------------------------------------------------------- #
def test_different_frame_counts(tmp_path):
    """Verify mismatched signal lengths are rejected."""
    cover = tmp_path / "cover.wav"
    stego = tmp_path / "stego.wav"

    frames_long = _pcm_bytes_16([100, -100, 200, -200])
    frames_short = _pcm_bytes_16([100, -100])
    _make_wav(str(cover), frames_long, channels=1, sample_width=2, rate=44100)
    _make_wav(str(stego), frames_short, channels=1, sample_width=2, rate=44100)

    with pytest.raises(EvaluationError, match="Frame count mismatch"):
        compare_audio(str(cover), str(stego))


# --------------------------------------------------------------------------- #
# Test 10 — 8-bit audio.
# --------------------------------------------------------------------------- #
def test_8bit_audio():
    """Verify correct unsigned interpretation of 8-bit PCM."""
    # 8-bit PCM is unsigned (0–255).
    orig_bytes = bytes([128, 200, 50, 100])
    stego_bytes = bytes([128, 201, 50, 101])
    orig = decode_pcm(orig_bytes, sample_width=1)
    stego = decode_pcm(stego_bytes, sample_width=1)

    assert orig.tolist() == [128, 200, 50, 100]
    assert stego.tolist() == [128, 201, 50, 101]

    result = calculate_metrics(orig, stego, sample_width=1)
    assert result.modified_samples == 2
    assert result.max_sample_difference == 1


# --------------------------------------------------------------------------- #
# Test 11 — 16-bit audio.
# --------------------------------------------------------------------------- #
def test_16bit_audio():
    """Verify correct 16-bit signed interpretation."""
    orig = np.array([1000, -2000, 3000], dtype=np.int64)
    stego = np.array([1001, -1999, 3001], dtype=np.int64)
    result = calculate_metrics(orig, stego, sample_width=2)

    assert result.modified_samples == 3
    assert result.max_sample_difference == 1
    assert result.mse == pytest.approx(1.0, rel=1e-9)


# --------------------------------------------------------------------------- #
# Test 12 — 24-bit audio.
# --------------------------------------------------------------------------- #
def test_24bit_audio():
    """Verify 24-bit decoding without truncation."""
    orig_samples = [100000, -200000, 300000]
    stego_samples = [100001, -199999, 300001]
    orig_bytes = _pcm_bytes_24(orig_samples)
    stego_bytes = _pcm_bytes_24(stego_samples)

    orig = decode_pcm(orig_bytes, sample_width=3)
    stego = decode_pcm(stego_bytes, sample_width=3)

    assert orig.tolist() == orig_samples
    assert stego.tolist() == stego_samples

    result = calculate_metrics(orig, stego, sample_width=3)
    assert result.modified_samples == 3
    assert result.max_sample_difference == 1


# --------------------------------------------------------------------------- #
# Test 13 — 32-bit audio.
# --------------------------------------------------------------------------- #
def test_32bit_audio():
    """Verify correct 32-bit signed interpretation."""
    orig = np.array([1000000, -2000000, 3000000], dtype=np.int64)
    stego = np.array([1000001, -1999999, 3000001], dtype=np.int64)
    result = calculate_metrics(orig, stego, sample_width=4)

    assert result.modified_samples == 3
    assert result.max_sample_difference == 1


# --------------------------------------------------------------------------- #
# Test 14 — Real integration-style evaluation.
# --------------------------------------------------------------------------- #
def test_real_integration(tmp_path):
    """Embed a message via the real service, then compare cover vs stego."""
    cover = tmp_path / "cover.wav"
    stego = tmp_path / "stego.wav"

    # Generate a synthetic 16-bit mono WAV (2 seconds at 44.1 kHz).
    n_frames = 44100 * 2
    samples = np.array(
        [int(10000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(n_frames)],
        dtype=np.int16,
    )
    frames = samples.tobytes()
    _make_wav(str(cover), frames, channels=1, sample_width=2, rate=44100)

    # Embed a small message.
    message = "Test message for Phase 7 evaluation."
    password = "test-password"
    embed_message(str(cover), str(stego), message, password)

    # Compare.
    result = compare_audio(str(cover), str(stego))

    # Verify metrics are sensible.
    assert result.mse >= 0.0
    assert result.snr_db > 0.0 or math.isinf(result.snr_db)
    assert result.psnr_db > 0.0 or math.isinf(result.psnr_db)
    assert result.modified_samples > 0  # LSB embedding changed some samples
    assert result.max_sample_difference >= 1  # LSB changes are ±1 or 0
    assert result.max_sample_difference <= 1  # for basic LSB, max diff is 1
    assert 0.0 <= result.modification_percentage <= 100.0
