# Stewart Architecture & Agent Guide

This document is the architectural manifest for **Stewart**. It provides context, build instructions, and design patterns for future AI agents and developers.

---

## 1. High-Level Overview

Stewart is an extensible, low-latency voice assistant for Linux desktop environments with local neural speech processing (STT and TTS) and modular command plugins.

```
                          ┌──────────────────────────┐
                          │   main.py (Boot & BLAS)  │
                          └─────────────┬────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
  ┌─────────────────────────────┐               ┌─────────────────────────────┐
  │   Startup Audio Thread      │               │   STT Init & Pre-Warm       │
  │   Plays startup.wav &       │               │   faster-whisper / Vosk     │
  │   cached greeting (<2ms)    │               │   stt.wait_ready()          │
  └─────────────────────────────┘               └──────────────┬──────────────┘
                                                               │
                                                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            App (app/app.py)                                 │
│                                                                             │
│  - Audio Stream: Reads 1024-sample mono PCM chunks (PyAudio @ 16kHz)        │
│  - Voice Activity Detection: Silero VAD (audio/input/models/silero_vad.jit) │
│  - Pause Buffering: pause_threshold (0.8s) prevents mid-sentence cutoffs   │
│  - Wake-Word Detection: remove_trigger_word() handles 'стюарт', 'stewart'   │
│  - Command Matching: Manager.find() parses commands and synonyms            │
│  - Action Execution: Dispatches to plugin actions (plugins/core, custom)    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AppAPI (api/app.py)                               │
│                                                                             │
│  - Config Merger: default config.yaml + ~/.config/stewart/config.yaml + lang │
│  - Audio Player: libmpv IPC socket client                                   │
│  - Speech Synthesis (audio/tts/):                                           │
│      • English / Multilingual -> Kokoro-82M (audio/tts/synthesis.py)         │
│      • Russian (ru)           -> Silero TTS v5 (audio/tts/silero.py)        │
│  - Audio Cache: ~/.cache/stewart/tts/<engine>|<hash>.wav                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Rebuilding Stewart

### Build with Nix
The application is packaged with Nix and builds into `./result/bin/stewart`:
```bash
nix-build default.nix
```

### Interactive Development Shell
To enter an environment with all Python dependencies (`torch`, `scipy`, `faster-whisper`, `kokoro`, `soundfile`, `pyaudio`, `python-mpv`, etc.):
```bash
nix-shell default.nix --run "python3 main.py --text-mode"
# Or run with voice:
nix-shell default.nix --run "python3 main.py"
```

### Adding New Python Packages
Whenever a new library is required:
1. Add it to `propagatedBuildInputs` in `default.nix` (under `with pypkgs; [ ... ]`).
2. Add it to `pyproject.toml` under `dependencies` or `optional-dependencies`.
3. Re-run `nix-build default.nix`.

---

## 3. Speech Subsystems

### A. Speech-to-Text (STT) — `audio/input/recognition.py`
- **Supported Backends**: `whisper` (via `faster-whisper` CTranslate2) and `vosk` (Kaldi offline).
- **Recognition Strength Presets** (`audio.stt.strength` in `config.yaml`):
  - `low` / `fast`: `tiny` model, greedy decoding (`beam_size: 1`)
  - `medium`: `base` model, beam search (`beam_size: 2`)
  - `high` (default): `small` model, precision beam search (`beam_size: 5`)
  - `ultra`: `large-v3` model, precision beam search (`beam_size: 5`)
  *(Explicit `model` and `beam_size` keys in `config.yaml` take priority over presets).*
- **Pause & Cutoff Protection**:
  - `pause_threshold`: Number of seconds of silence required to end an utterance (default: `0.8s`). This allows natural pauses between words (300ms–600ms) without fragmenting sentences.
  - `vad_threshold`: Silero VAD threshold (default: `0.5`).
  - Pre-buffer: 350ms of audio preceding voice onset is preserved to avoid clipping initial consonants.
- **Model Readiness**: `STT.wait_ready()` ensures background model loading / downloading is complete before speech recognition starts.

### B. Text-to-Speech (TTS) — `audio/tts/`
- **Dual Engine Architecture**:
  - `audio/tts/synthesis.py`: Core `TTS` class. Auto-routes Russian speech to `SileroTTS` because Kokoro does not support Russian.
  - `audio/tts/silero.py`: `SileroTTS` engine using official Silero v5 (`v5_ru.pt` via `torch.package.PackageImporter`). Auto-downloads to `~/.cache/stewart/models/v5_ru.pt`.
- **Russian Speakers**: `aidar`, `baya`, `kseniya`, `xenia`, `eugene`. Default user voice is `eugene`.
- **Speaker Fallback**: If an invalid or foreign voice name is supplied, `SileroTTS` automatically falls back to a valid Russian speaker, preventing `ValueError` crashes.
- **TTS Caching**: Audio clips are hashed using `engine={engine}|{text}|prosody={prosody}|speaker={speaker}` and stored in `~/.cache/stewart/tts/` to eliminate engine collision.

---

## 4. Configuration & Localization

### Active Language Resolution
`utils/system.py:load_lang()` resolves language in the following priority order:
1. `STEWART_LANG` environment variable
2. CLI flag `--lang <code/name>` / `-l <code/name>`
3. `~/.config/stewart/lang.txt` (or `./config/lang.txt`)
4. `lang.prefix` in `~/.config/stewart/config.yaml` (or `./config/config.yaml`)
5. Fallback: `en`

### Language Normalization
`utils/system.py:normalize_lang()` standardizes aliases so `russian`, `ru`, `русский` all map to `ru`, and `english`, `eng` map to `en`.

### Configuration Files
- System Defaults: `config/config.yaml`
- User Override: `~/.config/stewart/config.yaml`
- Language Lexicons & Commands: `config/langs/ru.yaml`, `config/langs/en.yaml`

---

## 5. Codebase Memory Knowledge Graph

This repository is indexed with `codebase-memory-mcp`:
```bash
# Get architecture overview
.agents/bin/cbm get_architecture

# Read architectural record (ADR)
.agents/bin/cbm get_adr

# Search graph symbols
.agents/bin/cbm search_graph --name-pattern ".*TTS.*"

# Reindex after code modifications
.agents/bin/cbm reindex
```
