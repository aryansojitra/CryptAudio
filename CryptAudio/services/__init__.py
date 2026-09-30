"""CryptAudio service layer package (Phase 5).

Exposes the high-level application API that composes the stable crypto, audio
and steganography modules into a single tested workflow.
"""

from services.cryptaudio_service import (
    AuthenticationFailureError,
    AudioError,
    CapacityExceededError,
    EmbedResult,
    InputValidationError,
    NoHiddenMessageError,
    ServiceError,
    available_capacity_bytes,
    embed_message,
    extract_message,
)

__all__ = [
    "embed_message",
    "extract_message",
    "available_capacity_bytes",
    "EmbedResult",
    "ServiceError",
    "InputValidationError",
    "AudioError",
    "CapacityExceededError",
    "NoHiddenMessageError",
    "AuthenticationFailureError",
]
