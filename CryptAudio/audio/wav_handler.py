"""CryptAudio — WAV / PCM audio handling module (Phase 3).

This module is the *audio foundation* for the future LSB steganography module.
It can inspect, validate, read and write uncompressed **PCM WAV** files, and it
can calculate the theoretical one-LSB embedding capacity of a WAV file.

Scope
-----
* Uses the Python standard-library :mod:`wave` module for all WAV I/O.
* Supports only uncompressed PCM WAV. MP3/AAC/OGG/FLAC and other lossy or
  compressed formats are out of scope (lossy compression destroys LSB data).
* No steganography is implemented here. This module only produces/consumes raw
  PCM sample data; Phase 4 will manipulate the least significant bits.

Key WAV concepts
----------------
* **Container** — WAV (RIFF) holds a ``fmt `` metadata chunk and a ``data``
  chunk with the audio samples. Only the ``data`` samples are ever modified by
  steganography; the header/metadata must stay intact.
* **PCM** — uncompressed samples stored as integers; lossless, so a
  read -> write round trip preserves the exact sample values.
* **Sample** — one amplitude value for one channel at one instant.
* **Frame** — one sample from every channel at the same instant (interleaved).
* **Sample width** — bytes per sample (1/2/3/4 => 8/16/24/32 bit).
* **Relationships**::

      frame_size_bytes = channels * sample_width
      total_samples    = n_frames * channels

Raw byte mapping (important for Phase 4 LSB work)
-------------------------------------------------
:func:`read_wav` returns the PCM ``data`` chunk as raw ``bytes`` (``frames``).
Samples are stored **little-endian** (except 8-bit, which is unsigned). For a
sample of width ``w`` bytes, sample ``i`` occupies::

    frames[i*w : (i+1)*w]

and its **least significant bit** is bit 0 of the *first* stored byte of that
sample (the little-endian low byte). Keeping the data as raw bytes is lossless
for every supported width, including 24-bit PCM which has no native integer or
NumPy dtype.

Reliability guarantees
----------------------
* Reading never modifies the source file.
* :func:`write_wav` refuses to overwrite the source when ``source_path`` is
  supplied and resolves to the same file as the output.
* WAV metadata (channels, sample width, frame rate, compression) is preserved.
* A read -> write round trip preserves the PCM bytes exactly.
"""

from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #

#: The RIFF format tag for uncompressed PCM (used in the ``fmt `` chunk).
WAVE_FORMAT_PCM: int = wave.WAVE_FORMAT_PCM  # == 1

#: Value returned by ``wave.Wave_read.getcomptype()`` for uncompressed PCM.
#: Note: Python's :mod:`wave` reports the compression *type* as the string
#: ``'NONE'`` (not the integer format tag), so PCM detection must compare
#: against this string.
WAVE_COMPRESSION_NONE: str = "NONE"

#: Sample widths (in bytes) this module can read/write as PCM.
SUPPORTED_SAMPLE_WIDTHS: tuple[int, ...] = (1, 2, 3, 4)

#: The same widths expressed in bits, for documentation/validation messages.
SUPPORTED_SAMPLE_WIDTH_BITS: tuple[int, ...] = (8, 16, 24, 32)


# --------------------------------------------------------------------------- #
# Project-specific exceptions.
# --------------------------------------------------------------------------- #


class WavError(Exception):
    """Base class for all CryptAudio WAV/audio errors."""


class WavNotFoundError(WavError):
    """Raised when the given WAV path does not exist."""


class InvalidWavError(WavError):
    """Raised when a path is not a readable, well-formed WAV file."""


class UnsupportedWavError(WavError):
    """Raised for non-PCM WAV files or unsupported sample widths."""


