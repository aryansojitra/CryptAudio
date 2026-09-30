"""Integration tests for the CryptAudio service layer (Phase 5).

These tests exercise the complete backend workflow — crypto + WAV audio + LSB
steganography — through :mod:`services.cryptaudio_service`, using synthetic WAV
files generated on the fly. No external audio files and no GUI are involved.

Run the FULL regression suite from the project root::

    .venv\\Scripts\\python.exe -m pytest -v
"""

from __future__ import annotations

import numpy as np
import pytest

from audio.wav_handler import (
    WAVE_COMPRESSION_NONE,
    WavParameters,
    inspect_wav,
    read_wav,
    write_wav,
)
from services.cryptaudio_service import (
    AuthenticationFailureError,
    CapacityExceededError,
    EmbedResult,
    InputValidationError,
    NoHiddenMessageError,
    available_capacity_bytes,
    embed_message,
    extract_message,
)
from steganography.lsb_embed import HEADER_SIZE

PASSWORD = "correct-password"


# --------------------------------------------------------------------------- #
# Synthetic WAV helpers.
# --------------------------------------------------------------------------- #


def _make_cover_wav(
    path,
    total_samples: int,
    *,
    channels: int = 1,
    sample_width: int = 2,
    seed: int = 1234,
    frame_rate: int = 8000,
):
    """Write a deterministic synthetic PCM WAV to ``path`` and return it."""
    assert total_samples % channels == 0
    n_frames = total_samples // channels
    rng = np.random.default_rng(seed)
    frames = rng.integers(
        0, 256, size=total_samples * sample_width, dtype=np.uint8
    ).tobytes()
    params = WavParameters(
        channels=channels,
        sample_width=sample_width,
        frame_rate=frame_rate,
        n_frames=n_frames,
        compression_type=WAVE_COMPRESSION_NONE,
        compression_name="not compressed",
    )
    write_wav(path, params, frames)
    return path


def _flip_sample_lsb_in_file(src, dst, sample_index: int):
    """Read ``src``, flip one sample's LSB, write the result to ``dst``."""
    data = read_wav(src)
    arr = bytearray(data.frames)
    arr[sample_index * data.sample_width] ^= 0x01  # little-endian low byte
    write_wav(dst, data.parameters, bytes(arr))
    return dst


# --------------------------------------------------------------------------- #
# Test 1 — complete round trip.
# --------------------------------------------------------------------------- #
def test_complete_round_trip(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000)
    stego = tmp_path / "stego.wav"
    message = "This is a secret CryptAudio message."

    result = embed_message(cover, stego, message, PASSWORD)

    assert isinstance(result, EmbedResult)
    assert stego.exists()
    assert extract_message(stego, PASSWORD) == message


# --------------------------------------------------------------------------- #
# Test 2 — Unicode messages.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "message",
    [
        "Hello CryptAudio \U0001F510",
        "\u0928\u092E\u0938\u094D\u0924\u0947",
        "\u0A97\u0AC1\u0A9C\u0AB0\u0ABE\u0AA4\u0AC0 \u0AB8\u0A82\u0AA6\u0AC7\u0AB6",
    ],
)
def test_unicode_message(tmp_path, message):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000)
    stego = tmp_path / "stego.wav"

    embed_message(cover, stego, message, PASSWORD)
    assert extract_message(stego, PASSWORD) == message


# --------------------------------------------------------------------------- #
# Test 3 — long message.
# --------------------------------------------------------------------------- #
def test_long_message(tmp_path):
    message = "CryptAudio long-form secret payload. " * 200  # ~7400 chars
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=200000)
    stego = tmp_path / "stego.wav"

    # Sanity: the message must actually fit in this cover.
    assert len(message.encode("utf-8")) < available_capacity_bytes(cover)

    embed_message(cover, stego, message, PASSWORD)
    assert extract_message(stego, PASSWORD) == message


# --------------------------------------------------------------------------- #
# Test 4 — wrong password fails authentication.
# --------------------------------------------------------------------------- #
def test_wrong_password(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000)
    stego = tmp_path / "stego.wav"

    embed_message(cover, stego, "top secret", "password-A")

    with pytest.raises(AuthenticationFailureError):
        extract_message(stego, "password-B")


# --------------------------------------------------------------------------- #
# Test 5 — tampered stego audio is not trusted.
# --------------------------------------------------------------------------- #
def test_tampered_stego_file(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000)
    stego = tmp_path / "stego.wav"
    tampered = tmp_path / "tampered.wav"

    embed_message(cover, stego, "do not tamper", PASSWORD)

    # Flip one LSB inside the encrypted-payload region (after the stego header).
    _flip_sample_lsb_in_file(stego, tampered, sample_index=(HEADER_SIZE + 5) * 8)

    with pytest.raises(AuthenticationFailureError):
        extract_message(tampered, PASSWORD)


