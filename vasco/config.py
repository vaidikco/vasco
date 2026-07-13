"""Central configuration for Vasco.

Every setting can be overridden with a VASCO_* environment variable or a
.env file in the project root, so nothing is hard-coded to one machine.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


_load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Config:
    # Wake word (matched fuzzily, lowercase)
    wake_word: str = os.environ.get("VASCO_WAKE_WORD", "hey vasco")
    # Seconds Vasco stays in LISTENING before giving up and returning to IDLE
    listen_timeout: float = float(os.environ.get("VASCO_LISTEN_TIMEOUT", "10"))

    # Optional cloud brain (Anthropic). Off unless you set a key — Vasco
    # defaults to the free, unlimited local Ollama brain so nothing is paid.
    anthropic_model: str = os.environ.get("VASCO_ANTHROPIC_MODEL", "claude-opus-4-8")
    max_tokens: int = int(os.environ.get("VASCO_MAX_TOKENS", "4096"))
    # Replies are spoken aloud, so favor snappy responses by default.
    effort: str = os.environ.get("VASCO_EFFORT", "low")

    # Local brain (Ollama)
    ollama_url: str = os.environ.get("VASCO_OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.environ.get("VASCO_OLLAMA_MODEL", "llama3")

    # Weather units for the built-in weather action: "metric" (°C) or "imperial" (°F)
    weather_units: str = os.environ.get("VASCO_WEATHER_UNITS", "metric")

    # Voice — Microsoft (Edge) neural voices.
    # Christopher is a deep, calm, JARVIS-like Microsoft voice AND it is ~4x
    # faster to synthesize than the "…MultilingualNeural" voices (≈1.0s vs
    # ≈4.3s for a short line), which is why replies start almost immediately.
    # Other fast Microsoft options: en-US-GuyNeural, en-US-AriaNeural,
    # en-US-JennyNeural. Avoid the "Multilingual" variants — they are slow.
    tts_voice: str = os.environ.get("VASCO_TTS_VOICE", "en-US-ChristopherNeural")
    # Edge accepts values such as "+5%", "-10%", and "+0Hz".  A slightly brisk
    # rate keeps spoken replies snappy.
    tts_rate: str = os.environ.get("VASCO_TTS_RATE", "+6%")
    tts_pitch: str = os.environ.get("VASCO_TTS_PITCH", "+0Hz")
    tts_volume: str = os.environ.get("VASCO_TTS_VOLUME", "+0%")
    tts_offline_voice: str = os.environ.get("VASCO_TTS_OFFLINE_VOICE", "Samantha")
    asr_model_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("VASCO_ASR_MODEL", str(PROJECT_ROOT / "model"))
        )
    )
    # Speech recognition accuracy. Vosk (bundled, offline) always handles the
    # live/wake layer. If faster-whisper is installed, it re-transcribes each
    # command for much higher accuracy (proper nouns, punctuation, etc.).
    #   engine: "auto" (whisper if available, else vosk) | "whisper" | "vosk"
    #   model : whisper size — tiny.en (fastest) | base.en (default) | small.en (most accurate)
    asr_engine: str = os.environ.get("VASCO_ASR_ENGINE", "auto")
    whisper_model: str = os.environ.get("VASCO_WHISPER_MODEL", "base.en")
    whisper_compute: str = os.environ.get("VASCO_WHISPER_COMPUTE", "int8")

    # Memory vault (Obsidian-style markdown notes)
    vault_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("VASCO_VAULT", str(Path.home() / ".vasco" / "memory"))
        ).expanduser()
    )

    # Sandbox
    script_timeout: float = float(os.environ.get("VASCO_SCRIPT_TIMEOUT", "5"))

    # How many conversation messages to keep as context (user+assistant)
    history_limit: int = int(os.environ.get("VASCO_HISTORY_LIMIT", "12"))


config = Config()