# --------------------------------------------------------------------------- #
# Typed data structures.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WavParameters:
    """The WAV format parameters needed to re-create a compatible file."""

    channels: int
    sample_width: int          # bytes per sample (1, 2, 3 or 4)
    frame_rate: int            # frames per second (Hz)
    n_frames: int              # number of frames
    compression_type: int      # wave.WAVE_FORMAT_PCM == 1 for PCM
    compression_name: str      # e.g. 'not compressed'

    @property
    def sample_width_bits(self) -> int:
        """Sample width expressed in bits (8, 16, 24 or 32)."""
        return self.sample_width * 8

    @property
    def frame_size_bytes(self) -> int:
        """Bytes per frame = channels * sample_width."""
        return self.channels * self.sample_width

    @property
    def total_samples(self) -> int:
        """Total number of channel samples = n_frames * channels."""
        return self.n_frames * self.channels


@dataclass(frozen=True)
class WavInfo:
    """Rich, GUI-friendly metadata about a WAV file."""

    path: str
    channels: int
    sample_width: int          # bytes
    sample_width_bits: int     # bits
    frame_rate: int
    n_frames: int
    compression_type: int
    compression_name: str
    duration_seconds: float
    is_pcm: bool

    @property
    def frame_size_bytes(self) -> int:
        """Bytes per frame = channels * sample_width."""
        return self.channels * self.sample_width

    @property
    def total_samples(self) -> int:
        """Total number of channel samples = n_frames * channels."""
        return self.n_frames * self.channels

    def parameters(self) -> WavParameters:
        """Return the :class:`WavParameters` needed to write this format back."""
        return WavParameters(
            channels=self.channels,
            sample_width=self.sample_width,
            frame_rate=self.frame_rate,
            n_frames=self.n_frames,
            compression_type=self.compression_type,
            compression_name=self.compression_name,
        )


@dataclass(frozen=True)
class WavData:
    """PCM audio data plus the parameters describing its format.

    Attributes:
        parameters: The WAV format parameters.
        frames: Raw PCM ``data``-chunk bytes (interleaved, little-endian).
            Length equals ``n_frames * channels * sample_width``.
    """

    parameters: WavParameters
    frames: bytes

    @property
    def channels(self) -> int:
        return self.parameters.channels

    @property
    def sample_width(self) -> int:
        return self.parameters.sample_width

    @property
    def frame_rate(self) -> int:
        return self.parameters.frame_rate

    @property
    def n_frames(self) -> int:
        return self.parameters.n_frames

    @property
    def total_samples(self) -> int:
        return self.parameters.total_samples


@dataclass(frozen=True)
class Capacity:
    """Theoretical one-LSB embedding capacity for a WAV file."""

    frames: int
    channels: int
    total_samples: int
    capacity_bits: int
    capacity_bytes: int


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #


def _ensure_wav_file(path: "str | os.PathLike[str]") -> Path:
    """Validate that ``path`` points to an existing, non-directory file.

    Raises:
        WavNotFoundError: If the path does not exist.
        InvalidWavError: If the path is a directory.
    """
    p = Path(path)
    if not p.exists():
        raise WavNotFoundError(f"WAV file not found: {path}")
    if p.is_dir():
        raise InvalidWavError(f"Path is a directory, not a WAV file: {path}")
    return p


def _open_wav_read(path: Path) -> wave.Wave_read:
    """Open ``path`` for reading, translating low-level errors into ours.

    Raises:
        UnsupportedWavError: If the file is a non-PCM WAV (e.g. IEEE float).
        InvalidWavError: If the file is not a well-formed WAV file.
    """
    try:
        return wave.open(str(path), "rb")
    except wave.Error as exc:
        message = str(exc).lower()
        # wave raises Error('unknown format: N') for non-PCM format tags.
        if "format" in message:
            raise UnsupportedWavError(
                f"Unsupported (non-PCM) WAV format: {path}"
            ) from exc
        raise InvalidWavError(f"Not a valid WAV file: {path}") from exc
    except EOFError as exc:
        raise InvalidWavError(f"Truncated or invalid WAV file: {path}") from exc