# --------------------------------------------------------------------------- #
# Test 6 — extraction from a clean WAV fails clearly.
# --------------------------------------------------------------------------- #
def test_clean_wav(tmp_path):
    cover = _make_cover_wav(tmp_path / "clean.wav", total_samples=20000)

    with pytest.raises(NoHiddenMessageError):
        extract_message(cover, PASSWORD)


# --------------------------------------------------------------------------- #
# Test 7 — oversized message is rejected, no output created.
# --------------------------------------------------------------------------- #
def test_oversized_message(tmp_path):
    tiny = _make_cover_wav(tmp_path / "tiny.wav", total_samples=200)  # ~12 bytes
    out = tmp_path / "out.wav"

    with pytest.raises(CapacityExceededError):
        embed_message(tiny, out, "this message is far too large to fit", PASSWORD)

    assert not out.exists()
    # The temporary atomic-write file must not linger either.
    assert not (tmp_path / "out.wav.part").exists()


# --------------------------------------------------------------------------- #
# Test 8 — source WAV is never modified.
# --------------------------------------------------------------------------- #
def test_source_protection(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000)
    stego = tmp_path / "stego.wav"

    before = cover.read_bytes()
    embed_message(cover, stego, "protect the source", PASSWORD)
    after = cover.read_bytes()

    assert before == after                 # source byte-for-byte unchanged
    assert stego.resolve() != cover.resolve()
    assert stego.exists()


def test_identical_input_output_rejected(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=2000)

    with pytest.raises(InputValidationError):
        embed_message(cover, cover, "message", PASSWORD)


def test_empty_inputs_rejected(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=2000)
    out = tmp_path / "out.wav"

    with pytest.raises(InputValidationError):
        embed_message(cover, out, "", PASSWORD)
    with pytest.raises(InputValidationError):
        embed_message(cover, out, "message", "")
    with pytest.raises(InputValidationError):
        extract_message(cover, "")


# --------------------------------------------------------------------------- #
# Test 9 — audio metadata is preserved.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("channels,sample_width", [(1, 2), (2, 2), (1, 3)])
def test_metadata_preservation(tmp_path, channels, sample_width):
    total = 20000 if channels == 1 else 20000
    cover = _make_cover_wav(
        tmp_path / "cover.wav",
        total_samples=total,
        channels=channels,
        sample_width=sample_width,
    )
    stego = tmp_path / "stego.wav"

    embed_message(cover, stego, "metadata must survive", PASSWORD)

    a = inspect_wav(cover)
    b = inspect_wav(stego)
    assert b.channels == a.channels
    assert b.sample_width == a.sample_width
    assert b.sample_width_bits == a.sample_width_bits
    assert b.frame_rate == a.frame_rate
    assert b.n_frames == a.n_frames
    assert b.duration_seconds == pytest.approx(a.duration_seconds)
    assert b.is_pcm is True


# --------------------------------------------------------------------------- #
# Test 10 — audio data modification is limited to embedded LSBs.
# --------------------------------------------------------------------------- #
def test_audio_modification_is_limited(tmp_path):
    cover = _make_cover_wav(tmp_path / "cover.wav", total_samples=20000, sample_width=2)
    stego = tmp_path / "stego.wav"

    result = embed_message(cover, stego, "limited modification", PASSWORD)

    orig = read_wav(cover)
    mod = read_wav(stego)
    w = orig.sample_width

    orig_bytes = np.frombuffer(orig.frames, dtype=np.uint8)
    mod_bytes = np.frombuffer(mod.frames, dtype=np.uint8)
    assert orig_bytes.shape == mod_bytes.shape

    # Non-low bytes of every sample must be identical.
    for byte_index in range(1, w):
        assert np.array_equal(orig_bytes[byte_index::w], mod_bytes[byte_index::w])

    # Low bytes may differ only in bit 0.
    diff = orig_bytes[0::w] ^ mod_bytes[0::w]
    assert np.all((diff & 0xFE) == 0)

    # Samples beyond the embedded frame must be completely untouched.
    used_samples = result.used_bytes * 8
    assert np.array_equal(
        orig_bytes[used_samples * w :], mod_bytes[used_samples * w :]
    )

    # The stego WAV is still a structurally valid, inspectable PCM file.
    assert inspect_wav(stego).is_pcm is True
