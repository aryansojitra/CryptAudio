# CryptAudio — Cryptographic Audio Steganography Tool

## Description

A local desktop application that combines **AES-256-GCM** encryption with **LSB
(Least Significant Bit)** audio steganography to securely hide an encrypted text
message inside a **PCM `.wav`** audio file.

The secret message is first encrypted (so that even if the hidden bits are
recovered, they remain unreadable without the password), then embedded into the
least significant bit of the audio samples. The resulting stego WAV remains
normally playable and perceptually near-identical to the original.

> **Why only PCM WAV?** Lossy audio formats (MP3, AAC, OGG, etc.) apply lossy
> compression that discards fine-grained sample detail. Because LSB
> steganography stores data in the least significant bit of each sample, that
> compression can destroy the hidden information. CryptAudio therefore targets
> lossless PCM WAV only.

## Current Status

```text
Phase 7 — Audio Quality Evaluation (COMPLETE)
```

**Done:** environment (Phase 1); AES-256-GCM + PBKDF2 cryptography (Phase 2);
PCM WAV handling (Phase 3); LSB steganography (Phase 4); the integration service
layer (Phase 5); a Tkinter/`ttk` desktop GUI (Phase 6); and audio quality
evaluation (Phase 7). The evaluation module (`evaluation/audio_quality.py`)
computes MSE, SNR, PSNR, and sample-modification statistics by comparing decoded
PCM samples (not raw bytes) between cover and stego WAVs, supporting 8/16/24/32-bit
PCM without truncation. Real experiment on a 10-second stereo 16-bit WAV:
**MSE ≈ 0.001, SNR ≈ 101 dB, PSNR ≈ 120 dB, only 0.098% of samples modified,
max sample difference = 1** — confirming LSB steganography is virtually inaudible.
Test suite: crypto + audio + steganography + integration + GUI + audio quality
(111 tests, all passing).

**Not yet implemented:** security testing, documentation, and presentation
(Phases 8–10).

### Running the application

```powershell
.venv\Scripts\python.exe main.py
```

## Planned Features

* AES-256-GCM encryption
* PBKDF2-HMAC-SHA256 key derivation
* WAV processing
* LSB embedding
* LSB extraction
* Embed GUI
* Extract GUI
* Capacity calculation
* Audio quality evaluation
* MSE calculation
* SNR calculation
* Security testing

*(These are planned — none are implemented at this stage.)*

## Project Structure

```text
CryptAudio/
├── main.py
├── requirements.txt
├── README.md
├── .gitignore
├── verify_environment.py
├── gui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── embed_tab.py
│   └── extract_tab.py
├── crypto/
│   ├── __init__.py
│   └── aes_crypto.py
├── services/
│   ├── __init__.py
│   └── cryptaudio_service.py
├── steganography/
│   ├── __init__.py
│   ├── lsb_embed.py
│   └── lsb_extract.py
├── audio/
│   ├── __init__.py
│   └── wav_handler.py
├── evaluation/
│   ├── __init__.py
│   └── audio_quality.py
├── tests/
│   ├── __init__.py
│   ├── test_crypto.py
│   ├── test_steganography.py
│   ├── test_audio.py
│   ├── test_integration.py
│   ├── test_gui.py
│   └── test_audio_quality.py
├── samples/
│   └── .gitkeep
└── output/
    └── .gitkeep
```

## Environment Setup

### 1. Create the virtual environment

```powershell
python -m venv .venv
```

### 2. Activate the virtual environment

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation with an execution-policy error, either use the
batch activator:

```powershell
.venv\Scripts\activate.bat
```

or call the environment's Python directly without activating:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Verify the environment

```powershell
python verify_environment.py
```

## Dependencies

See [`requirements.txt`](requirements.txt). Tkinter is intentionally **not**
listed because it ships with the standard Python installation rather than being
installed via pip.

## Development Roadmap

| Phase | Focus |
|-------|-------|
| 1 | Environment setup — **DONE** |
| 2 | Cryptography (AES-256-GCM, PBKDF2) — **DONE** |
| 3 | WAV handling — **DONE** |
| 4 | LSB steganography — **DONE** |
| 5 | Integration — **DONE** |
| 6 | GUI — **DONE** |
| 7 | Evaluation (MSE, SNR, PSNR) — **DONE** |
| 8 | Security testing |
| 9 | Documentation |
| 10 | Presentation & viva |

## Academic Note

This is an academic group project (5 members) for an MSc Cyber Security Applied
Cryptography course. Development proceeds incrementally, one phase at a time.
