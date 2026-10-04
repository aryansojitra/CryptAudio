"""CryptAudio — Audio quality evaluation (Phase 7).

Quantitatively measures how much LSB embedding changes the audio signal by
comparing decoded PCM samples (not raw bytes) between cover and stego WAVs.

Metrics:
    - MSE (Mean Squared Error)
    - SNR (Signal-to-Noise Ratio, dB)
    - PSNR (Peak Signal-to-Noise Ratio, dB)
    - Total / modified sample counts
    - Modification percentage
    - Maximum absolute sample difference

The module is read-only with respect to the audio — it never modifies files.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from audio.wav_handler import WavData, read_wav


# --------------------------------------------------------------------------- #
# Exceptions.
# --------------------------------------------------------------------------- #
class EvaluationError(Exception):
    """Raised when two WAV files cannot be compared (incompatible formats)."""


# --------------------------------------------------------------------------- #
# Result structure.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AudioQualityResult:
    """Structured audio-quality comparison result.

    Attributes:
        mse: Mean squared error between cover and stego samples.
        snr_db: Signal-to-noise ratio in dB (float('inf') if noise is zero).
        psnr_db: Peak SNR in dB (float('inf') if MSE is zero).
        total_samples: Total number of compared PCM samples.
        modified_samples: Number of samples where cover != stego.
        modification_percentage: Percentage of modified samples (0–100).
        max_sample_difference: Maximum absolute difference between any pair.
    """

    mse: float
    snr_db: float
    psnr_db: float
    total_samples: int
    modified_samples: int
    modification_percentage: float
    max_sample_difference: int


# --------------------------------------------------------------------------- #
# PCM decoding.
# --------------------------------------------------------------------------- #
def decode_pcm(frames: bytes, sample_width: int) -> np.ndarray:
    """Decode raw PCM bytes into a 1D int64 array.

    Args:
        frames: Raw PCM data (interleaved channels, little-endian).
        sample_width: Bytes per sample (1, 2, 3, or 4).

    Returns:
        1D int64 array of decoded samples.

    Raises:
        ValueError: If sample_width is unsupported or frames length is invalid.
    """
    if sample_width == 1:
        # 8-bit PCM is unsigned (0–255).
        return np.frombuffer(frames, dtype=np.uint8).astype(np.int64)
    if sample_width == 2:
        # 16-bit PCM is signed little-endian.
        return np.frombuffer(frames, dtype="<i2").astype(np.int64)
    if sample_width == 3:
        # 24-bit PCM: 3 bytes per sample, signed little-endian.
        n = len(frames) // 3
        if len(frames) % 3 != 0:
            raise ValueError("Frame length is not a multiple of 3 bytes.")
        arr = np.frombuffer(frames, dtype=np.uint8).reshape(n, 3)
        # Little-endian: byte0 + byte1*256 + byte2*65536.
        values = (
            arr[:, 0].astype(np.int64)
            + (arr[:, 1].astype(np.int64) << 8)
            + (arr[:, 2].astype(np.int64) << 16)
        )
        # Sign-extend from 24-bit.
        values = np.where(values >= 0x800000, values - 0x1000000, values)
        return values
    if sample_width == 4:
        # 32-bit PCM is signed little-endian.
        return np.frombuffer(frames, dtype="<i4").astype(np.int64)
    raise ValueError(f"Unsupported sample width: {sample_width}")


def _max_amplitude(sample_width: int) -> int:
    """Return the maximum absolute amplitude for a given sample width."""
    if sample_width == 1:
        return 255  # 8-bit unsigned
    return (1 << (sample_width * 8 - 1)) - 1  # signed: 2^(bits-1) - 1


# --------------------------------------------------------------------------- #
# In-memory metrics calculation.
# --------------------------------------------------------------------------- #
def calculate_metrics(
    original_samples: np.ndarray,
    stego_samples: np.ndarray,
    sample_width: int,
) -> AudioQualityResult:
    """Compute audio-quality metrics from decoded 1D int arrays.

    Args:
        original_samples: 1D int array of cover samples.
        stego_samples: 1D int array of stego samples (same length).
        sample_width: Bytes per sample (for PSNR MAX calculation).

    Returns:
        AudioQualityResult with all metrics.

    Raises:
        ValueError: If arrays differ in length.
    """
    if len(original_samples) != len(stego_samples):
        raise ValueError(
            f"Sample length mismatch: {len(original_samples)} vs "
            f"{len(stego_samples)}"
        )
    if len(original_samples) == 0:
        raise ValueError("Cannot compute metrics on empty arrays.")

    # Convert to float64 for arithmetic (avoid int overflow in squares).
    orig = original_samples.astype(np.float64)
    stego = stego_samples.astype(np.float64)

    diff = orig - stego
    n = len(orig)

    # MSE.
    mse = float(np.mean(diff ** 2))

    # SNR.
    signal_power = float(np.mean(orig ** 2))
    noise_power = float(np.mean(diff ** 2))
    if noise_power == 0.0:
        snr_db = float("inf")
    else:
        snr_db = 10.0 * math.log10(signal_power / noise_power)

    # PSNR.
    max_amp = _max_amplitude(sample_width)
    if mse == 0.0:
        psnr_db = float("inf")
    else:
        psnr_db = 10.0 * math.log10((max_amp ** 2) / mse)

    # Modified samples.
    int_diff = np.abs(original_samples.astype(np.int64) - stego_samples.astype(np.int64))
    modified = int(np.count_nonzero(int_diff))
    max_diff = int(np.max(int_diff))

    return AudioQualityResult(
        mse=mse,
        snr_db=snr_db,
        psnr_db=psnr_db,
        total_samples=n,
        modified_samples=modified,
        modification_percentage=(modified / n) * 100.0,
        max_sample_difference=max_diff,
    )


# --------------------------------------------------------------------------- #
# File-level comparison.
# --------------------------------------------------------------------------- #
def compare_audio(
    original_wav: str,
    stego_wav: str,
) -> AudioQualityResult:
    """Compare two WAV files and return audio-quality metrics.

    Reads both files, validates that their formats are compatible (same
    channels, sample width, frame rate, and frame count), decodes PCM samples,
    and computes metrics.

    Args:
        original_wav: Path to the cover WAV file.
        stego_wav: Path to the stego WAV file.

    Returns:
        AudioQualityResult with all metrics.

    Raises:
        EvaluationError: If the files have incompatible formats.
    """
    orig_data: WavData = read_wav(original_wav)
    stego_data: WavData = read_wav(stego_wav)

    orig_params = orig_data.parameters
    stego_params = stego_data.parameters

    # Validate compatibility.
    if orig_params.channels != stego_params.channels:
        raise EvaluationError(
            f"Channel count mismatch: {orig_params.channels} vs "
            f"{stego_params.channels}"
        )
    if orig_params.sample_width != stego_params.sample_width:
        raise EvaluationError(
            f"Sample width mismatch: {orig_params.sample_width} vs "
            f"{stego_params.sample_width}"
        )
    if orig_params.frame_rate != stego_params.frame_rate:
        raise EvaluationError(
            f"Frame rate mismatch: {orig_params.frame_rate} vs "
            f"{stego_params.frame_rate}"
        )
    if orig_params.n_frames != stego_params.n_frames:
        raise EvaluationError(
            f"Frame count mismatch: {orig_params.n_frames} vs "
            f"{stego_params.n_frames}"
        )

    # Decode PCM.
    orig_samples = decode_pcm(orig_data.frames, orig_params.sample_width)
    stego_samples = decode_pcm(stego_data.frames, stego_params.sample_width)

    return calculate_metrics(orig_samples, stego_samples, orig_params.sample_width)