def _validate_format(wav_file: wave.Wave_read, path: Path) -> None:
    """Confirm the opened WAV is uncompressed PCM with a supported width.

    Raises:
        UnsupportedWavError: If compression is not PCM or the sample width is
            not one of 8/16/24/32 bits.
    """
    if wav_file.getcomptype() != WAVE_COMPRESSION_NONE:
        raise UnsupportedWavError(
            f"Only uncompressed PCM WAV is supported: {path}"
        )
    if wav_file.getsampwidth() not in SUPPORTED_SAMPLE_WIDTHS:
        raise UnsupportedWavError(
            f"Unsupported sample width ({wav_file.getsampwidth()} bytes): {path}"
        )


# --------------------------------------------------------------------------- #
# Public API — inspection.
# --------------------------------------------------------------------------- #


def inspect_wav(path: "str | os.PathLike[str]") -> WavInfo:
    """Inspect a PCM WAV file and return its metadata.

    Args:
        path: Filesystem path to a ``.wav`` file.

    Returns:
        A :class:`WavInfo` describing channels, sample width (bytes and bits),
        frame rate, frame count, compression, duration and PCM status.

    Raises:
        WavNotFoundError: If the file does not exist.
        InvalidWavError: If the path is a directory or not a valid WAV.
        UnsupportedWavError: If the WAV is non-PCM or has an unsupported width.
    """
    file_path = _ensure_wav_file(path)
    wav_file = _open_wav_read(file_path)
    try:
        _validate_format(wav_file, file_path)

        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        n_frames = wav_file.getnframes()
        compression_type = wav_file.getcomptype()
        compression_name = wav_file.getcompname()

        duration = (n_frames / frame_rate) if frame_rate else 0.0
        return WavInfo(
            path=str(file_path),
            channels=channels,
            sample_width=sample_width,
            sample_width_bits=sample_width * 8,
            frame_rate=frame_rate,
            n_frames=n_frames,
            compression_type=compression_type,
            compression_name=compression_name,
            duration_seconds=duration,
            is_pcm=(compression_type == WAVE_COMPRESSION_NONE),
        )
    finally:
        wav_file.close()


# --------------------------------------------------------------------------- #
# Public API — reading.
# --------------------------------------------------------------------------- #


