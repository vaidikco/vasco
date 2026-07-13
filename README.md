# Vasco

A JARVIS-style desktop AI assistant. Say **"Hey Vasco"** (or click the island) and ask it to open apps, open websites, search the web, read your screen, remember things, or just talk.

Vasco stays as a small always-on-top pill above your current app. When you say the wake phrase it comes to the front and opens a command surface; when it answers, that surface expands to show the complete response (with scrolling for unusually long replies).

Works on **macOS, Windows, and Linux**.

## Architecture

```
 ┌────────────┐   wake word    ┌────────────────────────────┐
 │  ASR (Vosk │ ─────────────> │        VascoCore           │
 │  offline)  │                │  state machine + history   │
 └────────────┘                └────┬───────────┬───────────┘
                                    │           │
                     instant match  │           │  everything else
                                    v           v
                            ┌──────────────┐  ┌─────────────────────────┐
                            │ ActionRegistry│  │ BrainRouter             │
                            │ (open app,   │  │  Claude (cloud, w/tools)│
                            │  time, vol…) │  │  Ollama  (local)        │
                            └──────────────┘  └─────────────────────────┘
                                    │           │
                                    v           v
                            ┌────────────────────────────┐
                            │ TTS (Edge neural / native) │──> 🔊
                            └────────────────────────────┘
```

- **vasco/core.py** — orchestrator state machine (IDLE → LISTENING → THINKING/EXECUTING → SPEAKING). Headless; no Qt needed.
- **vasco/actions.py** — built-in cross-platform OS actions, matched instantly by regex *and* exposed to Claude as tools.
- **vasco/router.py** — picks who answers: built-in action, Claude (with tool use), or local Ollama. Degrades gracefully.
- **vasco/executor.py** — AST-whitelisted, process-isolated, time-limited sandbox for generated Python.
- **vasco/memory.py** — markdown vault at `~/.vasco/memory` with semantic (or keyword) recall.
- **vasco/asr.py** — ears. Vosk (offline) detects the wake word and segments speech in real time; [faster-whisper](https://github.com/SYSTRAN/faster-whisper) then transcribes the command with high accuracy. Falls back to Vosk-only if Whisper isn't installed.
- **vasco/tts.py / ocr.py** — voice (Microsoft neural, played in-process) and eyes (screen OCR).
- **vasco/ui.py** — PyQt6 "Dynamic Island" overlay.

## Setup

Works on **macOS** and **Windows**. Python **3.11–3.13** has the widest package
support (3.14 also works).

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Optional (heavy, ~2GB): screen OCR + semantic memory
pip install -r requirements-optional.txt
```

**Brain — free & local by default:** install [Ollama](https://ollama.com) and
`ollama pull llama3`. Vasco uses it automatically — no API key, no cost, works
offline. (Optional: set `ANTHROPIC_API_KEY` in a `.env` file to use Claude instead.)

**Speech models download themselves on first run:** the Vosk wake-word model
(~40MB) and the faster-whisper accuracy model (`base.en`, ~145MB). No manual steps.

## Run

Easiest — **double-click the launcher** (starts Ollama for you, then Vasco):
- macOS: **`Vasco.command`** (first time: right-click → Open)
- Windows: **`Vasco.bat`**

Or from a terminal:
```bash
python main.py            # island UI + voice
python main.py --text     # text REPL, no mic/speakers needed
python main.py --no-tts   # voice input, silent replies
```

Things to try:

- "Hey Vasco" … "open safari"
- "Hey Vasco, what time is it" (single breath works)
- "search for the weather in tokyo"
- "open YouTube"
- "open a pasta recipe in browser"
- "set volume to 40"
- "take a screenshot"
- "remember that my wifi password is hunter2"
- "what's my wifi password?"
- "what's on my screen?" (needs optional OCR extras)
- "open textedit and write me a haiku about robots" (Claude chains tools)

## Configuration

Everything is overridable via environment variables (or `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `VASCO_WAKE_WORD` | `hey vasco` | wake phrase (fuzzy matched) |
| `VASCO_OLLAMA_MODEL` | `llama3` | local brain model |
| `VASCO_ASR_ENGINE` | `auto` | `auto` (Whisper if available) / `whisper` / `vosk` |
| `VASCO_WHISPER_MODEL` | `base.en` | `tiny.en` (fastest) / `base.en` / `small.en` (most accurate) |
| `VASCO_TTS_VOICE` | `en-US-ChristopherNeural` | Microsoft neural voice (avoid `…MultilingualNeural` — slow) |
| `VASCO_VAULT` | `~/.vasco/memory` | memory vault location |
| `VASCO_LISTEN_TIMEOUT` | `10` | seconds to wait for a command after waking |
| `VASCO_ANTHROPIC_MODEL` | `claude-opus-4-8` | optional cloud model (only if a key is set) |

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Tests are hermetic: no network, mic, GUI, or API keys needed.

## Roadmap

- [ ] Streaming TTS (speak while Claude is still writing)
- [ ] Conversation mode (no wake word needed for follow-ups)
- [ ] More actions: media control, window management, calendar, email
- [ ] Vision: send screenshots to Claude directly instead of OCR text
- [ ] Ethics/permissions layer: confirmation prompts for sensitive actions
- [ ] Installer/packaging (pyinstaller)
