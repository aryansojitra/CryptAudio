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
Phase 6 — Desktop GUI (COMPLETE)
```

**Done:** environment (Phase 1); AES-256-GCM + PBKDF2 cryptography (Phase 2);
PCM WAV handling (Phase 3); LSB steganography (Phase 4); the integration service
layer (Phase 5); and a Tkinter/`ttk` desktop GUI (Phase 6). The GUI is a thin
view over the frozen backend — `gui/main_window.py` hosts a `ttk.Notebook` with
🔐 Embed and 🔓 Extract tabs that call only
`services/cryptaudio_service.embed_message()` / `extract_message()` /
`available_capacity_bytes()` and `audio.wav_handler.inspect_wav()` for metadata.
No crypto/WAV/LSB logic lives in the GUI. Long operations run on a worker
thread and marshal results back to the main thread via a queue + `after()` poll
loop, buttons are disabled while busy, passwords are masked and cleared after
use, and service exceptions are translated into friendly messages (no class
names or tracebacks are ever shown).
Test suite: crypto + audio + steganography + integration + GUI
(97 tests, all passing).

**Not yet implemented:** audio-quality evaluation and the remaining phases
(7–10).

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
│   └── test_gui.py
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
| 7 | Evaluation (MSE, SNR) |
| 8 | Security testing |
| 9 | Documentation |
| 10 | Presentation & viva |

## Academic Note

This is an academic group project (5 members) for an MSc Cyber Security Applied
Cryptography course. Development proceeds incrementally, one phase at a time.