def read_wav(path: "str | os.PathLike[str]") -> WavData:
    """Read a PCM WAV file into raw PCM frame bytes plus its parameters.

    The returned :class:`WavData` preserves channels, sample width, frame rate
    and the exact PCM sample bytes, so it can later be modified (Phase 4) and
    written back with :func:`write_wav` without altering the audio format.

    Note:
        The full ``data`` chunk is read into memory. This is required for
        sample-level LSB access; callers should avoid pointing this at
        pathologically large files.

    Args:
        path: Filesystem path to a ``.wav`` file.

    Returns:
        A :class:`WavData` instance.

    Raises:
        WavNotFoundError, InvalidWavError, UnsupportedWavError: as in
        :func:`inspect_wav`.
    """
    file_path = _ensure_wav_file(path)
    wav_file = _open_wav_read(file_path)
    try:
        _validate_format(wav_file, file_path)

        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        declared_frames = wav_file.getnframes()

        frames = wav_file.readframes(declared_frames)

        # Derive the true frame count from the bytes actually read, in case the
        # header's frame count disagrees with the data chunk.
        frame_size = channels * sample_width
        actual_frames = (len(frames) // frame_size) if frame_size else 0

        parameters = WavParameters(
            channels=channels,
            sample_width=sample_width,
            frame_rate=frame_rate,
            n_frames=actual_frames,
            compression_type=wav_file.getcomptype(),
            compression_name=wav_file.getcompname(),
        )
        return WavData(parameters=parameters, frames=frames)
    finally:
        wav_file.close()


# --------------------------------------------------------------------------- #
# Public API — writing.
# --------------------------------------------------------------------------- #


def write_wav(
    output_path: "str | os.PathLike[str]",
    parameters: WavParameters,
    frames: bytes,
    *,
    source_path: "str | os.PathLike[str] | None" = None,
) -> None:
    """Write PCM frame bytes to a new WAV file, preserving the audio format.

    The output WAV keeps the same channels, sample width, frame rate and
    compression (PCM) as ``parameters``. Only sample data is written; the WAV
    header is regenerated correctly by :mod:`wave`.

    Args:
        output_path: Destination ``.wav`` path.
        parameters: Format parameters (typically from :func:`read_wav`).
        frames: Raw PCM frame bytes to write.
        source_path: Optional original file path. If supplied and it resolves to
            the same file as ``output_path``, the write is refused to avoid
            clobbering the source.

    Raises:
        WavError: If the output path is invalid, would overwrite the source, or
            the frame bytes are inconsistent with ``parameters``.
    """
    out = Path(output_path)

    # Refuse to overwrite the source file during normal operation.
    if source_path is not None:
        try:
            if out.resolve() == Path(source_path).resolve():
                raise WavError(
                    "Refusing to overwrite the source WAV file; choose a "
                    "different output path."
                )
        except OSError:
            # If paths cannot be resolved (e.g. missing), fall back to a
            # literal comparison.
            if str(out) == str(source_path):
                raise WavError(
                    "Refusing to overwrite the source WAV file; choose a "
                    "different output path."
                ) from None

    if out.is_dir():
        raise WavError(f"Output path is a directory: {output_path}")
    parent = out.parent
    if str(parent) and not parent.exists():
        raise WavError(f"Output directory does not exist: {parent}")

    if not isinstance(frames, (bytes, bytearray)):
        raise WavError("frames must be bytes-like PCM data.")

    frame_size = parameters.channels * parameters.sample_width
    if frame_size <= 0:
        raise WavError("Invalid parameters: channels/sample_width must be > 0.")
    if len(frames) % frame_size != 0:
        raise WavError(
            "Frame data length is not a whole number of frames "
            f"({len(frames)} bytes, frame size {frame_size} bytes)."
        )
    if parameters.n_frames >= 0 and len(frames) != frame_size * parameters.n_frames:
        raise WavError(
            "Frame data length does not match declared n_frames "
            f"({len(frames)} bytes vs expected {frame_size * parameters.n_frames})."
        )

    with wave.open(str(out), "wb") as wav_out:
        wav_out.setnchannels(parameters.channels)
        wav_out.setsampwidth(parameters.sample_width)
        wav_out.setframerate(parameters.frame_rate)
        # wave only supports PCM on write; comptype/compname default to PCM.
        wav_out.writeframes(bytes(frames))


# --------------------------------------------------------------------------- #
# Public API — capacity.
# --------------------------------------------------------------------------- #


def calculate_capacity(n_frames: int, channels: int) -> Capacity:
    """Calculate the theoretical one-LSB embedding capacity.

    For a basic design that hides **one bit per channel sample**::

        total_samples  = n_frames * channels
        capacity_bits  = total_samples
        capacity_bytes = capacity_bits // 8

    No cryptographic/payload overhead is subtracted here; that is the concern of
    the higher-level integration phase.

    Args:
        n_frames: Number of audio frames.
        channels: Number of audio channels.

    Returns:
        A :class:`Capacity` describing frames, channels, total samples and the
        capacity in bits and bytes.

    Raises:
        WavError: If either argument is negative.
    """
    if n_frames < 0 or channels < 0:
        raise WavError("n_frames and channels must be non-negative.")

    total_samples = n_frames * channels
    capacity_bits = total_samples
    capacity_bytes = capacity_bits // 8
    return Capacity(
        frames=n_frames,
        channels=channels,
        total_samples=total_samples,
        capacity_bits=capacity_bits,
        capacity_bytes=capacity_bytes,
    )


def capacity_of(path: "str | os.PathLike[str]") -> Capacity:
    """Inspect a WAV file and return its one-LSB embedding capacity.

    Raises:
        WavNotFoundError, InvalidWavError, UnsupportedWavError: as in
        :func:`inspect_wav`.
    """
    info = inspect_wav(path)
    return calculate_capacity(info.n_frames, info.channels)
